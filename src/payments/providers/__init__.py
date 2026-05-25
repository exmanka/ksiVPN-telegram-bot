"""Provider adapters for external payment gateways.

Each provider implements ``PaymentProvider`` (see ``base.py``) and adapts its
SDK / HTTP API to the common contract. Provider SDK types must not leak past
this package's boundary — providers return DTOs from ``src.payments.models``.
"""

from .base import PaymentProvider

__all__ = ["PaymentProvider"]
