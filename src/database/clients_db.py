"""``clients`` table: lookups by telegram_id / client_id and client registration."""
import asyncpg
import datetime

from src.database.connection import acquire
from src.database.subscriptions_db import get_ref_provided_sub_id


async def is_user_registered(telegram_id: int) -> bool | None:
    """Check telegram_id exists in DB."""
    async with acquire() as conn:
        return await conn.fetchval(
            '''
            SELECT TRUE
            FROM clients
            WHERE telegram_id = $1;
            ''',
            telegram_id)


async def get_clientID_by_telegramID(telegram_id: int) -> int | None:
    """Return client_id by specified telegram_id."""
    async with acquire() as conn:
        return await conn.fetchval('''
            SELECT id
            FROM clients
            WHERE telegram_id = $1;
            ''',
            telegram_id)


async def get_telegramID_by_clientID(client_id: str) -> int | None:
    """Return telegram_id by specified client_id."""
    async with acquire() as conn:
        return await conn.fetchval(
            '''
            SELECT telegram_id
            FROM clients
            WHERE id = $1;
            ''',
            client_id)


async def get_telegramID_by_username(username: str) -> int | None:
    """Return telegram_id by specified @username."""
    async with acquire() as conn:
        return await conn.fetchval(
            '''
            SELECT telegram_id
            FROM clients
            WHERE username = $1;
            ''',
            username)


async def get_client_info_by_telegramID(telegram_id: int) -> asyncpg.Record | None:
    """Return information about client by specified telegram_id.

    :param telegram_id:
    :return: asyncgp.Record object having (id, name, surname, username, register_date, used_ref_promo_id)
    :rtype: asyncpg.Record | None
    """
    async with acquire() as conn:
        return await conn.fetchrow(
            '''
            SELECT id, name, surname, username, register_date, used_ref_promo_id
            FROM clients
            WHERE telegram_id = $1;
            ''',
            telegram_id)


async def get_client_info_by_clientID(client_id: int) -> asyncpg.Record | None:
    """Return information about client by specified client_id.

    :param client_id:
    :return: asyncgp.Record object having (name, surname, username, telegram_id, register_date, used_ref_promo_id)
    :rtype: asyncpg.Record | None
    """
    async with acquire() as conn:
        return await conn.fetchrow(
            '''
            SELECT name, surname, username, telegram_id, register_date, used_ref_promo_id
            FROM clients
            WHERE id = $1;
            ''',
            client_id)


async def get_clients_ids() -> list[asyncpg.Record]:
    """Return all clients' ids from DB as list[asyncpg.Record]."""
    async with acquire() as conn:
        return await conn.fetch(
            '''
            SELECT id
            FROM clients;
            ''')


async def get_clients_telegram_ids() -> list[asyncpg.Record]:
    """Return all clients' telegram ids from DB as list[asyncpg.Record]."""
    async with acquire() as conn:
        return await conn.fetch(
            '''
            SELECT telegram_id
            FROM clients;
            ''')


async def insert_client(name: str,
                        telegram_id: int,
                        surname: str | None = None,
                        username: str | None = None,
                        used_ref_promo_id: int | None = None,
                        provided_sub_id: int | None = None,
                        bonus_time: datetime.timedelta | None = None,
                        ) -> int:
    """Add new client to DB. Returns the new client_id."""
    if username:
        username = '@' + username

    if provided_sub_id is None:
        provided_sub_id = 1  # default: Standard subscription

    if bonus_time is None:
        bonus_time = datetime.timedelta()    # zero days

    # Determine what subscription type the new client's OWN referral promo will offer.
    # Defined per-subscription in subscriptions.ref_provided_sub_id — no magic numbers.
    provided_ref_sub_id = await get_ref_provided_sub_id(provided_sub_id)

    async with acquire() as conn:
        async with conn.transaction():
            client_id: int = await conn.fetchval(
                '''
                INSERT INTO clients (name, surname, username, telegram_id, used_ref_promo_id)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id;
                ''',
                name, surname, username, telegram_id, used_ref_promo_id)

            await conn.execute(
                '''
                INSERT INTO clients_subscriptions (client_id, sub_id, expiration_date)
                VALUES ($1, $2, TIMESTAMP 'EPOCH' + $3);
                ''',
                client_id, provided_sub_id, bonus_time)

            await conn.execute(
                '''
                INSERT INTO promocodes_ref (client_creator_id, provided_sub_id)
                VALUES ($1, $2);
                ''',
                client_id, provided_ref_sub_id)

            await conn.execute(
                '''
                INSERT INTO settings (client_id)
                VALUES ($1);
                ''',
                client_id)

    return client_id
