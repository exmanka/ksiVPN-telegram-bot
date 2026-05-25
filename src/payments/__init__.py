"""Multi-provider payment module.

Public surface:
- ``PaymentProvider``: Protocol all provider adapters implement.
- ``PaymentStatus``, ``PaymentProviderName``: domain enums.
- ``CreatedInvoice``, ``ProviderPaymentEvent``: provider-facing DTOs.
- ``Money``: value object for monetary amounts.
- ``PaymentError`` and subclasses: domain exception hierarchy.

Handlers and services outside this package should depend on ``PaymentService``
(introduced in a later PR) and the types re-exported here — not on individual
provider implementations.
"""

from .enums import PaymentProviderName, PaymentStatus
from .exceptions import (
    InvalidWebhookSignature,
    PaymentError,
    ProviderError,
    ProviderUnavailable,
)
from .models import CreatedInvoice, Money, ProviderPaymentEvent
from .providers.base import PaymentProvider

__all__ = [
    "CreatedInvoice",
    "InvalidWebhookSignature",
    "Money",
    "PaymentError",
    "PaymentProvider",
    "PaymentProviderName",
    "PaymentStatus",
    "ProviderError",
    "ProviderPaymentEvent",
    "ProviderUnavailable",
]
