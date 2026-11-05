"""``payments`` table: creation, idempotent finalize, provider state, history and stats."""
import asyncpg
import datetime
import json
from decimal import Decimal

from src.database.connection import acquire


async def get_paymentIDs(client_id: int) -> list[asyncpg.Record]:
    """Return all payments ids created by client.

    :param client_id:
    :return: list of asyncgp.Record objects having (id)
    :rtype: list[asyncpg.Record]
    """
    async with acquire() as conn:
        return await conn.fetch(
            '''
            SELECT id
            FROM payments
            WHERE client_id = $1
            ORDER BY date_of_initiation DESC
            ''',
            client_id)


async def get_paymentIDs_last(client_id: int, minutes: int) -> list[asyncpg.Record]:
    """Return all created by client payments in last n minutes.

    :param client_id
    :param minutes: number of minutes for which ids are selected
    :return: list of asyncgp.Record objects having (id)
    :rtype: list[asyncpg.Record]
    """
    async with acquire() as conn:
        return await conn.fetch(
            '''
            SELECT id
            FROM payments
            WHERE client_id = $1
            AND date_of_initiation > CURRENT_TIMESTAMP - make_interval(mins => $2)
            ORDER BY date_of_initiation DESC;
            ''',
            client_id, minutes)


async def get_payments_successful_info(client_id: int) -> list[asyncpg.Record]:
    """Return information about successful payments by client.

    :param client_id:
    :return: list of asyncgp.Record objects having (p.id, s.title, p.price, p.days_number, p.date_of_initiation)
    :rtype: list[asyncpg.Record]
    """
    async with acquire() as conn:
        return await conn.fetch(
            '''
            SELECT p.id, s.title, p.price, p.days_number, p.date_of_initiation
            FROM payments AS p
            JOIN subscriptions AS s
            ON p.sub_id = s.id
            WHERE p.client_id = $1
            AND p.is_successful = TRUE;
            ''',
            client_id)


async def get_payments_successful_number(client_id: int) -> int:
    """Return number of successful payments initiated by client."""
    async with acquire() as conn:
        return await conn.fetchval(
            '''
            SELECT COUNT(*)
            FROM payments
            WHERE client_id = $1
            AND is_successful = TRUE;
            ''',
            client_id)


async def get_payments_successful_sum(client_id: int) -> Decimal:
    """Return sum of successful payments initiated by client."""
    async with acquire() as conn:
        return await conn.fetchval(
            '''
            SELECT
            CASE
                WHEN SUM(price) IS NULL THEN 0.00
                ELSE SUM(price)
            END
            FROM payments
            WHERE client_id = $1
            AND is_successful = TRUE;
            ''',
            client_id)


async def get_payment_status(payment_id: int) -> bool | None:
    """Return TRUE if payment was successful else FALSE."""
    async with acquire() as conn:
        return await conn.fetchval(
            '''
            SELECT is_successful
            FROM payments
            WHERE id = $1;
            ''',
            payment_id)


async def get_payment_telegram_message_id(payment_id: int) -> int | None:
    """Return telegram message id for specified payment_id."""
    async with acquire() as conn:
        return await conn.fetchval(
            '''
            SELECT telegram_message_id
            FROM payments
            WHERE id = $1;
            ''',
            payment_id)


async def get_payment_days_number(payment_id: int) -> int | None:
    """Return paid number of days for specified payment_id."""
    async with acquire() as conn:
        return await conn.fetchval(
            '''
            SELECT days_number
            FROM payments
            WHERE id = $1;
            ''',
            payment_id)


async def get_payment_last_message_id(client_id: int) -> asyncpg.Record | None:
    """Return telegram message id for last created payment."""
    async with acquire() as conn:
        return await conn.fetchval(
            '''
            SELECT telegram_message_id
            FROM payments
            WHERE client_id = $1
            ORDER BY date_of_initiation DESC
            LIMIT 1;
            ''',
            client_id)


async def get_earnings_per_month() -> Decimal:
    """Return sum of successful payments' prices per current month. Is used by administrator."""
    async with acquire() as conn:
        return await conn.fetchval(
            '''
            SELECT COALESCE(SUM(price), 0)
            FROM payments
            WHERE is_successful = TRUE
            AND date_of_initiation > date_trunc('month', CURRENT_TIMESTAMP);
            '''
        )


async def insert_payment(
    client_id: int, sub_id: int, price: float, days_number: int, provider: str,
) -> int | None:
    """Add new payment for client in DB.

    ``provider`` is the payment-gateway identifier (e.g. 'yoomoney', 'yookassa').
    ``external_id`` is left NULL — set later via ``update_payment_provider_external``
    once the provider has issued its own payment id.
    """
    async with acquire() as conn:
        return await conn.fetchval(
            '''
            INSERT INTO payments (client_id, sub_id, price, days_number, provider)
            VALUES($1, $2, $3, $4, $5)
            RETURNING id;
            ''',
            client_id, sub_id, price, days_number, provider)


async def claim_payment_finalize(payment_id: int, client_id: int, paid_days: int) -> bool:
    """Atomic idempotent finalize: mark payment succeeded AND extend subscription, exactly once.

    The ``payments`` UPDATE is guarded by ``WHERE status != 'succeeded'`` and RETURNING.
    If no row was updated, another concurrent caller (webhook, reconciler, manual recheck)
    already finalized this payment — we return ``False`` and the caller skips the
    post-finalize chain (Remnawave sync, referral, admin notify) to avoid double-effects.

    Both UPDATEs run in one transaction so partial-finalize is impossible.

    :returns: ``True`` if this call performed the finalization; ``False`` if already done.
    """
    async with acquire() as conn:
        async with conn.transaction():
            updated_id = await conn.fetchval(
                '''
                UPDATE payments
                SET is_successful = TRUE,
                    status        = 'succeeded',
                    paid_at       = CURRENT_TIMESTAMP,
                    updated_at    = CURRENT_TIMESTAMP
                WHERE id = $1 AND status != 'succeeded'
                RETURNING id;
                ''',
                payment_id)
            if updated_id is None:
                return False

            await conn.execute(
                '''
                UPDATE clients_subscriptions
                SET paid_days_counter = paid_days_counter + $1,
                expiration_date =
                CASE
                    -- Blank (EPOCH) or expired: count from now
                    WHEN expiration_date <= CURRENT_TIMESTAMP
                    THEN CURRENT_TIMESTAMP + make_interval(days => $1)

                    -- Active: extend from current expiry
                    ELSE expiration_date + make_interval(days => $1)
                END
                WHERE client_id = $2;
                ''',
                paid_days, client_id)
            return True


async def get_payment_id_by_external(provider: str, external_id: str) -> int | None:
    """Resolve our ``payments.id`` from ``(provider, external_id)``.

    Used by ``PaymentService.handle_event`` when a webhook arrives carrying
    an opaque provider-side identifier (e.g. a UUID label for YooMoney) and
    we need to map it back to the bot's own payment row.

    Returns ``None`` if no matching payment is found — caller logs and ignores
    the event (it's not ours, or DB state is inconsistent).
    """
    async with acquire() as conn:
        return await conn.fetchval(
            '''
            SELECT id
            FROM payments
            WHERE provider = $1 AND external_id = $2;
            ''',
            provider, external_id)


async def get_payment_provider_info(payment_id: int) -> asyncpg.Record | None:
    """Return ``(provider, external_id, status)`` for ``payment_id``, or ``None``.

    Small lookup used by user-initiated re-check flows that need the provider
    routing info but don't want to pull the entire finalize context.
    """
    async with acquire() as conn:
        return await conn.fetchrow(
            '''
            SELECT provider, external_id, status
            FROM payments
            WHERE id = $1;
            ''',
            payment_id)


async def get_payment_finalize_context(payment_id: int) -> asyncpg.Record | None:
    """Single-query fetch of everything needed to finalize ``payment_id``.

    Returns a row with: ``id``, ``client_id``, ``days_number``, ``status``,
    ``telegram_message_id``, ``telegram_id``. ``None`` if no such payment.
    """
    async with acquire() as conn:
        return await conn.fetchrow(
            '''
            SELECT p.id, p.client_id, p.days_number, p.status, p.telegram_message_id,
                   c.telegram_id
            FROM payments p
            JOIN clients c ON c.id = p.client_id
            WHERE p.id = $1;
            ''',
            payment_id)


async def update_payment_successful(payment_id: int, client_id: int, paid_days: int) -> None:
    """Change status of payment specified by payment_id to successful and change subscription data.

    Writes both legacy ``is_successful`` flag and the new ``status``/``paid_at``/``updated_at``
    columns so legacy and new read paths stay consistent until the legacy column is dropped.

    .. note::
        This function is non-idempotent — calling twice doubles the subscription extension.
        New code paths should use :func:`claim_payment_finalize` instead.
    """
    async with acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                '''
                UPDATE payments
                SET is_successful = TRUE,
                    status        = 'succeeded',
                    paid_at       = CURRENT_TIMESTAMP,
                    updated_at    = CURRENT_TIMESTAMP
                WHERE id = $1;
                ''',
                payment_id)

            await conn.execute(
                '''
                UPDATE clients_subscriptions
                SET paid_days_counter = paid_days_counter + $1,
                expiration_date =
                CASE
                    -- Blank (EPOCH) or expired: count from now
                    WHEN expiration_date <= CURRENT_TIMESTAMP
                    THEN CURRENT_TIMESTAMP + make_interval(days => $1)

                    -- Active: extend from current expiry
                    ELSE expiration_date + make_interval(days => $1)
                END
                WHERE client_id = $2;
                ''',
                paid_days, client_id)


async def update_payment_telegram_message_id(payment_id: int, telegram_message_id: int) -> None:
    """Add telegram message id for payment specified by payment_id."""
    async with acquire() as conn:
        await conn.execute(
            '''
            UPDATE payments
            SET telegram_message_id = $1
            WHERE id = $2;
            ''',
            telegram_message_id, payment_id)


async def update_payment_provider_external(
    payment_id: int, provider: str, external_id: str,
) -> None:
    """Record provider-side external id once the gateway has issued one.

    Called by ``PaymentService.initiate`` after ``provider.create_invoice`` returns.
    ``provider`` is also stored at INSERT time but is harmless to overwrite here.
    """
    async with acquire() as conn:
        await conn.execute(
            '''
            UPDATE payments
            SET provider    = $1,
                external_id = $2,
                updated_at  = CURRENT_TIMESTAMP
            WHERE id = $3;
            ''',
            provider, external_id, payment_id)


async def update_payment_status(
    payment_id: int,
    status: str,
    paid_at: datetime.datetime | None = None,
    raw_payload: dict | list | None = None,
) -> None:
    """Lower-level status update for webhook/reconciler paths.

    Mirrors ``status='succeeded'`` to legacy ``is_successful`` to keep read paths
    consistent. ``paid_at`` and ``raw_payload`` are merged via COALESCE — passing
    ``None`` does not overwrite an existing value.

    ``is_successful`` is bound as a Python bool ($2) instead of being derived in
    SQL as ``($1 = 'succeeded')`` because asyncpg can't unify the type of $1
    used as ``VARCHAR`` (column assignment) and as ``text`` (literal comparison)
    — it raises AmbiguousParameterError. Pre-computing in Python sidesteps the
    type-inference altogether.
    """
    is_successful = (status == 'succeeded')
    raw_payload_json = json.dumps(raw_payload) if raw_payload is not None else None
    async with acquire() as conn:
        await conn.execute(
            '''
            UPDATE payments
            SET status        = $1,
                is_successful = $2,
                paid_at       = COALESCE($3, paid_at),
                raw_payload   = COALESCE($4::jsonb, raw_payload),
                updated_at    = CURRENT_TIMESTAMP
            WHERE id = $5;
            ''',
            status, is_successful, paid_at, raw_payload_json, payment_id)


async def update_payment_fiscal_receipt_url(payment_id: int, fiscal_receipt_url: str) -> None:
    """Persist the «Мой налог» receipt URL for ``payment_id``.

    Called after a successful income registration via :mod:`src.payments.fiscalization`.
    The URL is used both for admin audit (``SELECT … WHERE fiscal_receipt_url IS NULL``
    to find non-registered payments) and to share with the buyer at notification time.
    """
    async with acquire() as conn:
        await conn.execute(
            '''
            UPDATE payments
            SET fiscal_receipt_url = $1,
                updated_at         = CURRENT_TIMESTAMP
            WHERE id = $2;
            ''',
            fiscal_receipt_url, payment_id)


async def get_payment_amount(payment_id: int) -> Decimal | None:
    """Return the ``price`` value for ``payment_id`` (the amount actually charged).

    Used by the fiscalization step in ``finalize_successful_payment`` — needs
    the canonical amount to register with «Мой налог».
    """
    async with acquire() as conn:
        return await conn.fetchval(
            "SELECT price FROM payments WHERE id = $1;",
            payment_id)


async def list_pending_payments_recent(minutes: int = 30) -> list[asyncpg.Record]:
    """Pending payments initiated within the last ``minutes`` — for reconciler.

    Returns rows where ``status='pending'`` AND ``external_id IS NOT NULL`` —
    only payments that have actually been registered with the provider. Newly-
    INSERTed payments without an external_id yet are skipped (they're still in
    flight inside ``PaymentService.initiate``).
    """
    async with acquire() as conn:
        return await conn.fetch(
            '''
            SELECT id, client_id, sub_id, provider, external_id, days_number, price
            FROM payments
            WHERE status = 'pending'
              AND external_id IS NOT NULL
              AND date_of_initiation > NOW() - make_interval(mins => $1)
            ORDER BY date_of_initiation;
            ''',
            minutes)
