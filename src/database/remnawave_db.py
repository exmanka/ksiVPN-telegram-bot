"""``clients_remnawave`` and ``remnawave_internal_squads``: panel provisioning state."""
import asyncpg
import uuid

from src.database.connection import acquire


# ---------------------------------------------------------------------------
# Remnawave — clients_remnawave helpers
# ---------------------------------------------------------------------------

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


async def has_remnawave_record(client_id: int) -> bool:
    """Return True if client already has a Remnawave panel record."""
    async with acquire() as conn:
        return bool(await conn.fetchval(
            '''
            SELECT EXISTS(
                SELECT 1 FROM clients_remnawave WHERE client_id = $1
            );
            ''',
            client_id))


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


async def get_clients_without_remnawave_record() -> list[asyncpg.Record]:
    """Return all clients that have no Remnawave panel record yet (for migration script)."""
    async with acquire() as conn:
        return await conn.fetch(
            '''
            SELECT c.id, c.telegram_id, c.username, cs.expiration_date
            FROM clients AS c
            JOIN clients_subscriptions AS cs ON cs.client_id = c.id
            LEFT JOIN clients_remnawave AS cr ON cr.client_id = c.id
            WHERE cr.client_id IS NULL;
            ''')


# ---------------------------------------------------------------------------
# Remnawave — remnawave_internal_squads helpers
# ---------------------------------------------------------------------------

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
