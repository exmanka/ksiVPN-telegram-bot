"""``subscription_events``: consumer side of the trigger-owned expiration schedule."""
import asyncpg

from src.database.connection import acquire


SUBSCRIPTION_EVENTS_CHANNEL = 'subscription_events'


async def get_next_subscription_event_delay() -> float | None:
    """Return seconds until the nearest pending subscription event, or None if there is none.

    Computed against the database clock, so container clock skew doesn't matter.
    Negative when an event is already due.
    """
    async with acquire() as conn:
        return await conn.fetchval(
            '''
            SELECT EXTRACT(EPOCH FROM MIN(fire_at) - CURRENT_TIMESTAMP)::float8
            FROM subscription_events
            WHERE done_at IS NULL;
            ''')


async def fetch_due_subscription_events(limit: int = 100) -> list[asyncpg.Record]:
    """Return pending subscription events whose fire_at has come, oldest first.

    :return: asyncpg.Record objects having (id, client_id, kind, fire_at, for_expiration, attempts,
        expiration_date, telegram_id, name, surname, username, sub_expiration_in_1d,
        sub_expiration_in_3d, sub_expiration_in_7d, price, remnawave_subscription_url)
    """
    async with acquire() as conn:
        return await conn.fetch(
            '''
            SELECT se.id, se.client_id, se.kind, se.fire_at, se.for_expiration, se.attempts,
                   cs.expiration_date,
                   c.telegram_id, c.name, c.surname, c.username,
                   s.sub_expiration_in_1d, s.sub_expiration_in_3d, s.sub_expiration_in_7d,
                   sub.price,
                   cr.remnawave_subscription_url
            FROM subscription_events AS se
            JOIN clients AS c ON c.id = se.client_id
            JOIN clients_subscriptions AS cs ON cs.client_id = se.client_id
            JOIN subscriptions AS sub ON sub.id = cs.sub_id
            LEFT JOIN settings AS s ON s.client_id = se.client_id
            LEFT JOIN clients_remnawave AS cr ON cr.client_id = se.client_id
            WHERE se.done_at IS NULL
              AND se.fire_at <= CURRENT_TIMESTAMP
            ORDER BY se.fire_at, se.id
            LIMIT $1;
            ''',
            limit)


async def claim_subscription_event(event_id: int) -> bool:
    """Mark a subscription event processed. Returns True exactly once per event."""
    async with acquire() as conn:
        claimed_id = await conn.fetchval(
            '''
            UPDATE subscription_events
            SET done_at = CURRENT_TIMESTAMP
            WHERE id = $1 AND done_at IS NULL
            RETURNING id;
            ''',
            event_id)
        return claimed_id is not None


async def postpone_subscription_event(event_id: int, seconds: int) -> None:
    """Move a pending event's fire_at forward and count the attempt (its handler failed, retry later)."""
    async with acquire() as conn:
        await conn.execute(
            '''
            UPDATE subscription_events
            SET fire_at = CURRENT_TIMESTAMP + make_interval(secs => $2),
                attempts = attempts + 1
            WHERE id = $1 AND done_at IS NULL;
            ''',
            event_id, seconds)


async def purge_done_subscription_events(days: int = 90) -> int:
    """Delete processed subscription events older than ``days``. Returns the number of deleted rows."""
    async with acquire() as conn:
        status = await conn.execute(
            '''
            DELETE FROM subscription_events
            WHERE done_at IS NOT NULL
              AND done_at < CURRENT_TIMESTAMP - make_interval(days => $1);
            ''',
            days)
        return int(status.split()[-1])
