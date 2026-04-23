"""One-off / maintenance script: migrate existing bot clients to Remnawave Panel.

Назначение
----------
Для каждого клиента в таблице `clients`, у которого ещё нет записи в
`clients_remnawave`, скрипт:

1. Проверяет, существует ли уже пользователь в Remnawave Panel по telegram_id.
   - Если существует — привязывает UUID / subscription_url / created_at из панели
     к таблице `clients_remnawave` и синхронизирует expire_at из БД бота → панель.
   - Если не существует — создаёт нового пользователя в панели (стандартный поток).

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
    # Dry-run (посмотреть что изменится, с запросами к панели для категоризации):
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
from zoneinfo import ZoneInfo

import asyncpg
from remnawave import RemnawaveSDK
from remnawave.exceptions import ApiError as RemnawaveApiError
from remnawave.models import (
    CreateUserRequestDto,
    TelegramUserResponseDto,
    UpdateUserRequestDto,
    UserResponseDto,
)


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

# Timezone in which the bot DB stores naive datetimes.
# Must match TGBOT_TZ / TZ set in docker-compose / .env.
BOT_TZ = ZoneInfo(os.getenv('BOT_TZ', 'Europe/Moscow'))

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
    """Convert naive datetime (stored in BOT_TZ) to UTC-aware datetime."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=BOT_TZ).astimezone(timezone.utc)
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
                                   subscription_url: str,
                                   created_at: datetime | None = None) -> None:
    if created_at is not None:
        # TIMESTAMP WITHOUT TIME ZONE column requires a naive datetime.
        # Convert to UTC then strip tzinfo so asyncpg doesn't try to subtract timezones.
        created_at_naive = (
            created_at.astimezone(timezone.utc).replace(tzinfo=None)
            if created_at.tzinfo is not None
            else created_at
        )
        await conn.execute(
            '''
            INSERT INTO clients_remnawave
                (client_id, remnawave_uuid, remnawave_subscription_url, created_at)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT DO NOTHING;
            ''',
            client_id, remnawave_uuid, subscription_url, created_at_naive)
    else:
        await conn.execute(
            '''
            INSERT INTO clients_remnawave (client_id, remnawave_uuid, remnawave_subscription_url)
            VALUES ($1, $2, $3)
            ON CONFLICT DO NOTHING;
            ''',
            client_id, remnawave_uuid, subscription_url)


# ---------------------------------------------------------------------------
# Panel helpers
# ---------------------------------------------------------------------------

async def _find_panel_user_by_telegram_id(sdk: RemnawaveSDK,
                                          telegram_id: int) -> UserResponseDto | None:
    """Return the first panel user matching telegram_id, or None if not found."""
    result: TelegramUserResponseDto = await sdk.users.get_users_by_telegram_id(str(telegram_id))
    return result[0] if result else None


async def _update_panel_user_expiry(sdk: RemnawaveSDK,
                                    remnawave_uuid: uuid.UUID,
                                    expire_at: datetime) -> None:
    dto = UpdateUserRequestDto(uuid=remnawave_uuid, expire_at=_to_utc(expire_at))
    await sdk.users.update_user(dto)


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

            if not clients:
                logger.info("Nothing to do.")
                return

            if not apply:
                # Dry-run: query panel per client to show what would happen, but write nothing.
                logger.info("Dry-run mode — querying panel to categorise clients (no writes).")
                would_link = would_create = failed = 0
                for row in clients:
                    client_id = row['client_id']
                    telegram_id = row['telegram_id']
                    username = row['username']
                    expiration_date = row['expiration_date']
                    try:
                        panel_user = await _find_panel_user_by_telegram_id(sdk, telegram_id)
                        if panel_user is not None:
                            would_link += 1
                            logger.info(
                                "  [WOULD LINK]   client_id=%s  telegram_id=%s  username=%s"
                                "  expiry=%s  panel_uuid=%s",
                                client_id, telegram_id, username,
                                expiration_date, panel_user.uuid,
                            )
                        else:
                            would_create += 1
                            logger.info(
                                "  [WOULD CREATE] client_id=%s  telegram_id=%s  username=%s"
                                "  expiry=%s",
                                client_id, telegram_id, username, expiration_date,
                            )
                    except Exception as exc:
                        failed += 1
                        logger.error(
                            "  [ERROR]        client_id=%s  telegram_id=%s: %s",
                            client_id, telegram_id, exc,
                        )
                logger.info(
                    "Dry-run summary: would_link=%d  would_create=%d  panel_errors=%d",
                    would_link, would_create, failed,
                )
                logger.info("Re-run with --apply to apply changes.")
                return

            processed = migrated = linked = expiry_sync_failed = failed = 0
            for row in clients:
                processed += 1
                client_id = row['client_id']
                telegram_id = row['telegram_id']
                username = row['username']
                expiration_date = row['expiration_date']

                try:
                    panel_user = await _find_panel_user_by_telegram_id(sdk, telegram_id)

                    if panel_user is not None:
                        # User already exists in panel — link and sync expiry from bot DB.
                        await _insert_client_remnawave(
                            conn,
                            client_id,
                            panel_user.uuid,
                            panel_user.subscription_url,
                            created_at=panel_user.created_at,
                        )
                        linked += 1
                        logger.info(
                            "Linked  client_id=%s → existing remnawave_uuid=%s",
                            client_id, panel_user.uuid,
                        )

                        # Sync expiry separately: log warning on failure but keep linked count.
                        expire_at_utc = _to_utc(expiration_date)
                        logger.info(
                            "        syncing expire_at=%s (bot_db=%s, panel_current=%s)",
                            expire_at_utc, expiration_date, panel_user.expire_at,
                        )
                        try:
                            await _update_panel_user_expiry(sdk, panel_user.uuid, expiration_date)
                            logger.info(
                                "        expiry synced → %s", expire_at_utc,
                            )
                        except RemnawaveApiError as sync_exc:
                            expiry_sync_failed += 1
                            errors_detail = (
                                f" | validation_errors={sync_exc.error.errors}"
                                if sync_exc.error.errors else ""
                            )
                            logger.warning(
                                "        expiry sync FAILED for client_id=%s"
                                " remnawave_uuid=%s: %s%s",
                                client_id, panel_user.uuid, sync_exc, errors_detail,
                            )
                        except Exception as sync_exc:
                            expiry_sync_failed += 1
                            logger.warning(
                                "        expiry sync FAILED for client_id=%s"
                                " remnawave_uuid=%s: %s",
                                client_id, panel_user.uuid, sync_exc,
                            )
                    else:
                        # User not in panel — create from scratch.
                        squad_uuid = await _get_random_active_squad(conn)
                        if squad_uuid is None:
                            logger.warning(
                                "No active squads — creating client_id=%s without squad",
                                client_id,
                            )
                        dto = CreateUserRequestDto(
                            username=_sanitize_username(telegram_id, username),
                            expire_at=_to_utc(expiration_date),
                            telegram_id=telegram_id,
                            active_internal_squads=[squad_uuid] if squad_uuid else None,
                        )
                        response = await sdk.users.create_user(dto)
                        await _insert_client_remnawave(
                            conn, client_id, response.uuid, response.subscription_url)
                        migrated += 1
                        logger.info(
                            "Migrated client_id=%s → new remnawave_uuid=%s",
                            client_id, response.uuid,
                        )

                except RemnawaveApiError as exc:
                    failed += 1
                    errors_detail = (
                        f" | validation_errors={exc.error.errors}"
                        if exc.error.errors else ""
                    )
                    logger.error(
                        "FAILED client_id=%s telegram_id=%s: %s%s",
                        client_id, telegram_id, exc, errors_detail,
                    )
                except Exception as exc:
                    failed += 1
                    logger.error(
                        "FAILED client_id=%s telegram_id=%s: %s",
                        client_id, telegram_id, exc,
                    )

            logger.info(
                "Done: processed=%d  migrated=%d  linked=%d"
                "  expiry_sync_failed=%d  failed=%d",
                processed, migrated, linked, expiry_sync_failed, failed,
            )
    finally:
        await pool.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Migrate existing bot clients to Remnawave Panel.')
    parser.add_argument('--apply', action='store_true',
                        help='Write changes to the database and panel (default: dry-run)')
    args = parser.parse_args()
    asyncio.run(main(apply=args.apply))
