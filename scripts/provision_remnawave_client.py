"""One-off script: provision an already registered bot client in Remnawave Panel.

Назначение
----------
Доделывает регистрацию клиента, у которого `authorization_complete` создал
строки `clients` + `clients_subscriptions`, но не смог создать пользователя
в панели (сетевые/DNS-ошибки и т.п.) — то есть строки в `clients_remnawave` нет.

Повторяет шаг регистрации `create_panel_user` → `insert_client_remnawave`:

- Если строка `clients_remnawave` уже есть — ничего не делает.
- Если в панели уже есть пользователь с этим telegram_id (создан, но запись
  в БД не дошла) — не создаёт дубликат, а привязывает его и синхронизирует
  expire_at с БД бота.
- Иначе создаёт пользователя в панели (username как в боте, случайный
  активный assignable squad, expire_at из `clients_subscriptions`) и пишет
  `clients_remnawave`.

Пользователю ничего не отправляется — после --apply ссылка доступна
в «Моей подписке».

По умолчанию — dry-run: изменения не применяются, только выводится отчёт.
Ключ --apply создаёт пользователя в панели и пишет в БД.

Требования
----------
  Python 3.12 (.venv):
      .venv/bin/pip install asyncpg remnawave

Переменные окружения (БД):
    POSTGRES_HOST     — хост БД (по умолчанию 'ksivpn-tgbot-postgres')
    POSTGRES_PORT     — порт БД (по умолчанию 5432)
    POSTGRES_DB       — имя БД
    POSTGRES_USER
    POSTGRES_PASSWORD

Переменные окружения (Remnawave):
    REMNAWAVE_BASE_URL    — корневой URL панели (https://panel.example.com)
    REMNAWAVE_TOKEN       — API Bearer-токен (панель → API Tokens)
    REMNAWAVE_CADDY_TOKEN — необязательно, если панель за Caddy с токен-авторизацией

Прочее:
    BOT_TZ  — таймзона, в которой бот хранит даты (по умолчанию 'Europe/Moscow')
    GRACE_INTERNAL_SQUAD_UUID — необязательно: internal squad «только Telegram»; если задан,
                       добавляется пользователю как постоянный резерв (как делает бот
                       при TGBOT_REMNAWAVE__GRACE__ENABLED=true)

Использование:
    # Dry-run (посмотреть что будет сделано):
    .venv/bin/python scripts/provision_remnawave_client.py --client-id 1699

    # Применить:
    .venv/bin/python scripts/provision_remnawave_client.py --client-id 1699 --apply
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
from remnawave.exceptions import NotFoundError
from remnawave.models import CreateUserRequestDto, UpdateUserRequestDto


logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger('provision_remnawave_client')

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

# Telegram-only grace squad kept on every user as a "reserve" server (optional).
GRACE_INTERNAL_SQUAD_UUID = uuid.UUID(os.environ['GRACE_INTERNAL_SQUAD_UUID']) if os.getenv('GRACE_INTERNAL_SQUAD_UUID') else None

# Same rule as src/services/remnawave_service.py:_sanitize_username
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

async def _get_client(conn: asyncpg.Connection, client_id: int) -> asyncpg.Record | None:
    return await conn.fetchrow(
        '''
        SELECT c.id AS client_id,
               c.telegram_id,
               c.username,
               cs.expiration_date,
               cr.remnawave_uuid
        FROM clients c
        LEFT JOIN clients_subscriptions cs ON cs.client_id = c.id
        LEFT JOIN clients_remnawave cr     ON cr.client_id = c.id
        WHERE c.id = $1;
        ''',
        client_id)


async def _get_random_active_squad_uuid(conn: asyncpg.Connection) -> uuid.UUID | None:
    return await conn.fetchval(
        '''
        SELECT squad_uuid
        FROM remnawave_internal_squads
        WHERE is_active = TRUE
          AND is_assignable = TRUE
        ORDER BY RANDOM()
        LIMIT 1;
        ''')


async def _insert_client_remnawave(conn: asyncpg.Connection,
                                   client_id: int,
                                   remnawave_uuid: uuid.UUID,
                                   subscription_url: str) -> None:
    await conn.execute(
        '''
        INSERT INTO clients_remnawave (client_id, remnawave_uuid, remnawave_subscription_url)
        VALUES ($1, $2, $3);
        ''',
        client_id, remnawave_uuid, subscription_url)


# ---------------------------------------------------------------------------
# Panel helpers
# ---------------------------------------------------------------------------

async def _find_panel_users_by_telegram_id(sdk: RemnawaveSDK, telegram_id: int) -> list:
    try:
        return list(await sdk.users.get_users_by_telegram_id(str(telegram_id)))
    except NotFoundError:
        return []


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main(client_id: int, apply: bool) -> None:
    sdk = _build_sdk()

    for req_var, name in [(POSTGRES_DB, 'POSTGRES_DB'),
                          (POSTGRES_USER, 'POSTGRES_USER'),
                          (POSTGRES_PASSWORD, 'POSTGRES_PASSWORD')]:
        if not req_var:
            raise SystemExit(f"{name} is not set")

    conn = await asyncpg.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        database=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
    )

    try:
        client = await _get_client(conn, client_id)
        if client is None:
            raise SystemExit(f"Client {client_id} not found in bot DB")
        if client['remnawave_uuid'] is not None:
            logger.info("Client %s is already provisioned (remnawave_uuid=%s) — nothing to do.",
                        client_id, client['remnawave_uuid'])
            return
        if client['expiration_date'] is None:
            raise SystemExit(f"Client {client_id} has no clients_subscriptions row — registration is broken deeper, fix manually")

        telegram_id: int = client['telegram_id']
        expire_at_utc = _to_utc(client['expiration_date'])
        logger.info("Client %s: tg_id=%s username=%s expiration_date=%s (%s UTC, bot_tz=%s)",
                    client_id, telegram_id, client['username'],
                    client['expiration_date'], expire_at_utc, BOT_TZ)

        existing = await _find_panel_users_by_telegram_id(sdk, telegram_id)
        if len(existing) > 1:
            for u in existing:
                logger.error("  panel user %s  username=%s", u.uuid, u.username)
            raise SystemExit(f"Panel has {len(existing)} users with tg_id={telegram_id} — resolve manually")

        if existing:
            panel_user = existing[0]
            logger.info("Panel already has user %s (username=%s, expire_at=%s) for tg_id=%s — will link it.",
                        panel_user.uuid, panel_user.username, panel_user.expire_at, telegram_id)
            if not apply:
                logger.info("Dry-run mode — would link it and set expire_at=%s. Re-run with --apply.", expire_at_utc)
                return
            await sdk.users.update_user(UpdateUserRequestDto(uuid=panel_user.uuid, expire_at=expire_at_utc))
            await _insert_client_remnawave(conn, client_id, panel_user.uuid, panel_user.subscription_url)
            logger.info("Done: linked client %s → %s, subscription_url=%s",
                        client_id, panel_user.uuid, panel_user.subscription_url)
            return

        username = _sanitize_username(telegram_id, client['username'])
        squad_uuid = await _get_random_active_squad_uuid(conn)
        if squad_uuid is None:
            logger.warning("No active assignable Remnawave squads in DB — user will be created without a squad")
        squads = [squad_uuid] if squad_uuid else []
        if GRACE_INTERNAL_SQUAD_UUID and GRACE_INTERNAL_SQUAD_UUID not in squads:
            squads.append(GRACE_INTERNAL_SQUAD_UUID)
        logger.info("Will create panel user: username=%s squads=%s expire_at=%s", username, squads, expire_at_utc)

        if not apply:
            logger.info("Dry-run mode — no changes written. Re-run with --apply to apply.")
            return

        response = await sdk.users.create_user(CreateUserRequestDto(
            username=username,
            expire_at=expire_at_utc,
            telegram_id=telegram_id,
            active_internal_squads=squads or None,
        ))
        logger.info("Created Remnawave user %s", response.uuid)
        await _insert_client_remnawave(conn, client_id, response.uuid, response.subscription_url)
        logger.info("Done: provisioned client %s → %s, subscription_url=%s",
                    client_id, response.uuid, response.subscription_url)
    finally:
        await conn.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Provision a registered bot client in Remnawave Panel.')
    parser.add_argument('--client-id', type=int, required=True,
                        help='clients.id in the bot DB')
    parser.add_argument('--apply', action='store_true',
                        help='Create the panel user and write to the database (default: dry-run)')
    args = parser.parse_args()
    asyncio.run(main(client_id=args.client_id, apply=args.apply))
