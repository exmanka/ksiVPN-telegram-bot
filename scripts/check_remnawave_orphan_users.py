"""Поиск пользователей в Remnawave Panel, которых нет в БД бота.

Скрипт загружает всех пользователей из панели (с пагинацией) и проверяет,
есть ли их UUID в таблице `clients_remnawave`. Пользователи без записи в БД
считаются «сиротами» (orphans).

Требования
----------
  Python 3.12 (.venv-3.12):
      .venv-3.12/bin/pip install asyncpg remnawave

Переменные окружения (БД):
    POSTGRES_HOST     — хост БД (по умолчанию 'ksivpn-tgbot-postgres')
    POSTGRES_PORT     — порт БД (по умолчанию 5432)
    POSTGRES_DB       — имя БД
    POSTGRES_USER
    POSTGRES_PASSWORD

Переменные окружения (Remnawave):
    REMNAWAVE_BASE_URL
    REMNAWAVE_TOKEN
    REMNAWAVE_CADDY_TOKEN  — необязательно

Использование:
    .venv-3.12/bin/python scripts/check_remnawave_orphan_users.py
    .venv-3.12/bin/python scripts/check_remnawave_orphan_users.py --page-size 200
"""
import argparse
import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone

import asyncpg
from remnawave import RemnawaveSDK
from remnawave.models import UserResponseDto


logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger('check_remnawave_orphan_users')

# ---------------------------------------------------------------------------
# Config from env
# ---------------------------------------------------------------------------

POSTGRES_HOST = os.getenv('POSTGRES_HOST', 'ksivpn-tgbot-postgres')
POSTGRES_PORT = int(os.getenv('POSTGRES_PORT', '5432'))
POSTGRES_DB = os.getenv('POSTGRES_DB', '')
POSTGRES_USER = os.getenv('POSTGRES_USER', '')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD', '')

REMNAWAVE_BASE_URL = os.getenv('REMNAWAVE_BASE_URL', '')
REMNAWAVE_TOKEN = os.getenv('REMNAWAVE_TOKEN', '')
REMNAWAVE_CADDY_TOKEN = os.getenv('REMNAWAVE_CADDY_TOKEN')

DEFAULT_PAGE_SIZE = 100


def _build_sdk() -> RemnawaveSDK:
    if not REMNAWAVE_BASE_URL:
        raise SystemExit("REMNAWAVE_BASE_URL is not set")
    if not REMNAWAVE_TOKEN:
        raise SystemExit("REMNAWAVE_TOKEN is not set")
    kwargs: dict = {"base_url": REMNAWAVE_BASE_URL, "token": REMNAWAVE_TOKEN}
    if REMNAWAVE_CADDY_TOKEN:
        kwargs["caddy_token"] = REMNAWAVE_CADDY_TOKEN
    return RemnawaveSDK(**kwargs)


# ---------------------------------------------------------------------------
# Panel helpers
# ---------------------------------------------------------------------------

async def _fetch_all_panel_users(sdk: RemnawaveSDK,
                                 page_size: int) -> list[UserResponseDto]:
    """Fetch all users from the panel using offset pagination."""
    all_users: list[UserResponseDto] = []
    start = 0

    while True:
        response = await sdk.users.get_all_users(start=start, size=page_size)
        all_users.extend(response.users)
        logger.debug("Fetched %d/%d panel users", len(all_users), response.total)

        if len(all_users) >= response.total:
            break
        start += page_size

    return all_users


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

async def _get_known_uuids(conn: asyncpg.Connection) -> set[uuid.UUID]:
    """Return the set of remnawave_uuid values stored in clients_remnawave."""
    rows = await conn.fetch('SELECT remnawave_uuid FROM clients_remnawave;')
    return {row['remnawave_uuid'] for row in rows}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main(page_size: int) -> None:
    for req_var, name in [(POSTGRES_DB, 'POSTGRES_DB'),
                          (POSTGRES_USER, 'POSTGRES_USER'),
                          (POSTGRES_PASSWORD, 'POSTGRES_PASSWORD')]:
        if not req_var:
            raise SystemExit(f"{name} is not set")

    sdk = _build_sdk()

    pool = await asyncpg.create_pool(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        database=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        min_size=1,
        max_size=2,
    )

    try:
        logger.info("Fetching panel users...")
        panel_users = await _fetch_all_panel_users(sdk, page_size)
        logger.info("Total panel users: %d", len(panel_users))

        async with pool.acquire() as conn:
            known_uuids = await _get_known_uuids(conn)
        logger.info("Total bot DB records (clients_remnawave): %d", len(known_uuids))

        orphans = [u for u in panel_users if u.uuid not in known_uuids]

        if not orphans:
            logger.info("No orphan users found — panel and bot DB are in sync.")
            return

        logger.warning("Found %d orphan panel user(s):", len(orphans))
        now = datetime.now(timezone.utc)
        for u in orphans:
            expire_at = u.expire_at.astimezone(timezone.utc)
            status_str = u.status.value if hasattr(u.status, 'value') else str(u.status)
            expired_str = "  [EXPIRED]" if expire_at < now else ""
            logger.warning(
                "  uuid=%-36s  tg_id=%-12s  username=%-24s  expire=%s  status=%s%s",
                u.uuid,
                u.telegram_id if u.telegram_id else "—",
                u.username,
                expire_at.strftime('%Y-%m-%d %H:%M:%S'),
                status_str,
                expired_str,
            )

        logger.info(
            "Summary: panel_total=%d  bot_db_known=%d  orphans=%d",
            len(panel_users), len(known_uuids), len(orphans),
        )

    finally:
        await pool.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Find Remnawave Panel users not present in the bot DB.')
    parser.add_argument(
        '--page-size', type=int, default=DEFAULT_PAGE_SIZE,
        metavar='N',
        help=f'Users per API page (default: {DEFAULT_PAGE_SIZE})',
    )
    args = parser.parse_args()
    asyncio.run(main(page_size=args.page_size))
