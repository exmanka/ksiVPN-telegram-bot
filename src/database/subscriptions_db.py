"""``subscriptions`` / ``clients_subscriptions``: subscription types, state and expiration date."""
import asyncpg
import datetime

from src.database.connection import acquire


async def is_subscription_active(telegram_id: int) -> bool | None:
    """Check subcription's expiration date of client with specified telegram_id. Return TRUE if acive, None if inactive."""
    async with acquire() as conn:
        return await conn.fetchval(
            '''
            SELECT TRUE
            FROM clients_subscriptions AS cs
            JOIN clients AS c
            ON cs.client_id = c.id
            WHERE c.telegram_id = $1
            AND cs.expiration_date > NOW();
            ''',
            telegram_id)


async def is_subscription_not_started(telegram_id: int) -> bool | None:
    """Check admin hasn't send first client's configuration to activate subscription.

    Actually check subscription's expiration date before 1980 year (peculiarity of implementation of database architecture).
    """
    async with acquire() as conn:
        return await conn.fetchval(
            '''
            SELECT TRUE
            FROM clients_subscriptions AS cs
            JOIN clients AS c
            ON cs.client_id = c.id
            WHERE c.telegram_id = $1
            AND cs.expiration_date < TIMESTAMP 'EPOCH' + INTERVAL '10 years';
            ''',
            telegram_id)


async def is_subscription_blank(telegram_id: int) -> bool | None:
    """Check subscription was never paid or renewed.
    
    Actually check subscription's expiration date is 'EPOCH' = 1970-01-01 00:00 (peculiarity of implementation of database architecture)."""
    async with acquire() as conn:
        return await conn.fetchval(
            '''
            SELECT TRUE
            FROM clients_subscriptions AS cs
            JOIN clients AS c
            ON cs.client_id = c.id
            WHERE c.telegram_id = $1
            AND cs.expiration_date = TIMESTAMP 'EPOCH';
            ''',
            telegram_id)


async def is_subscription_free(telegram_id: int) -> bool | None:
    """Check client has free subscription."""
    async with acquire() as conn:
        return await conn.fetchval(
            '''
            SELECT
            CASE
                WHEN sub.price = 0 THEN TRUE
                ELSE FALSE
            END
            FROM subscriptions AS sub
            JOIN clients_subscriptions AS cs
            ON sub.id = cs.sub_id
            JOIN clients AS c
            ON cs.client_id = c.id
            WHERE c.telegram_id = $1;
            ''',
            telegram_id)


async def get_subscription_info_by_clientID(client_id: int) -> asyncpg.Record | None:
    """Return information about subscription of client specified by client_id.

    :param client_id:
    :return: asyncgp.Record object having (sub_id, title, description, price)
    :rtype: asyncpg.Record | None
    """
    async with acquire() as conn:
        return await conn.fetchrow(
            '''
            SELECT sub.id, sub.title, sub.description, sub.price
            FROM clients_subscriptions AS clients_sub
            JOIN subscriptions AS sub
            ON sub.id = clients_sub.sub_id
            WHERE clients_sub.client_id = $1;
            ''',
            client_id)


async def get_clients_subscriptions_info_by_clientID(client_id: int) -> asyncpg.Record | None:
    """Return information about subscription's expiration date of client specified by client_id.

    :param client_id:
    :return: asyncgp.Record object having (sub_id, paid_days_counter, expiration_date)
    :rtype: asyncpg.Record | None
    """
    async with acquire() as conn:
        return await conn.fetchrow(
            '''
            SELECT sub_id, paid_days_counter, expiration_date
            FROM clients_subscriptions
            WHERE client_id = $1;
            ''',
            client_id)


async def get_subscription_info_by_subID(subscription_id: int) -> asyncpg.Record | None:
    """Return information about subscription specified by sub_id.

    :param subscription_id:
    :return: asyncgp.Record object having (id, title, description, price)
    :rtype: asyncpg.Record | None
    """
    async with acquire() as conn:
        return await conn.fetchrow(
            '''
            SELECT id, title, description, price
            FROM subscriptions
            WHERE id = $1;
            ''',
            subscription_id)


async def get_ref_provided_sub_id(sub_id: int) -> int:
    """Return the subscription type that invitees receive when a user with sub_id uses their ref promo.

    Reads subscriptions.ref_provided_sub_id — the value is defined per-row in the DB,
    so adding new subscription types never requires code changes.
    Falls back to 1 (Standard) if the row is missing (should not happen under FK constraints).
    """
    async with acquire() as conn:
        result = await conn.fetchval(
            'SELECT ref_provided_sub_id FROM subscriptions WHERE id = $1;',
            sub_id)
    return result if result is not None else 1


async def get_subscription_expiration_date(telegram_id: int) -> datetime.datetime | None:
    """Return subscription's expiration date as a raw timestamp.

    Use :func:`src.services.date_formatting.format_localized_datetime` at the
    call site to render it in the bot's configured language.
    """
    async with acquire() as conn:
        return await conn.fetchval(
            '''
            SELECT cs.expiration_date
            FROM clients_subscriptions AS cs
            JOIN clients AS c
            ON cs.client_id = c.id
            WHERE c.telegram_id = $1;
            ''',
            telegram_id)


async def get_max_configurations_by_telegramID(telegram_id: int) -> int | None:
    """Return max configurations allowed by the client's subscription."""
    async with acquire() as conn:
        return await conn.fetchval(
            '''
            SELECT s.max_configurations
            FROM subscriptions AS s
            JOIN clients_subscriptions AS cs ON s.id = cs.sub_id
            JOIN clients AS c ON cs.client_id = c.id
            WHERE c.telegram_id = $1;
            ''',
            telegram_id)


async def activate_client_bonus_time(client_id: int) -> None:
    """Convert EPOCH-based pending bonus to NOW()-based active expiry.

    insert_client stores expiration_date as EPOCH + bonus_time when a referral promo
    is used. This function activates the bonus by rewriting it as NOW() + bonus_time.
    Safe to call only when bonus_time > 0; the 10-year guard prevents touching
    subscriptions that have already been activated or paid.
    """
    async with acquire() as conn:
        await conn.execute(
            '''
            UPDATE clients_subscriptions
            SET expiration_date = NOW() + (expiration_date - TIMESTAMP 'EPOCH')
            WHERE client_id = $1
              AND expiration_date < TIMESTAMP 'EPOCH' + INTERVAL '10 years';
            ''',
            client_id)


async def update_client_subscription(client_id: int, new_sub_id: int) -> None:
    """Change client's subscription type."""
    async with acquire() as conn:
        await conn.execute(
            '''
            UPDATE clients_subscriptions
            SET sub_id = $1
            WHERE client_id = $2
            ''',
            new_sub_id, client_id)


async def add_subscription_period(client_id: int, days: int) -> None:
    """Add interval for subscription expiration date.

    For blank (EPOCH) or already expired subscriptions counts from CURRENT_TIMESTAMP,
    so the bonus is never added to a date in the past.
    """
    async with acquire() as conn:
        await conn.execute(
            '''
            UPDATE clients_subscriptions
            SET expiration_date = CASE
                WHEN expiration_date <= CURRENT_TIMESTAMP
                THEN CURRENT_TIMESTAMP + make_interval(days => $1)
                ELSE expiration_date + make_interval(days => $1)
            END
            WHERE client_id = $2;
            ''',
            days, client_id)


async def get_subscription_expiration_date_by_clientID(client_id: int) -> datetime.datetime | None:
    """Return subscription's expiration date by client_id."""
    async with acquire() as conn:
        return await conn.fetchval(
            '''
            SELECT expiration_date
            FROM clients_subscriptions
            WHERE client_id = $1;
            ''',
            client_id)
