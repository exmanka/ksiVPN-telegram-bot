"""Domain DTOs for the payment module.

These are the value objects that cross the boundary between provider adapters
and ``PaymentService``. They're deliberately small and frozen — providers MUST
NOT leak SDK-specific types upward.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from .enums import PaymentStatus


@dataclass(frozen=True, slots=True)
class Money:
    """Monetary amount with currency.

    ``amount`` is a ``Decimal`` to preserve precision across rounding boundaries
    (provider APIs expect strings like ``"300.00"``, not floats).
    """

    amount: Decimal
    currency: str = "RUB"


@dataclass(frozen=True, slots=True)
class CreatedInvoice:
    """What ``PaymentProvider.create_invoice`` returns.

    ``external_id``: provider-side payment identifier (UUID for YooKassa, our
    own ``payment_id`` echoed for YooMoney where label == external_id).

    ``payment_url``: URL the user is redirected to in order to complete the
    payment (confirmation page on the gateway).
    """

    external_id: str
    payment_url: str


@dataclass(frozen=True, slots=True)
class ProviderPaymentEvent:
    """Normalized payment event from either a webhook or a status poll.

    ``payment_id`` — our database row id.

    - For webhook events: providers MUST populate this (parsed from the
      provider-side metadata: YooMoney ``label`` field, YooKassa
      ``metadata.payment_id``).
    - For ``get_status`` results: providers populate this when they can extract
      it from the response; otherwise the caller (reconciler) knows it from its
      own DB query and ignores this field.

    ``external_id`` — provider-side payment identifier.

    ``raw_payload`` — webhook body parsed to dict OR the provider's
    ``get_status`` response shape. Persisted in ``payments.raw_payload`` for
    diagnostics. Must be JSON-serializable (plain strings/numbers/bools/lists/dicts);
    providers must convert any provider-SDK types (Decimals, datetimes) before
    populating this field.
    """

    external_id: str
    status: PaymentStatus
    payment_id: int | None = None
    raw_payload: dict[str, Any] | None = None
