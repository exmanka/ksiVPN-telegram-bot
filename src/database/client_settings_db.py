"""``settings`` table: per-client notification toggles and ChatGPT mode."""
import asyncpg

from src.database.connection import acquire


async def get_chatgpt_mode_status(client_id: int) -> bool | None:
    """Return TRUE if bot is answering unrecognized messages in ChatGPT mode else FALSE."""
    async with acquire() as conn:
        return await conn.fetchval(
            '''
            SELECT chatgpt_mode
            FROM settings
            WHERE client_id = $1;
            ''',
            client_id)


async def get_settings_info(client_id: int) -> asyncpg.Record | None:
    """Return information about client's setting where TRUE means TURNED ON and FALSE means TURNED OFF.

    :param client_id:
    :return: asyncgp.Record object having (sub_expiration_in_1d, sub_expiration_in_3d, sub_expiration_in_7d, chatgpt_mode)
    :rtype: asyncpg.Record | None
    """
    async with acquire() as conn:
        return await conn.fetchrow(
            '''
            SELECT sub_expiration_in_1d, sub_expiration_in_3d, sub_expiration_in_7d, chatgpt_mode
            FROM settings
            WHERE client_id = $1;
            ''',
            client_id)


async def update_chatgpt_mode(client_id: int) -> bool | None:
    """Turn on/off ChatGPT bot mode in DB of client with specified telegram_id."""
    async with acquire() as conn:
        return await conn.fetchval(
            '''
            UPDATE settings
            SET chatgpt_mode = NOT chatgpt_mode
            WHERE client_id = $1
            RETURNING chatgpt_mode;
            ''',
            client_id)


async def update_notifications_1d(client_id: int) -> bool | None:
    """Change client's settings for sending notification one day before subscription expires where TRUE is send notification
    and FALSE is not send notification, return current settings."""
    async with acquire() as conn:
        return await conn.fetchval(
            '''
            UPDATE settings
            SET sub_expiration_in_1d = NOT sub_expiration_in_1d
            WHERE client_id = $1
            RETURNING sub_expiration_in_1d;
            ''',
            client_id)


async def update_notifications_3d(client_id: int) -> bool | None:
    """Change client's settings for sending notification three days before subscription expires where TRUE is send notification
    and FALSE is not send notification, return current settings."""
    async with acquire() as conn:
        return await conn.fetchval(
            '''
            UPDATE settings
            SET sub_expiration_in_3d = NOT sub_expiration_in_3d
            WHERE client_id = $1
            RETURNING sub_expiration_in_3d;
            ''',
            client_id)


async def update_notifications_7d(client_id: int) -> bool | None:
    """Change client's settings for sending notification seven day before subscription expires where TRUE is send notification
    and FALSE is not send notification, return current settings."""
    async with acquire() as conn:
        return await conn.fetchval(
            '''
            UPDATE settings
            SET sub_expiration_in_7d = NOT sub_expiration_in_7d
            WHERE client_id = $1
            RETURNING sub_expiration_in_7d;
            ''',
            client_id)
