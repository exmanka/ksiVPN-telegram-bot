"""``PaymentProvider`` protocol — contract every gateway adapter implements."""

from decimal import Decimal
from typing import ClassVar, Mapping, Protocol, runtime_checkable

from ..enums import PaymentProviderName
from ..fiscalization import FiscalReceipt
from ..models import CreatedInvoice, Money, ProviderPaymentEvent


@runtime_checkable
class PaymentProvider(Protocol):
    """Adapter contract for an external payment gateway.

    Implementations live in ``src.payments.providers.<vendor>``. ``PaymentService``
    routes to them by ``name`` and treats them as black boxes — no provider-
    specific code may live outside this package.

    All methods are async. Network errors raise ``ProviderError``; signature
    failures raise ``InvalidWebhookSignature``. See ``src.payments.exceptions``.
    """

    name: ClassVar[PaymentProviderName]
    """Identifier used for DB ``payments.provider`` column and config lookup."""

    supports_webhook: ClassVar[bool]
    """True if the provider can push payment events to our webhook endpoint.

    Reconciler is always used as a safety net regardless, but knowing this lets
    the webhook router refuse traffic for providers that should never deliver
    (defense against misrouting).
    """

    async def create_invoice(
        self,
        *,
        payment_id: int,
        amount: Money,
        description: str,
        return_url: str | None = None,
    ) -> CreatedInvoice:
        """Register a new payment with the gateway and return a confirmation URL.

        ``payment_id`` is our database row id — providers use it as label
        (YooMoney) and idempotence_key (YooKassa). Re-calling with the same
        ``payment_id`` MUST be safe and return an equivalent ``CreatedInvoice``
        (provider-side idempotency guarantees this).
        """
        ...

    async def get_status(self, external_id: str) -> ProviderPaymentEvent:
        """Poll the gateway for current status of a specific payment.

        Used by the reconciler job and by the manual ``/restore_payments`` flow.
        Returns a normalized ``ProviderPaymentEvent`` — ``payment_id`` may be
        ``None`` if the provider's response doesn't carry it.
        """
        ...

    async def parse_webhook(
        self,
        *,
        body: bytes,
        headers: Mapping[str, str],
    ) -> ProviderPaymentEvent:
        """Verify and parse a webhook payload from this provider.

        Raises ``InvalidWebhookSignature`` if the signature/HMAC check fails.
        For providers where ``supports_webhook is False``, calling this MUST
        raise ``NotImplementedError`` — but such providers should never have
        their webhook route registered in the first place.
        """
        ...

    async def fiscalize_income(
        self,
        *,
        payment_id: int,
        amount: Decimal,
        description: str,
    ) -> FiscalReceipt | None:
        """Register income with the tax authority (ФНС) for this payment.

        Returns ``None`` when fiscalization is disabled for this provider OR
        when this provider doesn't fiscalize at all. Returns a populated
        :class:`FiscalReceipt` on success. Raises
        :class:`~src.payments.fiscalization.FiscalizationError` on registration
        failure — the business-logic chain handles it as best-effort (logs +
        admin alert, payment is not unwound).

        Each concrete provider decides its mechanism:

        - YooKassa, YooMoney: delegate to a shared ``MoyNalogClient`` (direct
          calls to ``lknpd.nalog.ru`` since YooKassa removed its built-in
          fiscalization for self-employed on 2025-12-29).
        - Hypothetical Robokassa or CloudPayments (if their built-in
          fiscalization comes back): read receipt URL out of their own payment
          response — no «Мой налог» call needed.
        """
        ...
