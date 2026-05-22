"""YooMoney P2P-wallet provider.

Replaces the legacy ``src/services/aiomoney.py``. Differences from the legacy
implementation:

- Webhook-driven instead of polling: ``parse_webhook`` verifies HMAC-SHA256 of
  the YooMoney HTTP-notification payload (see
  https://yoomoney.ru/docs/wallet/using-api/notification-p2p-incoming).
- Retry-with-backoff on the outbound ``operation-history`` call, with a single
  long-lived ``aiohttp.ClientSession`` — fixes the spammy
  ``ConnectionResetError [Errno 104] Connection reset by peer`` exceptions
  produced by the legacy short-lived sessions under churn.
- ``get_status`` exists only as a reconciler fallback — the primary signal is
  the webhook.
"""

import asyncio
import hashlib
import hmac
import logging
import urllib.parse
import uuid
from typing import Any, ClassVar, Mapping

import aiohttp

from ..enums import PaymentProviderName, PaymentStatus
from ..exceptions import InvalidWebhookSignature, ProviderError
from ..models import CreatedInvoice, Money, ProviderPaymentEvent


logger = logging.getLogger(__name__)


_QUICKPAY_URL = "https://yoomoney.ru/quickpay/confirm.xml"
_OPERATION_HISTORY_URL = "https://yoomoney.ru/api/operation-history"

# How many times to retry a transient network failure (ClientOSError,
# ServerDisconnectedError, asyncio.TimeoutError) on outbound HTTP. Total
# attempts = 1 + this. Backoff is exponential: 0.5s, 1s, 2s.
_MAX_RETRIES = 3
_REQUEST_TIMEOUT_SECONDS = 10

_RETRYABLE_ERRORS: tuple[type[BaseException], ...] = (
    aiohttp.ClientOSError,
    aiohttp.ServerDisconnectedError,
    asyncio.TimeoutError,
)


class YooMoneyTransferProvider:
    """``PaymentProvider`` adapter for YooMoney P2P-wallet."""

    name: ClassVar[PaymentProviderName] = PaymentProviderName.YOOMONEY
    supports_webhook: ClassVar[bool] = True

    def __init__(
        self,
        *,
        receiver_account: int,
        access_token: str,
        notification_secret: str,
    ) -> None:
        self._receiver_account = receiver_account
        self._access_token = access_token
        self._notification_secret = notification_secret
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Lazily create the shared ``ClientSession`` once we're inside a running loop."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=_REQUEST_TIMEOUT_SECONDS),
                connector=aiohttp.TCPConnector(limit=10, keepalive_timeout=30),
            )
        return self._session

    async def aclose(self) -> None:
        """Close the shared session on application shutdown."""
        if self._session is not None and not self._session.closed:
            await self._session.close()
            self._session = None

    async def _request_with_retry(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
    ) -> aiohttp.ClientResponse:
        """HTTP request wrapped in exponential-backoff retry for transient errors.

        Caller MUST consume the response inside ``async with`` to avoid leaking
        connections — but we return the response object directly so the caller
        can read body/headers. To keep this safe, callers use the returned
        ``ClientResponse`` from inside a single ``async with`` that wraps the
        whole request — see ``get_status`` for the pattern.
        """
        last_exc: BaseException | None = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                session = await self._get_session()
                # We deliberately don't use `async with` here; caller handles it.
                return await session.request(method, url, headers=headers, params=params, data=data)
            except _RETRYABLE_ERRORS as exc:
                last_exc = exc
                if attempt == _MAX_RETRIES:
                    break
                backoff = 0.5 * (2 ** attempt)
                logger.warning(
                    "YooMoney %s %s attempt %d/%d failed (%s); retrying in %.1fs",
                    method, url, attempt + 1, _MAX_RETRIES + 1, exc.__class__.__name__, backoff,
                )
                await asyncio.sleep(backoff)
        raise ProviderError(f"YooMoney {method} {url} failed after {_MAX_RETRIES + 1} attempts: {last_exc!r}")

    # ---- PaymentProvider interface -------------------------------------------------

    async def create_invoice(
        self,
        *,
        payment_id: int,
        amount: Money,
        description: str,  # noqa: ARG002 — YooMoney quickpay doesn't carry a description
        return_url: str | None = None,
    ) -> CreatedInvoice:
        """Build a YooMoney quickpay URL with a freshly-generated UUID label.

        For P2P-wallet, payment is initiated by the user navigating to the
        returned URL; no API call needed at this stage. We still GET the
        quickpay endpoint to let YooMoney resolve any redirects (matches
        legacy behavior).

        **Why UUID instead of ``payment_id`` as label**: YooMoney's wallet
        stores every operation's label forever. If we used a sequential
        ``payment_id``, dev environments (where ``payment_id`` restarts from 1
        after a DB reset) would collide with historic operations stored in the
        wallet from previous dev cycles, causing ``get_status`` to falsely
        report fresh payments as already SUCCEEDED. UUIDs guarantee that every
        label is unique forever, across all environments sharing a wallet, so
        server-side ``label`` filtering on the API stays accurate.

        The returned ``external_id`` (== UUID label) is persisted in
        ``payments.external_id``. ``PaymentService.handle_event`` then resolves
        ``external_id → payment_id`` via DB lookup when webhooks arrive.
        """
        label = str(uuid.uuid4())
        params: dict[str, Any] = {
            "receiver": self._receiver_account,
            "quickpay-form": "button",
            "paymentType": "PC",  # YooMoney wallet (matches legacy default in sub_renewal)
            "sum": str(amount.amount),
            "label": label,
        }
        if return_url:
            params["successURL"] = return_url

        resp = await self._request_with_retry(
            "GET", _QUICKPAY_URL, params=params,
        )
        async with resp:
            if resp.status >= 400:
                raise ProviderError(
                    f"YooMoney quickpay returned status {resp.status} for payment_id={payment_id}",
                )
            payment_url = str(resp.url)

        return CreatedInvoice(
            external_id=label,
            payment_url=payment_url,
        )

    async def get_status(self, external_id: str) -> ProviderPaymentEvent:
        """Reconciler / manual-recheck path: poll ``operation-history`` by UUID label.

        Returns ``PaymentStatus.SUCCEEDED`` only if an operation matches the
        ``external_id`` (UUID) and has ``status == "success"``. Otherwise
        ``PENDING``. The YooMoney wallet API doesn't expose explicit
        failed/expired statuses for incoming P2P transfers — absence simply
        means "not yet paid".

        Server-side ``label`` filter is safe to use because labels are UUIDs
        (see :meth:`create_invoice`) — no collisions with historic operations
        in the wallet, even across environments. A defensive client-side
        filter is kept as belt-and-braces (cheap and protects against the
        unlikely case of YooMoney returning unrelated operations).

        ``payment_id`` in the returned event is ``None`` — UUID labels carry
        no encoded payment id. :meth:`PaymentService.handle_event` resolves
        ``payment_id`` from ``external_id`` via DB lookup.
        """
        headers = {"Authorization": f"Bearer {self._access_token}"}
        resp = await self._request_with_retry(
            "POST", _OPERATION_HISTORY_URL, headers=headers, data={"label": external_id},
        )
        async with resp:
            if resp.status >= 400:
                raise ProviderError(
                    f"YooMoney operation-history returned status {resp.status} for label={external_id}",
                )
            payload = await resp.json(content_type=None)

        operations = payload.get("operations") or []
        # Client-side filter — defensive (in case the API ignores the param for some account configs).
        matching = [op for op in operations if op.get("label") == external_id]
        if matching and matching[-1].get("status") == "success":
            return ProviderPaymentEvent(
                external_id=external_id,
                status=PaymentStatus.SUCCEEDED,
                payment_id=None,  # resolved by PaymentService.handle_event via DB lookup
                raw_payload=matching[-1],
            )

        return ProviderPaymentEvent(
            external_id=external_id,
            status=PaymentStatus.PENDING,
            payment_id=None,
        )

    async def parse_webhook(
        self,
        *,
        body: bytes,
        headers: Mapping[str, str],  # noqa: ARG002 — YooMoney signs only the body
    ) -> ProviderPaymentEvent:
        """Verify HMAC-SHA256 and normalize the P2P-incoming notification.

        Algorithm (https://yoomoney.ru/docs/wallet/using-api/notification-p2p-incoming):
          1. Parse application/x-www-form-urlencoded body.
          2. Exclude ``sign``; keep all other parameters (including the legacy
             ``sha1_hash`` if present — it's still part of the signed payload).
          3. Sort by parameter name (alphabetically).
          4. URL-encode each value (RFC 3986).
          5. Join as ``key=value&key=value``.
          6. HMAC-SHA256 with notification_secret → hex (lowercase).
          7. Constant-time compare against ``sign``.
        """
        try:
            decoded = body.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise InvalidWebhookSignature(f"YooMoney webhook body is not valid UTF-8: {exc}") from exc

        # parse_qs preserves duplicate keys as lists; YooMoney never sends duplicates,
        # so we collapse to scalar with [0].
        parsed = urllib.parse.parse_qs(decoded, keep_blank_values=True, strict_parsing=False)
        fields = {k: v[0] for k, v in parsed.items()}

        provided_sign = fields.pop("sign", None)
        if not provided_sign:
            raise InvalidWebhookSignature("YooMoney webhook missing 'sign' parameter")

        expected_sign = _compute_yoomoney_signature(fields, self._notification_secret)
        if not hmac.compare_digest(expected_sign, provided_sign):
            logger.warning(
                "YooMoney webhook signature mismatch (label=%s, operation_id=%s)",
                fields.get("label"), fields.get("operation_id"),
            )
            raise InvalidWebhookSignature("YooMoney webhook signature mismatch")

        notification_type = fields.get("notification_type")
        if notification_type not in ("p2p-incoming", "card-incoming"):
            # Defensive: bot's YooMoney account should only receive these two.
            raise InvalidWebhookSignature(
                f"YooMoney webhook unexpected notification_type={notification_type!r}",
            )

        label = fields.get("label", "")
        # label is a UUID we generated in create_invoice — it carries no
        # encoded payment_id, so we leave that field None. PaymentService
        # resolves payment_id via (provider, external_id) DB lookup.
        return ProviderPaymentEvent(
            external_id=label,
            status=PaymentStatus.SUCCEEDED,  # YooMoney only notifies on success
            payment_id=None,
            raw_payload=fields,
        )


def _compute_yoomoney_signature(fields: dict[str, str], secret: str) -> str:
    """Pure helper for HMAC-SHA256 over sorted, URL-encoded fields."""
    parts = [
        f"{key}={urllib.parse.quote(str(value), safe='')}"
        for key, value in sorted(fields.items())
    ]
    payload = "&".join(parts)
    digest = hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return digest
