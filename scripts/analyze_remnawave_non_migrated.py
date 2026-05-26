"""Analytics script: users with active subscription who never connected via Remnawave.

Назначение
----------
Находит пользователей, которые:
1. Имеют **активную** подписку в Remnawave Panel (expire_at > now)
2. **Ни разу не подключались** через Remnawave (user_traffic.online_at IS NULL)

Для этих пользователей скрипт ищет их старые конфигурации в БД бота и выдаёт
сводку в разрезе серверов: сколько человек не перешло и их telegram_id.

Все действия — только чтение (RO). Никаких изменений не вносится.

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
    REMNAWAVE_BASE_URL    — корневой URL панели (https://panel.example.com)
    REMNAWAVE_TOKEN       — API Bearer-токен (панель → API Tokens)
    REMNAWAVE_CADDY_TOKEN — необязательно, если панель за Caddy с токен-авторизацией

Использование:
    .venv-3.12/bin/python scripts/analyze_remnawave_non_migrated.py
    .venv-3.12/bin/python scripts/analyze_remnawave_non_migrated.py --page-size 200

Флаг --list-ids
---------------
Дополнительный раздел отчёта: плоский список telegram_id всех неперешедших
пользователей (активная подписка + ни одного подключения через Remnawave),
без разделения по серверам. Удобно для копипасты в другие инструменты.

    .venv-3.12/bin/python scripts/analyze_remnawave_non_migrated.py --list-ids

Флаг --no-fallback
------------------
Дополнительный раздел отчёта: пользователи из числа неперешедших, у которых
все старые конфигурации находятся **ровно на одном сервере**. Если этот сервер
отключить — они полностью теряют VPN-доступ (нет fallback-конфигурации).
Вывод группируется по тому единственному серверу.

    .venv-3.12/bin/python scripts/analyze_remnawave_non_migrated.py --no-fallback
"""
import argparse
import asyncio
import logging
import os
from datetime import datetime, timezone

import asyncpg
from remnawave import RemnawaveSDK


logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger('analyze_remnawave_non_migrated')

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
# Panel helpers
# ---------------------------------------------------------------------------

def _is_active(expire_at: datetime, now_utc: datetime) -> bool:
    if expire_at.tzinfo is None:
        expire_at = expire_at.replace(tzinfo=timezone.utc)
    return expire_at > now_utc


async def _fetch_all_panel_users(sdk: RemnawaveSDK, page_size: int) -> list:
    all_users: list = []
    start = 0
    total: int | None = None
    while True:
        response = await sdk.users.get_all_users(start=start, size=page_size)
        page = list(response.users)
        all_users.extend(page)
        if total is None:
            total = int(response.total)
            logger.info("Panel reports %d user(s) total", total)
        logger.info("  fetched %d/%d", len(all_users), total)
        if not page or len(all_users) >= total:
            break
        start += page_size
    return all_users


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

async def _get_old_configs_by_telegram_ids(
    conn: asyncpg.Connection,
    telegram_ids: list[int],
) -> list[asyncpg.Record]:
    """Return old configs (server breakdown) for the given telegram_ids.

    Groups by server, collecting distinct telegram_ids per server.
    Only users who have at least one configuration row are included here.
    """
    return await conn.fetch(
        '''
        SELECT
            s.id          AS server_id,
            s.alias       AS server_alias,
            s.name        AS server_name,
            s.country     AS country,
            s.city        AS city,
            COUNT(DISTINCT cl.telegram_id)             AS user_count,
            ARRAY_AGG(DISTINCT cl.telegram_id ORDER BY cl.telegram_id) AS telegram_ids
        FROM configurations cfg
        JOIN clients cl  ON cl.id  = cfg.client_id
        JOIN servers s   ON s.id   = cfg.server_id
        WHERE cl.telegram_id = ANY($1::BIGINT[])
        GROUP BY s.id, s.alias, s.name, s.country, s.city
        ORDER BY user_count DESC, s.id;
        ''',
        telegram_ids,
    )


async def _get_telegram_ids_without_configs(
    conn: asyncpg.Connection,
    telegram_ids: list[int],
) -> list[int]:
    """Return subset of telegram_ids that have no configurations in DB at all."""
    rows = await conn.fetch(
        '''
        SELECT cl.telegram_id
        FROM clients cl
        WHERE cl.telegram_id = ANY($1::BIGINT[])
          AND NOT EXISTS (
              SELECT 1 FROM configurations cfg WHERE cfg.client_id = cl.id
          )
        ORDER BY cl.telegram_id;
        ''',
        telegram_ids,
    )
    return [r['telegram_id'] for r in rows]


async def _get_no_fallback_by_telegram_ids(
    conn: asyncpg.Connection,
    telegram_ids: list[int],
) -> list[asyncpg.Record]:
    """Users whose configs span exactly one distinct server (no fallback), grouped by that server."""
    return await conn.fetch(
        '''
        SELECT
            s.id    AS server_id,
            s.alias AS server_alias,
            s.name  AS server_name,
            s.country,
            s.city,
            COUNT(DISTINCT cl.telegram_id)                              AS user_count,
            ARRAY_AGG(DISTINCT cl.telegram_id ORDER BY cl.telegram_id) AS telegram_ids
        FROM configurations cfg
        JOIN clients cl ON cl.id  = cfg.client_id
        JOIN servers  s  ON s.id   = cfg.server_id
        WHERE cl.telegram_id = ANY($1::BIGINT[])
          AND (
              SELECT COUNT(DISTINCT cfg2.server_id)
              FROM configurations cfg2
              WHERE cfg2.client_id = cl.id
          ) = 1
        GROUP BY s.id, s.alias, s.name, s.country, s.city
        ORDER BY user_count DESC, s.id;
        ''',
        telegram_ids,
    )


async def _get_telegram_ids_not_in_bot_db(
    conn: asyncpg.Connection,
    telegram_ids: list[int],
) -> list[int]:
    """Return telegram_ids from the panel that don't exist in clients table at all."""
    rows = await conn.fetch(
        '''
        SELECT u.telegram_id
        FROM UNNEST($1::BIGINT[]) AS u(telegram_id)
        WHERE NOT EXISTS (
            SELECT 1 FROM clients cl WHERE cl.telegram_id = u.telegram_id
        )
        ORDER BY u.telegram_id;
        ''',
        telegram_ids,
    )
    return [r['telegram_id'] for r in rows]


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def _print_report(
    total_panel: int,
    candidates: list,  # panel user objects: active + never connected
    candidate_tids: list[int],
    server_rows: list[asyncpg.Record],
    no_configs_ids: list[int],
    not_in_db_ids: list[int],
    list_ids: bool = False,
    no_fallback_rows: list[asyncpg.Record] | None = None,
) -> None:
    separator = '─' * 72

    print()
    print(separator)
    print("  АНАЛИТИКА: пользователи с активной подпиской без подключения")
    print("             через Remnawave (старые конфигурации не сменили)")
    print(separator)
    print(f"  Всего пользователей в панели          : {total_panel}")
    print(f"  Активных без единого подключения      : {len(candidates)}")
    print(separator)

    if not candidates:
        print("  Все активные пользователи уже подключались через Remnawave.")
        print(separator)
        return

    # --- breakdown by server ---
    print()
    print("  РАЗБИВКА ПО СЕРВЕРАМ (старые конфигурации в БД бота)")
    print()

    if server_rows:
        for row in server_rows:
            ids_str = ', '.join(str(t) for t in row['telegram_ids'])
            print(f"  [{row['server_alias']}] {row['server_name']}  ({row['country']}, {row['city']})")
            print(f"    id в БД          : {row['server_id']}")
            print(f"    Не перешло       : {row['user_count']} чел.")
            print(f"    telegram_id      : {ids_str}")
            print()
    else:
        print("  (нет пользователей со старыми конфигурациями в БД)")
        print()

    # --- users without any old configs ---
    if no_configs_ids:
        ids_str = ', '.join(str(t) for t in no_configs_ids)
        print(separator)
        print(f"  Активны в панели, без старых конфигов в БД бота : {len(no_configs_ids)} чел.")
        print(f"  telegram_id : {ids_str}")

    # --- telegram_ids from panel not found in bot DB at all ---
    if not_in_db_ids:
        ids_str = ', '.join(str(t) for t in not_in_db_ids)
        print(separator)
        print(f"  Активны в панели, НЕ найдены в clients таблице  : {len(not_in_db_ids)} чел.")
        print(f"  telegram_id : {ids_str}")

    # --- flat id list (only when --list-ids flag was passed) ---
    if list_ids:
        print()
        print(separator)
        print("  ПЛОСКИЙ СПИСОК telegram_id (активны + ни разу не подключались)")
        print(separator)
        print(f"  Всего: {len(candidate_tids)}")
        print()
        print('  ' + ', '.join(str(t) for t in sorted(candidate_tids)))
        print()

    # --- no-fallback section (only when --no-fallback flag was passed) ---
    if no_fallback_rows is not None:
        print()
        print(separator)
        print("  БЕЗ FALLBACK: конфиги только на одном сервере")
        print("  (отключение сервера = полная потеря доступа к VPN)")
        print(separator)
        if no_fallback_rows:
            total_no_fallback = sum(r['user_count'] for r in no_fallback_rows)
            print(f"  Всего таких пользователей: {total_no_fallback}")
            print()
            for row in no_fallback_rows:
                ids_str = ', '.join(str(t) for t in row['telegram_ids'])
                print(f"  [{row['server_alias']}] {row['server_name']}  ({row['country']}, {row['city']})")
                print(f"    id в БД          : {row['server_id']}")
                print(f"    Без fallback     : {row['user_count']} чел.")
                print(f"    telegram_id      : {ids_str}")
                print()
        else:
            print("  (все неперешедшие пользователи имеют конфиги на 2+ серверах)")
            print()

    print(separator)
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main(page_size: int, list_ids: bool, no_fallback: bool) -> None:
    for req_var, name in [
        (POSTGRES_DB, 'POSTGRES_DB'),
        (POSTGRES_USER, 'POSTGRES_USER'),
        (POSTGRES_PASSWORD, 'POSTGRES_PASSWORD'),
    ]:
        if not req_var:
            raise SystemExit(f"{name} is not set")

    sdk = _build_sdk()

    logger.info("Fetching all panel users …")
    all_users = await _fetch_all_panel_users(sdk, page_size=page_size)
    now_utc = datetime.now(timezone.utc)

    candidates = [
        u for u in all_users
        if _is_active(u.expire_at, now_utc)
        and u.user_traffic.online_at is None
        and u.telegram_id is not None
    ]
    logger.info(
        "Active + never connected: %d of %d total panel users",
        len(candidates), len(all_users),
    )

    candidate_tids: list[int] = [int(u.telegram_id) for u in candidates]

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
            server_rows = await _get_old_configs_by_telegram_ids(conn, candidate_tids)
            no_configs_ids = await _get_telegram_ids_without_configs(conn, candidate_tids)
            not_in_db_ids = await _get_telegram_ids_not_in_bot_db(conn, candidate_tids)
            no_fallback_rows = (
                await _get_no_fallback_by_telegram_ids(conn, candidate_tids)
                if no_fallback else None
            )
    finally:
        await pool.close()

    _print_report(
        total_panel=len(all_users),
        candidates=candidates,
        candidate_tids=candidate_tids,
        server_rows=server_rows,
        no_configs_ids=no_configs_ids,
        not_in_db_ids=not_in_db_ids,
        list_ids=list_ids,
        no_fallback_rows=no_fallback_rows,
    )


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Analyse active Remnawave users who never connected (RO).')
    parser.add_argument(
        '--page-size', type=int, default=500,
        help='Page size for sdk.users.get_all_users pagination (default: 500)')
    parser.add_argument(
        '--list-ids', action='store_true',
        help='Add a flat list of all non-migrated telegram_ids (no server breakdown)')
    parser.add_argument(
        '--no-fallback', action='store_true',
        help='Add a section listing users whose configs are on a single server only '
             '(losing that server = losing all VPN access)')
    args = parser.parse_args()
    asyncio.run(main(
        page_size=args.page_size,
        list_ids=args.list_ids,
        no_fallback=args.no_fallback,
    ))
