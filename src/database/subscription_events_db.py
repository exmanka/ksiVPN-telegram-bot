"""``subscription_events``: consumer side of the trigger-owned expiration and «first connection» schedule."""
import asyncpg

from src.database.connection import acquire


SUBSCRIPTION_EVENTS_CHANNEL = 'subscription_events'
# «First connection» reminder; its rows are never deleted (they mark a client as already handled).
FIRST_CONNECT_KIND = 'first_connect'


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
        expiration_date, subscription_active, telegram_id, name, surname, username, sub_expiration_in_1d,
        sub_expiration_in_3d, sub_expiration_in_7d, price, remnawave_uuid, remnawave_subscription_url)
    """
    async with acquire() as conn:
        return await conn.fetch(
            '''
            SELECT se.id, se.client_id, se.kind, se.fire_at, se.for_expiration, se.attempts,
                   cs.expiration_date,
                   (cs.expiration_date > CURRENT_TIMESTAMP) AS subscription_active,
                   c.telegram_id, c.name, c.surname, c.username,
                   s.sub_expiration_in_1d, s.sub_expiration_in_3d, s.sub_expiration_in_7d,
                   sub.price,
                   cr.remnawave_uuid, cr.remnawave_subscription_url
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


async def delete_pending_subscription_event(event_id: int) -> bool:
    """Delete a still unprocessed event. Returns True if it was deleted.

    Used for a «first connection» reminder whose subscription is no longer active: once all
    of a client's ``first_connect`` rows are gone, the next activation schedules a fresh set.
    """
    async with acquire() as conn:
        deleted_id = await conn.fetchval(
            '''
            DELETE FROM subscription_events
            WHERE id = $1 AND done_at IS NULL
            RETURNING id;
            ''',
            event_id)
        return deleted_id is not None


async def set_first_connect_delays(minutes: list[int]) -> None:
    """Store the «first connection» reminder delays read by the scheduling trigger.

    Applies to activations from now on; already scheduled reminders keep their ``fire_at``.
    An empty list disables scheduling of new reminders.
    """
    async with acquire() as conn:
        await conn.execute(
            '''
            UPDATE subscription_events_settings
            SET first_connect_delays = ARRAY(
                SELECT make_interval(mins => m) FROM unnest($1::int[]) AS m
            );
            ''',
            minutes)


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
    """Delete processed subscription events older than ``days``. Returns the number of deleted rows.

    ``first_connect`` rows are kept forever: they mark a client whose reminders were already scheduled.
    """
    async with acquire() as conn:
        status = await conn.execute(
            '''
            DELETE FROM subscription_events
            WHERE done_at IS NOT NULL
              AND kind <> $2
              AND done_at < CURRENT_TIMESTAMP - make_interval(days => $1);
            ''',
            days, FIRST_CONNECT_KIND)
        return int(status.split()[-1])
