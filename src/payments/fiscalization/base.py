"""Domain types shared across the fiscalization subpackage."""

from dataclasses import dataclass

from ..exceptions import PaymentError


@dataclass(frozen=True, slots=True)
class FiscalReceipt:
    """Result of a successful income registration with the tax authority.

    Attributes:
        receipt_uuid: Provider-specific receipt identifier. For «Мой налог» —
            the ``approvedReceiptUuid`` returned by the income-creation API.
            Used for audit and (potentially) cancellation.
        print_url: Public HTML page rendering the receipt — suitable to share
            with the buyer to satisfy 54-ФЗ / 422-ФЗ "transmission of the
            receipt to the buyer" requirement.
    """
    receipt_uuid: str
    print_url: str


class FiscalizationError(PaymentError):
    """Anything that goes wrong while registering income with the tax authority.

    Wraps the underlying SDK exceptions (``nalogo.DomainException`` subtree)
    so business-logic call sites have one type to catch.
    """
