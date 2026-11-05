"""``clients_remnawave`` and ``remnawave_internal_squads``: panel provisioning state."""
import datetime
import uuid

import asyncpg

from src.database.connection import acquire


async def insert_client_remnawave(client_id: int,
                                  remnawave_uuid: uuid.UUID,
                                  subscription_url: str) -> None:
    """Insert Remnawave panel record for a newly registered client."""
    async with acquire() as conn:
        await conn.execute(
            '''
            INSERT INTO clients_remnawave (client_id, remnawave_uuid, remnawave_subscription_url)
            VALUES ($1, $2, $3);
            ''',
            client_id, remnawave_uuid, subscription_url)


async def update_client_remnawave_subscription_url(remnawave_uuid: uuid.UUID,
                                                   subscription_url: str) -> bool:
    """Update the cached subscription_url (e.g. after subscription revoke).

    Return False when no client is linked to remnawave_uuid (panel user not registered through the bot).
    """
    async with acquire() as conn:
        return await conn.fetchval(
            '''
            UPDATE clients_remnawave
            SET remnawave_subscription_url = $2, updated_at = NOW()
            WHERE remnawave_uuid = $1
            RETURNING client_id;
            ''',
            remnawave_uuid, subscription_url) is not None


async def get_client_remnawave_uuid_by_clientID(client_id: int) -> uuid.UUID | None:
    """Return remnawave_uuid for client_id, or None if not provisioned."""
    async with acquire() as conn:
        return await conn.fetchval(
            '''
            SELECT remnawave_uuid FROM clients_remnawave WHERE client_id = $1;
            ''',
            client_id)


async def get_client_remnawave_uuid_by_telegramID(telegram_id: int) -> uuid.UUID | None:
    """Return remnawave_uuid for telegram_id, or None if not provisioned."""
    async with acquire() as conn:
        return await conn.fetchval(
            '''
            SELECT cr.remnawave_uuid
            FROM clients_remnawave AS cr
            JOIN clients AS c ON cr.client_id = c.id
            WHERE c.telegram_id = $1;
            ''',
            telegram_id)


async def get_client_remnawave_subscription_url_by_telegramID(telegram_id: int) -> str | None:
    """Return remnawave_subscription_url for telegram_id, or None if not provisioned."""
    async with acquire() as conn:
        return await conn.fetchval(
            '''
            SELECT cr.remnawave_subscription_url
            FROM clients_remnawave AS cr
            JOIN clients AS c ON cr.client_id = c.id
            WHERE c.telegram_id = $1;
            ''',
            telegram_id)


# ---------------------------------------------------------------------------
# Remnawave — «Telegram-only» grace period state (clients_remnawave.grace_*)
# ---------------------------------------------------------------------------

async def get_client_panel_state(client_id: int) -> asyncpg.Record | None:
    """Return everything needed to sync a client to the panel, or None if not provisioned.

    :return: asyncpg.Record having (remnawave_uuid, expiration_date, price, grace_started_at,
        pre_grace_internal_squads, pre_grace_external_squad_uuid, now). ``now`` is the DB clock
        (LOCALTIMESTAMP), the same one the subscription_events trigger compares against.
    """
    async with acquire() as conn:
        return await conn.fetchrow(
            '''
            SELECT cr.remnawave_uuid, cs.expiration_date, sub.price,
                   cr.grace_started_at, cr.pre_grace_internal_squads, cr.pre_grace_external_squad_uuid,
                   LOCALTIMESTAMP AS now
            FROM clients_remnawave AS cr
            JOIN clients_subscriptions AS cs ON cs.client_id = cr.client_id
            JOIN subscriptions AS sub ON sub.id = cs.sub_id
            WHERE cr.client_id = $1;
            ''',
            client_id)


async def start_client_grace(client_id: int,
                             pre_grace_internal_squads: list[uuid.UUID] | None,
                             pre_grace_external_squad_uuid: uuid.UUID | None) -> bool:
    """Mark the client as being in grace and remember the panel squads it had before.

    Never overwrites an already started grace (the captured state must stay the pre-grace one).
    Returns True if this call started the grace period.
    """
    async with acquire() as conn:
        return await conn.fetchval(
            '''
            UPDATE clients_remnawave
            SET grace_started_at = LOCALTIMESTAMP,
                pre_grace_internal_squads = $2,
                pre_grace_external_squad_uuid = $3,
                updated_at = NOW()
            WHERE client_id = $1 AND grace_started_at IS NULL
            RETURNING client_id;
            ''',
            client_id, pre_grace_internal_squads, pre_grace_external_squad_uuid) is not None


async def clear_client_grace(client_id: int) -> None:
    """Forget the grace state after the pre-grace squads were restored in the panel."""
    async with acquire() as conn:
        await conn.execute(
            '''
            UPDATE clients_remnawave
            SET grace_started_at = NULL,
                pre_grace_internal_squads = NULL,
                pre_grace_external_squad_uuid = NULL,
                updated_at = NOW()
            WHERE client_id = $1;
            ''',
            client_id)


async def get_client_grace_started_at_by_telegramID(telegram_id: int) -> datetime.datetime | None:
    """Return when the client's current grace period started, or None if not in grace."""
    async with acquire() as conn:
        return await conn.fetchval(
            '''
            SELECT cr.grace_started_at
            FROM clients_remnawave AS cr
            JOIN clients AS c ON cr.client_id = c.id
            WHERE c.telegram_id = $1;
            ''',
            telegram_id)


async def get_random_active_remnawave_squad_uuid() -> uuid.UUID | None:
    """Return a random squad UUID eligible for assignment to a new user.

    Filters by both is_active (squad exists in panel) and is_assignable
    (squad is not a test/admin-only squad).
    """
    async with acquire() as conn:
        return await conn.fetchval(
            '''
            SELECT squad_uuid
            FROM remnawave_internal_squads
            WHERE is_active = TRUE
              AND is_assignable = TRUE
            ORDER BY RANDOM()
            LIMIT 1;
            ''')
