"""Thin wrapper around the ``nalogo`` SDK for ``lknpd.nalog.ru``.

The wrapper owns:

- **Auth lifecycle.** ``nalogo.Client`` requires a two-step bootstrap
  (``create_new_access_token(username, password)`` → ``authenticate(token)``).
  We do this lazily on first use, hold the token in-memory, and re-do on
  401-style errors.
- **Concurrency safety.** ``asyncio.Lock`` around (re-)auth ensures concurrent
  ``register_income`` calls from multiple webhooks don't trigger N parallel
  auth round-trips.
- **Error surface translation.** Everything ``nalogo.DomainException``-shaped
  becomes :class:`FiscalizationError` so business code only catches one type.
- **Print-URL construction.** ``nalogo`` returns the receipt UUID; the public
  print URL is a well-known format we assemble ourselves.

Single instance is constructed in ``src.payments.runtime`` if the master
``payments.fiscalization_enabled`` flag is on and credentials are present.
Each ``PaymentProvider`` (YooKassa/YooMoney) receives the same instance.
"""

from __future__ import annotations

import asyncio
import logging
from decimal import Decimal

from nalogo import Client as NalogoClient
from nalogo import UnauthorizedException

from .base import FiscalizationError, FiscalReceipt


logger = logging.getLogger(__name__)


# Public HTML page that renders the issued receipt. Standard FNS-published
# URL format; not exposed by nalogo as a helper, so we assemble it ourselves.
_PRINT_URL_TEMPLATE = "https://lknpd.nalog.ru/api/v1/receipt/{inn}/{uuid}/print"


class MoyNalogClient:
    """Shared singleton: one «Мой налог» login → all payment providers use it."""

    def __init__(self, *, inn: str, password: str) -> None:
        self._inn = inn
        self._password = password
        # Lazy — the underlying ``nalogo.Client`` opens an aiohttp session on
        # first request, which must happen inside a running event loop.
        self._client: NalogoClient | None = None
        # Guards (re-)auth so concurrent ``register_income`` calls don't fire
        # N parallel ``create_new_access_token`` round-trips on first use or
        # after token expiry.
        self._auth_lock = asyncio.Lock()
        self._authed: bool = False

    @property
    def inn(self) -> str:
        """ИНН — used by providers to construct the receipt's print URL."""
        return self._inn

    async def _get_authed_client(self) -> NalogoClient:
        """Return the underlying ``nalogo.Client`` after ensuring it's authed.

        Cheap-path (already authed) does no I/O. Slow-path takes the lock and
        does a ``create_new_access_token`` round-trip.
        """
        if self._authed and self._client is not None:
            return self._client
        async with self._auth_lock:
            if self._authed and self._client is not None:
                return self._client
            await self._reauth_locked()
            assert self._client is not None
            return self._client

    async def _reauth_locked(self) -> None:
        """Caller MUST hold ``self._auth_lock``."""
        if self._client is None:
            self._client = NalogoClient()
        try:
            token = await self._client.create_new_access_token(
                username=self._inn,
                password=self._password,
            )
            self._client.authenticate(token)
            self._authed = True
            logger.info("MoyNalog: authenticated (inn=%s)", self._inn)
        except UnauthorizedException as exc:
            self._authed = False
            raise FiscalizationError(
                f"MoyNalog auth failed for inn={self._inn}: credentials rejected",
            ) from exc
        except Exception as exc:
            self._authed = False
            raise FiscalizationError(f"MoyNalog auth failed: {exc!r}") from exc

    async def register_income(
        self,
        *,
        amount: Decimal,
        description: str,
    ) -> FiscalReceipt:
        """Register an income event in «Мой налог» and return the printable receipt.

        On a 401-class ``UnauthorizedException`` from the SDK (token expired
        between sessions), one re-auth + retry is attempted. Anything beyond
        that bubbles up as :class:`FiscalizationError`.
        """
        try:
            return await self._register_once(amount, description)
        except FiscalizationError:
            raise
        except UnauthorizedException as exc:
            logger.info(
                "MoyNalog: token rejected on register_income, re-authing once "
                "(amount=%s)", amount,
            )
            async with self._auth_lock:
                await self._reauth_locked()
            try:
                return await self._register_once(amount, description)
            except Exception as retry_exc:
                raise FiscalizationError(
                    f"MoyNalog register_income failed after re-auth: {retry_exc!r}",
                ) from retry_exc

    async def _register_once(self, amount: Decimal, description: str) -> FiscalReceipt:
        client = await self._get_authed_client()
        try:
            result = await client.income.create(
                name=description,
                amount=amount,
                quantity=1,
            )
        except UnauthorizedException:
            raise
        except Exception as exc:
            raise FiscalizationError(
                f"MoyNalog income.create failed: {exc!r}",
            ) from exc

        uuid = result.get("approvedReceiptUuid")
        if not uuid:
            raise FiscalizationError(
                f"MoyNalog income.create returned no approvedReceiptUuid (raw={result!r})",
            )
        return FiscalReceipt(
            receipt_uuid=uuid,
            print_url=_PRINT_URL_TEMPLATE.format(inn=self._inn, uuid=uuid),
        )

    async def aclose(self) -> None:
        """Close the underlying nalogo client (releases its aiohttp session)."""
        if self._client is not None:
            close = getattr(self._client, "close", None) or getattr(self._client, "aclose", None)
            if close is not None:
                try:
                    await close()
                except Exception:
                    logger.warning("MoyNalogClient aclose failed", exc_info=True)
            self._client = None
            self._authed = False
