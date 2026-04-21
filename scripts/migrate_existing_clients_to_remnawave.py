"""One-off / maintenance script: migrate existing bot clients to Remnawave Panel.

Назначение
----------
Для каждого клиента в таблице `clients`, у которого ещё нет записи в
`clients_remnawave`, создаёт пользователя в Remnawave Panel через API и
записывает результат в БД.

По умолчанию — dry-run: изменения не применяются, только выводится отчёт.
Ключ --apply записывает изменения.

Идемпотентность
---------------
Повторный запуск с --apply безопасен: клиенты с уже существующей записью в
`clients_remnawave` пропускаются (LEFT JOIN c WHERE cr.client_id IS NULL).

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
    REMNAWAVE_BASE_URL   — корневой URL панели (https://panel.example.com)
    REMNAWAVE_TOKEN      — API Bearer-токен (панель → API Tokens)
    REMNAWAVE_CADDY_TOKEN — необязательно, если панель за Caddy с токен-авторизацией

Использование:
    # Dry-run (посмотреть что изменится):
    .venv-3.12/bin/python scripts/migrate_existing_clients_to_remnawave.py

    # Применить изменения:
    .venv-3.12/bin/python scripts/migrate_existing_clients_to_remnawave.py --apply
"""
import argparse
import asyncio
import logging
import os
import re
import uuid
from datetime import datetime, timezone

import asyncpg
from remnawave import RemnawaveSDK
from remnawave.models import CreateUserRequestDto


logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger('migrate_existing_clients')

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

_USERNAME_RE = re.compile(r'^[a-zA-Z0-9_-]{3,36}$')


def _build_sdk() -> RemnawaveSDK:
    if not REMNAWAVE_BASE_URL:
        raise SystemExit("REMNAWAVE_BASE_URL is not set")
    if not REMNAWAVE_TOKEN:
        raise SystemExit("REMNAWAVE_TOKEN is not set")
    kwargs: dict = {"base_url": REMNAWAVE_BASE_URL, "token": REMNAWAVE_TOKEN}
    if REMNAWAVE_CADDY_TOKEN:
        kwargs["caddy_token"] = REMNAWAVE_CADDY_TOKEN
    return RemnawaveSDK(**kwargs)


def _sanitize_username(telegram_id: int, tg_username: str | None) -> str:
    if tg_username and _USERNAME_RE.match(tg_username.lstrip('@')):
        return tg_username.lstrip('@')
    return f"tg_{telegram_id}"


def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# ---------------------------------------------------------------------------
# DB helpers (standalone, no src imports)
# ---------------------------------------------------------------------------

async def _get_clients_without_remnawave(conn: asyncpg.Connection) -> list[asyncpg.Record]:
    """Return clients that have a subscription but no remnawave record."""
    return await conn.fetch(
        '''
        SELECT c.id AS client_id,
               c.telegram_id,
               c.username,
               cs.expiration_date
        FROM clients c
        JOIN clients_subscriptions cs ON cs.client_id = c.id
        LEFT JOIN clients_remnawave cr ON cr.client_id = c.id
        WHERE cr.client_id IS NULL
        ORDER BY c.id;
        ''')


async def _get_random_active_squad(conn: asyncpg.Connection) -> uuid.UUID | None:
    row = await conn.fetchrow(
        'SELECT squad_uuid FROM remnawave_internal_squads WHERE is_active = TRUE ORDER BY RANDOM() LIMIT 1;')
    return row['squad_uuid'] if row else None


async def _insert_client_remnawave(conn: asyncpg.Connection,
                                   client_id: int,
                                   remnawave_uuid: uuid.UUID,
                                   subscription_url: str) -> None:
    await conn.execute(
        '''
        INSERT INTO clients_remnawave (client_id, remnawave_uuid, remnawave_subscription_url)
        VALUES ($1, $2, $3)
        ON CONFLICT DO NOTHING;
        ''',
        client_id, remnawave_uuid, subscription_url)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main(apply: bool) -> None:
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
        async with pool.acquire() as conn:
            clients = await _get_clients_without_remnawave(conn)
            logger.info("Found %d client(s) without Remnawave record", len(clients))

            if not apply:
                for row in clients:
                    logger.info("  client_id=%s  telegram_id=%s  username=%s  expiry=%s",
                                row['client_id'], row['telegram_id'],
                                row['username'], row['expiration_date'])
                logger.info("Dry-run mode — no changes written. Re-run with --apply to apply.")
                return

            processed = migrated = skipped = failed = 0
            for row in clients:
                processed += 1
                client_id = row['client_id']
                telegram_id = row['telegram_id']
                username = row['username']
                expiration_date = row['expiration_date']

                try:
                    squad_uuid = await _get_random_active_squad(conn)
                    if squad_uuid is None:
                        logger.warning("No active squads — creating client_id=%s without squad", client_id)

                    dto = CreateUserRequestDto(
                        username=_sanitize_username(telegram_id, username),
                        expire_at=_to_utc(expiration_date),
                        telegram_id=telegram_id,
                        active_internal_squads=[squad_uuid] if squad_uuid else None,
                    )
                    response = await sdk.users.create_user(dto)
                    await _insert_client_remnawave(conn, client_id, response.uuid, response.subscription_url)
                    migrated += 1
                    logger.info("Migrated client_id=%s → remnawave_uuid=%s", client_id, response.uuid)

                except Exception as exc:
                    failed += 1
                    logger.error("FAILED client_id=%s telegram_id=%s: %s", client_id, telegram_id, exc)

            logger.info(
                "Done: processed=%d  migrated=%d  skipped=%d  failed=%d",
                processed, migrated, skipped, failed,
            )
    finally:
        await pool.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Migrate existing bot clients to Remnawave Panel.')
    parser.add_argument('--apply', action='store_true',
                        help='Write changes to the database and panel (default: dry-run)')
    args = parser.parse_args()
    asyncio.run(main(apply=args.apply))
