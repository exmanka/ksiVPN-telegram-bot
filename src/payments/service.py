"""``PaymentService`` — orchestrator above provider adapters.

Strictly payment-transport concerns:

- ``initiate(...)`` — create a new payment row, ask the selected provider for
  a payment URL, persist the provider-side external id, return everything the
  UI handler needs to compose the user message.
- ``handle_event(event)`` — idempotently process a payment event (webhook or
  status poll): atomic finalize via ``repository.claim_finalize``. On a winning
  claim, invokes the injected ``on_payment_succeeded`` callback exactly once.
- ``poll_pending(minutes)`` — reconciler entry.
- ``recheck_user_pending(...)`` — manual user-triggered re-check.

The service deliberately knows **nothing** about Remnawave, referrals, admin
notifications, FSM state, keyboards, or Telegram in general. All of that is
subscription business-logic and lives in ``src.services.internal_functions``,
wired in via the ``on_payment_succeeded`` callback at construction time
(see ``src/payments/runtime.py``).

This keeps the module independently testable (no aiogram/bot dependency) and
makes future provider additions a matter of writing a new adapter, with zero
churn on the post-finalize chain.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Awaitable, Callable

from src.database import postgres_dbms

from . import repository
from .enums import PaymentProviderName, PaymentStatus
from .exceptions import ProviderError, ProviderUnavailable
from .models import Money, ProviderPaymentEvent
from .providers.base import PaymentProvider


PaymentSucceededCallback = Callable[[int, int, int], Awaitable[None]]
"""Invoked once per payment when it transitions to SUCCEEDED. Args: ``(payment_id, client_id, days_number)``."""


logger = logging.getLogger(__name__)


# Minimum amount accepted by YooMoney quickpay — kept consistent with the
# legacy ``sub_renewal`` floor and ``payments.test_price`` validator.
_MIN_PRICE = Decimal("2")


@dataclass(frozen=True, slots=True)
class InitiatedPayment:
    """Result of :meth:`PaymentService.initiate` — everything the handler needs."""

    payment_id: int
    payment_url: str
    price: float
    sub_title: str
    days_number: int
    discount: float
    is_test_payment: bool


class PaymentService:
    """See module docstring."""

    def __init__(
        self,
        *,
        providers: dict[PaymentProviderName, PaymentProvider],
        on_payment_succeeded: PaymentSucceededCallback,
        test_user_ids: list[int],
        test_price: Decimal,
    ) -> None:
        """
        ``on_payment_succeeded`` is invoked exactly once per payment, after the
        atomic claim succeeds. The callback owns the full post-finalize chain
        (Remnawave sync, referral check, admin notify, user notify, FSM reset,
        keyboard update). The service does not call it again on duplicate
        events, even if the duplicate carries an updated raw_payload.
        """
        self._providers = providers
        self._on_payment_succeeded = on_payment_succeeded
        self._test_user_ids = set(test_user_ids)
        self._test_price = test_price

    @property
    def providers(self) -> dict[PaymentProviderName, PaymentProvider]:
        return self._providers

    def get_provider(self, name: PaymentProviderName) -> PaymentProvider:
        try:
            return self._providers[name]
        except KeyError as exc:
            raise ProviderUnavailable(f"Provider {name} is not registered") from exc

    # ---- initiate ----------------------------------------------------------------

    async def initiate(
        self,
        *,
        telegram_id: int,
        days_number: int,
        discount: float,
        provider_name: PaymentProviderName,
        return_url: str | None = None,
    ) -> InitiatedPayment:
        """Create a new payment and return everything the UI handler needs.

        Does NOT send messages, set FSM state, or write the telegram_message_id —
        those remain in the handler since they require ``Message`` context.
        """
        provider = self.get_provider(provider_name)

        client_id = await postgres_dbms.get_clientID_by_telegramID(telegram_id)
        sub_id, sub_title, _, sub_price = await postgres_dbms.get_subscription_info_by_clientID(client_id)

        is_test_payment = telegram_id in self._test_user_ids
        if is_test_payment:
            sub_price = float(self._test_price)

        # Per-30-day reference price scaled to actual days, with discount.
        raw_price = Decimal(str(sub_price)) / 30 * days_number * Decimal(str(1 - discount))
        price = max(raw_price, _MIN_PRICE)
        # Round to 2 decimals — providers expect "300.00" not "299.999...".
        price = price.quantize(Decimal("0.01"))

        payment_id = await repository.insert_payment(
            client_id=client_id,
            sub_id=sub_id,
            price=price,
            days_number=days_number,
            provider=provider_name,
        )

        try:
            invoice = await provider.create_invoice(
                payment_id=payment_id,
                amount=Money(amount=price, currency="RUB"),
                description=f"Подписка ksiVPN на {days_number} дн., payment_id={payment_id}",
                return_url=return_url,
            )
        except ProviderError:
            logger.exception(
                "create_invoice failed for payment_id=%s provider=%s — payment row stays PENDING",
                payment_id, provider_name,
            )
            raise

        await repository.update_provider_external_id(
            payment_id=payment_id,
            provider=provider_name,
            external_id=invoice.external_id,
        )

        logger.info(
            "Payment initiated: payment_id=%s client_id=%s provider=%s price=%s days=%d test=%s",
            payment_id, client_id, provider_name, price, days_number, is_test_payment,
        )

        return InitiatedPayment(
            payment_id=payment_id,
            payment_url=invoice.payment_url,
            price=float(price),
            sub_title=sub_title,
            days_number=days_number,
            discount=discount,
            is_test_payment=is_test_payment,
        )

    # ---- handle_event ------------------------------------------------------------

    async def handle_event(
        self,
        event: ProviderPaymentEvent,
        *,
        provider_name: PaymentProviderName,
    ) -> None:
        """Idempotently process a payment event from any source (webhook / poll).

        Dispatches by ``event.status``. Safe to call concurrently for the same
        ``payment_id`` — :func:`repository.claim_finalize` enforces single-effect
        via atomic UPDATE...RETURNING.

        ``provider_name`` is required so we can resolve ``payment_id`` via
        ``(provider, external_id)`` when the event itself doesn't carry it
        (e.g. YooMoney webhooks ship UUID labels with no encoded payment_id).
        """
        payment_id = event.payment_id
        if payment_id is None:
            payment_id = await repository.resolve_payment_id(
                provider=provider_name, external_id=event.external_id,
            )
            if payment_id is None:
                logger.error(
                    "Unresolved payment event: no row for provider=%s external_id=%s "
                    "(spoofed webhook? DB state inconsistent? ignoring)",
                    provider_name, event.external_id,
                )
                return

        if event.status == PaymentStatus.SUCCEEDED:
            await self._finalize_succeeded(payment_id, event)
        elif event.status in (PaymentStatus.FAILED, PaymentStatus.EXPIRED):
            await self._mark_failed(payment_id, event)
        else:
            # PENDING — nothing to do business-wise, just log for visibility.
            logger.info(
                "Payment event PENDING (no-op): payment_id=%s external_id=%s",
                payment_id, event.external_id,
            )

    async def _finalize_succeeded(self, payment_id: int, event: ProviderPaymentEvent) -> None:
        ctx = await repository.get_finalize_context(payment_id)
        if ctx is None:
            logger.error("Payment finalize: payment_id=%s not found in DB", payment_id)
            return

        client_id = ctx["client_id"]
        days_number = ctx["days_number"]

        claimed = await repository.claim_finalize(
            payment_id=payment_id, client_id=client_id, days_number=days_number,
        )

        # Always persist the latest raw_payload for diagnostics, regardless of claim outcome.
        if event.raw_payload is not None:
            try:
                await repository.record_raw_payload(
                    payment_id=payment_id, status=PaymentStatus.SUCCEEDED,
                    raw_payload=event.raw_payload,
                )
            except Exception:
                logger.exception("Failed to persist raw_payload for payment_id=%s", payment_id)

        if not claimed:
            logger.info(
                "Payment finalize skipped — already done: payment_id=%s external_id=%s",
                payment_id, event.external_id,
            )
            return

        logger.info(
            "Payment finalized: payment_id=%s client_id=%s days=%d external_id=%s",
            payment_id, client_id, days_number, event.external_id,
        )

        # Hand off to the business-logic chain. Any errors there are the
        # callback's responsibility — service has done its job (DB is consistent).
        try:
            await self._on_payment_succeeded(payment_id, client_id, days_number)
        except Exception:
            logger.exception(
                "on_payment_succeeded callback raised for payment_id=%s; "
                "payment is already SUCCEEDED in DB",
                payment_id,
            )

    async def _mark_failed(self, payment_id: int, event: ProviderPaymentEvent) -> None:
        await repository.update_status(
            payment_id=payment_id,
            status=event.status,
            raw_payload=event.raw_payload,
        )
        logger.info(
            "Payment marked %s: payment_id=%s external_id=%s",
            event.status, payment_id, event.external_id,
        )

    # ---- reconciler / manual recheck ---------------------------------------------

    async def poll_pending(self, minutes: int = 30) -> int:
        """Reconciler entry: poll all recently-pending payments via each provider.

        Returns the number of payments that transitioned to SUCCEEDED during
        this call. Failures on individual payments are logged and don't abort
        the rest of the batch.
        """
        pending = await repository.list_pending_recent(minutes)
        finalized = 0
        for row in pending:
            provider_str = row["provider"]
            external_id = row["external_id"]
            payment_id = row["id"]
            try:
                provider_name = PaymentProviderName(provider_str)
                provider = self.get_provider(provider_name)
            except (ProviderUnavailable, ValueError):
                logger.warning(
                    "Reconciler: unknown provider %r for payment_id=%s — skipping",
                    provider_str, payment_id,
                )
                continue

            try:
                event = await provider.get_status(external_id)
            except ProviderError:
                logger.warning(
                    "Reconciler: get_status failed for payment_id=%s — will retry next tick",
                    payment_id, exc_info=True,
                )
                continue
            except Exception:
                logger.exception(
                    "Reconciler: unexpected error for payment_id=%s — skipping",
                    payment_id,
                )
                continue

            # We already know payment_id from the DB row; backfill it into the
            # event so handle_event skips the lookup round-trip.
            if event.payment_id is None:
                event = ProviderPaymentEvent(
                    external_id=event.external_id,
                    status=event.status,
                    payment_id=payment_id,
                    raw_payload=event.raw_payload,
                )

            if event.status == PaymentStatus.SUCCEEDED:
                await self.handle_event(event, provider_name=provider_name)
                finalized += 1
            elif event.status in (PaymentStatus.FAILED, PaymentStatus.EXPIRED):
                await self.handle_event(event, provider_name=provider_name)

        if finalized:
            logger.info("Reconciler: finalized %d payment(s)", finalized)
        return finalized

    async def recheck_user_pending(
        self,
        telegram_id: int,
        *,
        minutes: int | None = 60,
    ) -> list[int]:
        """User-initiated re-check across one user's pending payments.

        ``minutes=None`` → check the entire history (used by ``/restore_payments``).
        Returns the list of ``payment_id``s that were finalized as a result.
        """
        client_id = await postgres_dbms.get_clientID_by_telegramID(telegram_id)
        if minutes is None:
            rows = await postgres_dbms.get_paymentIDs(client_id)
        else:
            rows = await postgres_dbms.get_paymentIDs_last(client_id, minutes=minutes)

        finalized: list[int] = []
        for row in rows:
            payment_id = row["id"] if "id" in row.keys() else row[0]

            info = await postgres_dbms.get_payment_provider_info(payment_id)
            if info is None or info["status"] != "pending" or info["external_id"] is None:
                continue

            try:
                provider_name = PaymentProviderName(info["provider"])
                provider = self.get_provider(provider_name)
                event = await provider.get_status(info["external_id"])
            except (ProviderUnavailable, ProviderError, ValueError):
                logger.warning(
                    "recheck_user_pending: provider lookup/get_status failed for payment_id=%s",
                    payment_id, exc_info=True,
                )
                continue

            if event.status != PaymentStatus.SUCCEEDED:
                continue

            if event.payment_id is None:
                event = ProviderPaymentEvent(
                    external_id=event.external_id,
                    status=event.status,
                    payment_id=payment_id,
                    raw_payload=event.raw_payload,
                )
            await self.handle_event(event, provider_name=provider_name)
            finalized.append(payment_id)

        return finalized
