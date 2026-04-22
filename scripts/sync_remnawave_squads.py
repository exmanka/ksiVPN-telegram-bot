"""One-off / maintenance script: sync remnawave_internal_squads table from Remnawave Panel.

Назначение
----------
Читает все Internal Squads из Remnawave Panel через API и синхронизирует их
с локальной таблицей `remnawave_internal_squads` в боте:

- INSERT ... ON CONFLICT DO UPDATE для каждого squad-а из панели
- Помечает is_active=FALSE записи, которых больше нет в панели

По умолчанию — dry-run: изменения не применяются, только выводится отчёт.
Ключ --apply записывает изменения в БД.

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
    .venv-3.12/bin/python scripts/sync_remnawave_squads.py

    # Применить изменения:
    .venv-3.12/bin/python scripts/sync_remnawave_squads.py --apply
"""
import argparse
import asyncio
import logging
import os
import uuid

import asyncpg
from remnawave import RemnawaveSDK


logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger('sync_remnawave_squads')

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

async def _upsert_squad(conn: asyncpg.Connection, squad_uuid: uuid.UUID, name: str) -> None:
    await conn.execute(
        '''
        INSERT INTO remnawave_internal_squads (squad_uuid, name)
        VALUES ($1, $2)
        ON CONFLICT (squad_uuid) DO UPDATE
            SET name = EXCLUDED.name,
                is_active = TRUE,
                updated_at = NOW();
        ''',
        squad_uuid, name)


async def _deactivate_missing(conn: asyncpg.Connection,
                               active_uuids: list[uuid.UUID]) -> int:
    result = await conn.execute(
        '''
        UPDATE remnawave_internal_squads
        SET is_active = FALSE, updated_at = NOW()
        WHERE squad_uuid <> ALL($1::uuid[])
          AND is_active = TRUE;
        ''',
        active_uuids)
    return int(result.split()[-1])


async def _get_current_squads(conn: asyncpg.Connection) -> dict[uuid.UUID, str]:
    rows = await conn.fetch(
        'SELECT squad_uuid, name FROM remnawave_internal_squads WHERE is_active = TRUE;')
    return {row['squad_uuid']: row['name'] for row in rows}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main(apply: bool) -> None:
    sdk = _build_sdk()

    for req_var, name in [(POSTGRES_DB, 'POSTGRES_DB'),
                          (POSTGRES_USER, 'POSTGRES_USER'),
                          (POSTGRES_PASSWORD, 'POSTGRES_PASSWORD')]:
        if not req_var:
            raise SystemExit(f"{name} is not set")

    logger.info("Fetching internal squads from Remnawave Panel …")
    response = await sdk.internal_squads.get_internal_squads()
    panel_squads = {s.uuid: s.name for s in response.internal_squads}
    logger.info("Panel has %d squad(s):", len(panel_squads))
    for squad_uuid, name in panel_squads.items():
        logger.info("  %s  %s", squad_uuid, name)

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
            current = await _get_current_squads(conn)

            to_upsert = panel_squads
            to_deactivate = [u for u in current if u not in panel_squads]

            logger.info("--- Dry-run report ---")
            logger.info("  Upsert:     %d squad(s)", len(to_upsert))
            for u, n in to_upsert.items():
                marker = "(new)" if u not in current else "(update)" if current[u] != n else "(no-op)"
                logger.info("    %s  %s  %s", u, n, marker)
            logger.info("  Deactivate: %d squad(s)", len(to_deactivate))
            for u in to_deactivate:
                logger.info("    %s  %s", u, current[u])

            if not apply:
                logger.info("Dry-run mode — no changes written. Re-run with --apply to apply.")
                return

            logger.info("Applying changes …")
            async with conn.transaction():
                for squad_uuid, name in to_upsert.items():
                    await _upsert_squad(conn, squad_uuid, name)
                deactivated = await _deactivate_missing(conn, list(panel_squads.keys()))

            logger.info("Done: upserted %d, deactivated %d.", len(to_upsert), deactivated)
    finally:
        await pool.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Sync Remnawave internal squads into bot DB.')
    parser.add_argument('--apply', action='store_true',
                        help='Write changes to the database (default: dry-run)')
    args = parser.parse_args()
    asyncio.run(main(apply=args.apply))
