"""Domain-layer wrapper over ``postgres_dbms`` payment helpers.

All SQL stays in ``src/database/postgres_dbms.py``. This module adds typing,
``StrEnum`` ↔ ``str`` conversion, and small composition helpers so that
``PaymentService`` doesn't import ``postgres_dbms`` directly.

Keep this thin — when a new field is needed in ``payments``, prefer adding it
as a new ``postgres_dbms`` function rather than building ad-hoc SQL here.
"""

import datetime
from decimal import Decimal
from typing import Any

import asyncpg

from src.database import postgres_dbms

from .enums import PaymentProviderName, PaymentStatus


async def insert_payment(
    *,
    client_id: int,
    sub_id: int,
    price: Decimal | float,
    days_number: int,
    provider: PaymentProviderName,
) -> int:
    """INSERT a new ``payments`` row in ``pending`` state and return its id.

    ``external_id`` is left NULL — gets populated by ``update_provider_external_id``
    once the provider has issued its own id.

    Raises ``RuntimeError`` if the INSERT returns no id (unexpected — would
    indicate a DB constraint or pool issue).
    """
    payment_id = await postgres_dbms.insert_payment(
        client_id, sub_id, float(price), days_number, str(provider),
    )
    if payment_id is None:
        raise RuntimeError(
            f"insert_payment returned None for client_id={client_id}, provider={provider}",
        )
    return payment_id


async def update_provider_external_id(
    *, payment_id: int, provider: PaymentProviderName, external_id: str,
) -> None:
    """Record the provider-side payment id after ``create_invoice`` succeeded."""
    await postgres_dbms.update_payment_provider_external(
        payment_id, str(provider), external_id,
    )


async def update_status(
    *,
    payment_id: int,
    status: PaymentStatus,
    paid_at: datetime.datetime | None = None,
    raw_payload: dict[str, Any] | list[Any] | None = None,
) -> None:
    """Update payment ``status``; optionally record ``paid_at`` and ``raw_payload``."""
    await postgres_dbms.update_payment_status(
        payment_id, str(status), paid_at, raw_payload,
    )


async def claim_finalize(
    *, payment_id: int, client_id: int, days_number: int,
) -> bool:
    """Atomic idempotent finalize. See :func:`postgres_dbms.claim_payment_finalize`.

    Returns ``True`` when this call did the finalization, ``False`` when another
    caller had already done it (webhook+reconciler race, double-delivered webhook,
    manual re-check after webhook).
    """
    return await postgres_dbms.claim_payment_finalize(payment_id, client_id, days_number)


async def get_finalize_context(payment_id: int) -> asyncpg.Record | None:
    """Fetch everything needed to finalize a payment in one round-trip."""
    return await postgres_dbms.get_payment_finalize_context(payment_id)


async def resolve_payment_id(
    *, provider: PaymentProviderName, external_id: str,
) -> int | None:
    """Look up our ``payments.id`` from a provider-side ``external_id``.

    Used by ``PaymentService.handle_event`` to backfill ``payment_id`` for
    events where the provider couldn't extract it from its payload (e.g.
    YooMoney now ships UUID labels, which carry no payment_id).
    """
    return await postgres_dbms.get_payment_id_by_external(str(provider), external_id)


async def record_raw_payload(
    *, payment_id: int, status: PaymentStatus, raw_payload: dict[str, Any] | list[Any],
) -> None:
    """Persist webhook body / get_status response for forensics.

    Non-transactional with the main finalize step — diagnostics only.
    """
    await postgres_dbms.update_payment_status(
        payment_id, str(status), None, raw_payload,
    )


async def get_legacy_status(payment_id: int) -> bool | None:
    """Return legacy ``is_successful`` flag for ``payment_id``.

    Used by handlers that already grew around the legacy column. New code
    should rely on :func:`claim_finalize` returning ``False`` instead.
    """
    return await postgres_dbms.get_payment_status(payment_id)


async def list_pending_recent(minutes: int = 30) -> list[asyncpg.Record]:
    """Recent pending payments — feed for the APScheduler reconciler job."""
    return await postgres_dbms.list_pending_payments_recent(minutes)
