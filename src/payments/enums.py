"""Payment-domain enumerations.

Values are kept as bare strings so they map directly to ``payments.status`` and
``payments.provider`` columns without serialization helpers. ``StrEnum`` makes
instances usable wherever a ``str`` is expected (e.g. ``str(PaymentStatus.SUCCEEDED) == 'succeeded'``).
"""

import enum


class PaymentStatus(enum.StrEnum):
    """Mirror of the ``payments.status`` column.

    Lifecycle: PENDING → (SUCCEEDED | FAILED | EXPIRED).
    """

    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    EXPIRED = "expired"


class PaymentProviderName(enum.StrEnum):
    """Mirror of the ``payments.provider`` column.

    Add a new member only when an actual provider adapter ships — values are
    persisted in the database and read by reconciler/webhook routing.
    """

    YOOMONEY = "yoomoney"
    YOOKASSA = "yookassa"
