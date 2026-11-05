"""One-off script: prepare existing panel users for the «Telegram-only» grace period.

Назначение
----------
Grace-период (TGBOT_REMNAWAVE__GRACE__*) держит internal squad «только Telegram»
у каждого пользователя как постоянный «резервный» сервер: когда подписка
истекает, бот оставляет пользователю только этот squad, и нужный конфиг уже
лежит в VPN-приложении — обновлять подписку не нужно.

Новых пользователей бот создаёт сразу с этим squad. Скрипт дописывает его
всем уже существующим пользователям из `clients_remnawave`, у кого его нет.
Остальные squads, external squad и expire_at не трогаются.

Порядок выкатки:
    1. Настроить в панели inbound/host/internal squad «только Telegram»
       (и, по желанию, external squad для объявления в Happ).
    2. Применить миграцию 014, задеплоить бота с TGBOT_REMNAWAVE__GRACE__ENABLED=false.
    3. Запустить этот скрипт: dry-run, затем --apply.
    4. Включить TGBOT_REMNAWAVE__GRACE__ENABLED=true.

По умолчанию — dry-run: изменения не применяются, только выводится отчёт.
Ключ --apply обновляет пользователей в панели.

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
    GRACE_INTERNAL_SQUAD_UUID — UUID internal squad «только Telegram» (то же значение,
                                что TGBOT_REMNAWAVE__GRACE__INTERNAL_SQUAD_UUID)

Использование:
    # Dry-run (посмотреть что изменится):
    .venv/bin/python scripts/rollout_grace_period.py

    # Применить изменения:
    .venv/bin/python scripts/rollout_grace_period.py --apply
"""
import argparse
import asyncio
import logging
import os
import uuid

import asyncpg
from remnawave import RemnawaveSDK
from remnawave.models import UpdateUserRequestDto


logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger('rollout_grace_period')

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

GRACE_INTERNAL_SQUAD_UUID = os.getenv('GRACE_INTERNAL_SQUAD_UUID', '')


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
# DB helpers (standalone, no src imports)
# ---------------------------------------------------------------------------

async def _get_provisioned_clients(conn: asyncpg.Connection) -> list[asyncpg.Record]:
    return await conn.fetch(
        '''
        SELECT client_id, remnawave_uuid
        FROM clients_remnawave
        ORDER BY client_id;
        ''')


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main(apply: bool) -> None:
    if not GRACE_INTERNAL_SQUAD_UUID:
        raise SystemExit("GRACE_INTERNAL_SQUAD_UUID is not set")
    grace_squad = uuid.UUID(GRACE_INTERNAL_SQUAD_UUID)
    sdk = _build_sdk()

    for req_var, name in [(POSTGRES_DB, 'POSTGRES_DB'),
                          (POSTGRES_USER, 'POSTGRES_USER'),
                          (POSTGRES_PASSWORD, 'POSTGRES_PASSWORD')]:
        if not req_var:
            raise SystemExit(f"{name} is not set")

    response = await sdk.internal_squads.get_internal_squads()
    panel_squads = {s.uuid: s.name for s in response.internal_squads}
    if grace_squad not in panel_squads:
        raise SystemExit(f"Internal squad {grace_squad} does not exist in the panel")
    logger.info("Grace squad: %s (%s)", grace_squad, panel_squads[grace_squad])

    conn = await asyncpg.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        database=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
    )
    try:
        clients = await _get_provisioned_clients(conn)
    finally:
        await conn.close()
    logger.info("Provisioned clients in bot DB: %d", len(clients))

    to_update: list[tuple[int, uuid.UUID, list[uuid.UUID]]] = []
    already, failed = 0, 0
    for row in clients:
        try:
            user = await sdk.users.get_user_by_uuid(str(row['remnawave_uuid']))
        except Exception as exc:
            failed += 1
            logger.error("  client %s (%s): failed to fetch panel user: %s", row['client_id'], row['remnawave_uuid'], exc)
            continue
        squads = [s.uuid for s in user.active_internal_squads]
        if grace_squad in squads:
            already += 1
            continue
        to_update.append((row['client_id'], row['remnawave_uuid'], squads + [grace_squad]))

    logger.info("--- Dry-run report ---")
    logger.info("  Already have the grace squad: %d", already)
    logger.info("  Failed to fetch:              %d", failed)
    logger.info("  To update:                    %d", len(to_update))
    for client_id, remnawave_uuid, squads in to_update:
        logger.info("    client %s  %s  → %s", client_id, remnawave_uuid,
                    ', '.join(panel_squads.get(s, str(s)) for s in squads))

    if not apply:
        logger.info("Dry-run mode — no changes written. Re-run with --apply to apply.")
        return

    logger.info("Applying changes …")
    updated = 0
    for client_id, remnawave_uuid, squads in to_update:
        try:
            await sdk.users.update_user(UpdateUserRequestDto(uuid=remnawave_uuid, active_internal_squads=squads))
            updated += 1
        except Exception as exc:
            logger.error("  client %s (%s): update failed: %s", client_id, remnawave_uuid, exc)
    logger.info("Done: updated %d of %d.", updated, len(to_update))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Add the Telegram-only grace squad to every provisioned panel user.')
    parser.add_argument('--apply', action='store_true',
                        help='Update panel users (default: dry-run)')
    args = parser.parse_args()
    asyncio.run(main(apply=args.apply))
