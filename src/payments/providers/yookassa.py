"""YooKassa merchant provider.

Built on top of the official ``yookassa`` Python SDK
(https://github.com/yoomoney/yookassa-sdk-python). The SDK is synchronous
(``requests``-based); we wrap calls with :func:`asyncio.to_thread` so they
don't block the event loop. For the bot's payment volume this is fine — a
thread per payment-event is negligible overhead.

Key design notes:

- **Idempotency**: ``Payment.create`` is called with ``idempotence_key=str(payment_id)``.
  Retrying the same call (e.g. after a transient network error) returns the
  existing Payment instead of creating a new one. This matches our DB design
  where ``payments.id`` is the sole authoritative identifier.

- **Webhook authenticity**: YooKassa webhooks are **not** cryptographically
  signed by the provider. The recommended trust model is: never trust the
  body, always re-fetch via ``Payment.find_one(id)`` with our secret key.
  Only requests authenticated with our shop's API credentials can succeed,
  so a spoofed webhook with a fake payment id either returns 404 from
  YooKassa or yields a status we don't act on. We do exactly that here.

- **Auto-capture**: payments are created with ``capture=True`` so they go
  directly to ``succeeded`` after authorization. Self-employed accounts
  don't currently need the two-stage capture flow.

- **Receipt / fiscalization**: not attached at this stage. For self-employed
  the typical setup is manual reporting in «Мой налог»; if YooKassa requires
  receipt data per the merchant contract, add a ``receipt`` block to
  :meth:`_build_payment_payload` — open question in the plan.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, ClassVar, Mapping

from yookassa import Configuration, Payment as YooKassaPayment
from yookassa.domain.exceptions import ApiError, BadRequestError, ResponseProcessingError
from yookassa.domain.notification import (
    WebhookNotificationFactory,
)

from ..enums import PaymentProviderName, PaymentStatus
from ..exceptions import InvalidWebhookSignature, ProviderError
from ..models import CreatedInvoice, Money, ProviderPaymentEvent


logger = logging.getLogger(__name__)


# Map YooKassa payment status strings → our domain enum.
_STATUS_MAP: dict[str, PaymentStatus] = {
    "pending": PaymentStatus.PENDING,
    "waiting_for_capture": PaymentStatus.PENDING,  # auto-capture should skip this, but be safe
    "succeeded": PaymentStatus.SUCCEEDED,
    "canceled": PaymentStatus.FAILED,
}


class YookassaProvider:
    """``PaymentProvider`` adapter for YooKassa merchant account."""

    name: ClassVar[PaymentProviderName] = PaymentProviderName.YOOKASSA
    supports_webhook: ClassVar[bool] = True

    def __init__(
        self,
        *,
        shop_id: int,
        secret_key: str,
        return_url: str,
    ) -> None:
        # YooKassa SDK uses module-level configuration. Setting these here means
        # any subsequent ``Payment.*`` call uses these credentials. Safe as long
        # as we have a single merchant account (which we do).
        # The SDK ultimately sends shop_id as the HTTP Basic Auth username (string),
        # so we stringify defensively even though it's a numeric id in the dashboard.
        Configuration.account_id = str(shop_id)
        Configuration.secret_key = secret_key
        self._return_url = return_url

    # ---- PaymentProvider interface -------------------------------------------------

    async def create_invoice(
        self,
        *,
        payment_id: int,
        amount: Money,
        description: str,
        return_url: str | None = None,
    ) -> CreatedInvoice:
        payload = self._build_payment_payload(
            payment_id=payment_id,
            amount=amount,
            description=description,
            return_url=return_url or self._return_url,
        )
        try:
            payment = await asyncio.to_thread(
                YooKassaPayment.create, payload, str(payment_id),
            )
        except (ApiError, BadRequestError, ResponseProcessingError) as exc:
            raise ProviderError(
                f"YooKassa Payment.create failed for payment_id={payment_id}: {exc}",
            ) from exc

        confirmation_url = getattr(payment.confirmation, "confirmation_url", None)
        if not confirmation_url:
            raise ProviderError(
                f"YooKassa returned no confirmation_url for payment_id={payment_id} (status={payment.status})",
            )

        return CreatedInvoice(external_id=payment.id, payment_url=confirmation_url)

    async def get_status(self, external_id: str) -> ProviderPaymentEvent:
        try:
            payment = await asyncio.to_thread(YooKassaPayment.find_one, external_id)
        except (ApiError, BadRequestError, ResponseProcessingError) as exc:
            raise ProviderError(
                f"YooKassa Payment.find_one failed for external_id={external_id}: {exc}",
            ) from exc

        return self._normalize(payment)

    async def parse_webhook(
        self,
        *,
        body: bytes,
        headers: Mapping[str, str],  # noqa: ARG002 — YooKassa webhooks are unsigned; we verify via API re-fetch
    ) -> ProviderPaymentEvent:
        """Parse webhook envelope and re-fetch payment from API for authoritative status.

        We don't trust the body's status field at all — YooKassa doesn't sign
        webhooks, so anyone with our URL could push arbitrary JSON. Calling
        ``Payment.find_one`` with our secret_key is the only thing an attacker
        can't forge. The body is only used to extract the payment ``object.id``.
        """
        try:
            envelope = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise InvalidWebhookSignature(f"YooKassa webhook body is not valid JSON: {exc}") from exc

        try:
            notification = WebhookNotificationFactory().create(envelope)
        except Exception as exc:
            # WebhookNotificationFactory raises various exceptions for malformed
            # payloads; we collapse them to InvalidWebhookSignature so the
            # endpoint returns 400 and YooKassa doesn't retry forever.
            raise InvalidWebhookSignature(f"YooKassa webhook envelope malformed: {exc}") from exc

        external_id = getattr(notification.object, "id", None)
        if not external_id:
            raise InvalidWebhookSignature("YooKassa webhook envelope has no object.id")

        # Authoritative re-fetch.
        try:
            payment = await asyncio.to_thread(YooKassaPayment.find_one, external_id)
        except (ApiError, BadRequestError, ResponseProcessingError) as exc:
            raise ProviderError(
                f"YooKassa webhook re-fetch failed for external_id={external_id}: {exc}",
            ) from exc

        return self._normalize(payment)

    # ---- internals ----------------------------------------------------------------

    def _build_payment_payload(
        self,
        *,
        payment_id: int,
        amount: Money,
        description: str,
        return_url: str,
    ) -> dict[str, Any]:
        # YooKassa expects amount.value as a decimal string ("300.00", not 300.0).
        return {
            "amount": {
                "value": f"{amount.amount:.2f}",
                "currency": amount.currency,
            },
            "confirmation": {
                "type": "redirect",
                "return_url": return_url,
            },
            "capture": True,
            "description": description,
            "metadata": {
                # Echo our payment_id so the webhook envelope carries it back
                # — belt-and-braces; we also rely on idempotence_key=external_id.
                "payment_id": str(payment_id),
            },
        }

    def _normalize(self, payment: Any) -> ProviderPaymentEvent:
        """Convert a YooKassa SDK ``Payment`` object to our domain DTO."""
        status_str = getattr(payment, "status", "") or ""
        status = _STATUS_MAP.get(status_str, PaymentStatus.PENDING)
        if status_str not in _STATUS_MAP:
            logger.warning(
                "YooKassa returned unknown status %r for payment %s — treating as PENDING",
                status_str, payment.id,
            )

        metadata = getattr(payment, "metadata", None) or {}
        payment_id = _try_parse_payment_id(metadata.get("payment_id"))

        return ProviderPaymentEvent(
            external_id=payment.id,
            status=status,
            payment_id=payment_id,
            raw_payload=_payment_to_jsonable(payment),
        )


def _try_parse_payment_id(value: Any) -> int | None:
    """Extract our ``payment_id`` from YooKassa metadata.

    Returns ``None`` if the value is missing or malformed — caller can fall
    back to a DB lookup by ``external_id``.
    """
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _payment_to_jsonable(payment: Any) -> dict[str, Any]:
    """Best-effort conversion of a YooKassa Payment object to a plain dict.

    The SDK doesn't expose a stable dict serializer; we extract the fields
    we care about (status, amount, paid, metadata, timestamps). Used for
    forensic ``payments.raw_payload`` storage only — never for business
    logic.
    """
    out: dict[str, Any] = {}
    for attr in ("id", "status", "paid", "test", "created_at", "captured_at",
                 "expires_at", "description"):
        value = getattr(payment, attr, None)
        if value is not None:
            out[attr] = str(value) if not isinstance(value, (str, int, bool, float)) else value

    amount = getattr(payment, "amount", None)
    if amount is not None:
        out["amount"] = {
            "value": str(getattr(amount, "value", "")),
            "currency": getattr(amount, "currency", ""),
        }

    metadata = getattr(payment, "metadata", None)
    if metadata:
        out["metadata"] = dict(metadata)

    return out
