"""One-off script: cross-check vless configurations between the bot DB and 3X-UI panels.

Назначение
----------
Два режима прогона:

**Forward (по умолчанию): DB → 3X-UI**
  Для каждой vless-конфигурации из `configurations` извлекает UUID из `link` и ищет его
  в соответствующем 3X-UI сервере (по `server_id`). Если UUID не найден ни в одном inbound —
  конфигурация "призрак" (ghost-db): она числится в боте, но реальный клиент на сервере удалён.
  При `--apply` такие строки удаляются из `configurations`.

**Reverse (--reverse): 3X-UI → DB**
  Для каждого клиента в 3X-UI проверяет, есть ли его UUID в таблице `configurations`.
  Если нет — клиент "призрак" (ghost-xui): он занимает место на сервере, но не отслеживается ботом.
  При `--apply` такие клиенты удаляются из 3X-UI через API.

Затрагиваются только строки с `link LIKE 'vless://%'` — WireGuard-конфиги не трогаются.

Требования
----------
  Python 3.10+, py3xui, asyncpg.
  Используй .venv-3.12:
      .venv-3.12/bin/pip install py3xui asyncpg

Переменные окружения:
    POSTGRES_HOST     — хост БД (по умолчанию 'ksivpn-tgbot-postgres')
    POSTGRES_PORT     — порт БД (по умолчанию 5432)
    POSTGRES_DB       — имя БД
    POSTGRES_USER
    POSTGRES_PASSWORD

Использование:
    # Forward dry-run (найти ghost-конфиги в БД):
    .venv-3.12/bin/python scripts/check_vless_configs_vs_servers.py

    # Forward apply (удалить ghost-конфиги из БД):
    .venv-3.12/bin/python scripts/check_vless_configs_vs_servers.py --apply

    # Reverse dry-run (найти ghost-клиентов в 3X-UI):
    .venv-3.12/bin/python scripts/check_vless_configs_vs_servers.py --reverse

    # Reverse apply (удалить ghost-клиентов из 3X-UI):
    .venv-3.12/bin/python scripts/check_vless_configs_vs_servers.py --reverse --apply
"""
import argparse
import asyncio
import logging
import os
import sys
from urllib.parse import urlparse

import asyncpg
import py3xui


logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger('check_vless_configs')


async def fetch_servers(pool: asyncpg.Pool) -> list[asyncpg.Record]:
    """Fetch all servers that have 3X-UI API credentials."""
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT id, api_url, api_login, api_password FROM servers "
            "WHERE api_url IS NOT NULL AND api_login IS NOT NULL AND api_password IS NOT NULL "
            "ORDER BY id;"
        )


async def fetch_server_clients(
    server: asyncpg.Record,
) -> dict[str, tuple[int, str]] | None:
    """Connect to a 3X-UI panel and return {uuid: (inbound_id, uuid)} for all clients.

    Returns None if login fails.
    """
    server_id = server['id']
    api = py3xui.AsyncApi(
        server['api_url'],
        server['api_login'],
        server['api_password'],
        use_tls_verify=False,
    )
    try:
        await api.login()
    except Exception as e:
        logger.error('[login-error] server=%-30s error=%s', server_id, e)
        return None

    try:
        inbounds = await api.inbound.get_list()
    except Exception as e:
        logger.error('[fetch-error] server=%-30s error=%s', server_id, e)
        return None

    clients: dict[str, tuple[int, str]] = {}
    for inbound in inbounds:
        for client in (inbound.settings.clients or []):
            uuid = str(client.id)
            clients[uuid] = (inbound.id, uuid)

    logger.info('server=%-30s inbounds=%d clients=%d', server_id, len(inbounds), len(clients))
    return clients


async def fetch_vless_configs(pool: asyncpg.Pool) -> list[asyncpg.Record]:
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT id, client_id, server_id, link FROM configurations "
            "WHERE link LIKE 'vless://%' ORDER BY id;"
        )


async def delete_db_configs(pool: asyncpg.Pool, ids: list[int]) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM configurations WHERE id = ANY($1::int[]);",
            ids,
        )


async def delete_xui_clients(
    server: asyncpg.Record,
    ghosts: list[tuple[int, str]],
) -> None:
    """Delete ghost clients from 3X-UI. ghosts = [(inbound_id, uuid), ...]"""
    api = py3xui.AsyncApi(
        server['api_url'],
        server['api_login'],
        server['api_password'],
        use_tls_verify=False,
    )
    await api.login()
    for inbound_id, uuid in ghosts:
        try:
            await api.client.delete(inbound_id, uuid)
            logger.info('[deleted-xui] server=%-30s inbound=%-4s uuid=%s',
                        server['id'], inbound_id, uuid)
        except Exception as e:
            logger.error('[delete-error] server=%-30s inbound=%-4s uuid=%s error=%s',
                         server['id'], inbound_id, uuid, e)


async def run_forward(
    pool: asyncpg.Pool,
    server_clients: dict[str, dict[str, tuple[int, str]] | None],
    db_configs: list[asyncpg.Record],
    apply: bool,
) -> None:
    """Forward pass: find configs in DB whose UUID is missing from 3X-UI."""
    ghost_ids: list[int] = []
    ok = skipped = 0

    logger.info('=== Forward pass: DB → 3X-UI ===')
    for row in db_configs:
        config_id = row['id']
        server_id = row['server_id']
        link = row['link']

        uuid = urlparse(link).username
        if not uuid:
            logger.warning('[parse-error] id=%-6s link=%.80s', config_id, link)
            skipped += 1
            continue

        if server_id not in server_clients:
            logger.info('[skipped]  id=%-6s client_id=%-8s server=%-30s (no api_url)',
                        config_id, row['client_id'], server_id)
            skipped += 1
            continue

        known = server_clients[server_id]
        if known is None:
            logger.info('[skipped]  id=%-6s client_id=%-8s server=%-30s (login failed)',
                        config_id, row['client_id'], server_id)
            skipped += 1
            continue

        if uuid in known:
            logger.info('[ok]       id=%-6s client_id=%-8s server=%-30s uuid=%s',
                        config_id, row['client_id'], server_id, uuid)
            ok += 1
        else:
            logger.info('[ghost-db] id=%-6s client_id=%-8s server=%-30s uuid=%s  link=%.80s',
                        config_id, row['client_id'], server_id, uuid, link)
            ghost_ids.append(config_id)

    logger.info('--- forward summary ---')
    logger.info('total db vless configs: %d', len(db_configs))
    logger.info('ok:       %d', ok)
    logger.info('skipped:  %d', skipped)
    logger.info('ghost-db: %d', len(ghost_ids))

    if not ghost_ids:
        logger.info('Nothing to delete from DB.')
        return

    if apply:
        await delete_db_configs(pool, ghost_ids)
        logger.info('Deleted %d ghost configurations from DB.', len(ghost_ids))
    else:
        logger.info('[dry-run] Would delete %d configurations from DB. Pass --apply to apply.',
                    len(ghost_ids))


async def run_reverse(
    servers: list[asyncpg.Record],
    server_clients: dict[str, dict[str, tuple[int, str]] | None],
    db_uuids: set[str],
    apply: bool,
) -> None:
    """Reverse pass: find 3X-UI clients whose UUID is missing from DB."""
    # Collect ghosts per server for efficient deletion
    server_ghosts: dict[str, list[tuple[int, str]]] = {}
    total_xui = ok_xui = 0

    logger.info('=== Reverse pass: 3X-UI → DB ===')
    servers_by_id = {s['id']: s for s in servers}

    for server_id, clients in server_clients.items():
        if clients is None:
            logger.info('[skipped] server=%-30s (login failed)', server_id)
            continue

        for uuid, (inbound_id, _) in clients.items():
            total_xui += 1
            if uuid in db_uuids:
                ok_xui += 1
            else:
                logger.info('[ghost-xui] server=%-30s inbound=%-4s uuid=%s',
                            server_id, inbound_id, uuid)
                server_ghosts.setdefault(server_id, []).append((inbound_id, uuid))

    ghost_total = sum(len(v) for v in server_ghosts.values())
    logger.info('--- reverse summary ---')
    logger.info('total xui clients: %d', total_xui)
    logger.info('ok:        %d', ok_xui)
    logger.info('ghost-xui: %d', ghost_total)

    if not ghost_total:
        logger.info('Nothing to delete from 3X-UI.')
        return

    if apply:
        for server_id, ghosts in server_ghosts.items():
            await delete_xui_clients(servers_by_id[server_id], ghosts)
        logger.info('Deleted %d ghost clients from 3X-UI.', ghost_total)
    else:
        logger.info('[dry-run] Would delete %d clients from 3X-UI. Pass --apply to apply.',
                    ghost_total)


async def main(apply: bool, reverse: bool) -> int:
    pool = await asyncpg.create_pool(
        host=os.environ.get('POSTGRES_HOST', 'ksivpn-tgbot-postgres'),
        port=int(os.environ.get('POSTGRES_PORT', '5432')),
        database=os.environ['POSTGRES_DB'],
        user=os.environ['POSTGRES_USER'],
        password=os.environ['POSTGRES_PASSWORD'],
        min_size=1,
        max_size=2,
    )

    try:
        servers = await fetch_servers(pool)
        logger.info('Found %d servers with api credentials', len(servers))

        # Connect to each 3X-UI panel and collect all clients
        server_clients: dict[str, dict[str, tuple[int, str]] | None] = {}
        for server in servers:
            server_clients[server['id']] = await fetch_server_clients(server)

        db_configs = await fetch_vless_configs(pool)
        logger.info('Found %d vless configurations in DB', len(db_configs))

        if reverse:
            db_uuids: set[str] = set()
            for row in db_configs:
                uuid = urlparse(row['link']).username
                if uuid:
                    db_uuids.add(uuid)
            await run_reverse(servers, server_clients, db_uuids, apply)
        else:
            await run_forward(pool, server_clients, db_configs, apply)

    finally:
        await pool.close()

    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true',
                        help='actually apply changes (default: dry-run)')
    parser.add_argument('--reverse', action='store_true',
                        help='reverse pass: find 3X-UI clients missing from DB (default: find DB configs missing from 3X-UI)')
    args = parser.parse_args()
    sys.exit(asyncio.run(main(apply=args.apply, reverse=args.reverse)))
