"""One-off script: disable 3X-UI clients whose DB owner has no active subscription.

Назначение
----------
Находит все vless-конфигурации в `configurations`, у владельца которых нет активной
подписки (`clients_subscriptions.expiration_date > NOW()` — не выполняется ни для одной
строки). Для каждой такой конфигурации проверяет соответствующего клиента в 3X-UI.
Если клиент там **включён** (`enable=True`) — деактивирует его.

Случаи, когда конфиг пропускается (не является ошибкой):
  - Сервер без API-кредов (нет `api_url`) → [skipped]
  - UUID не найден ни в одном inbound сервера → [missing-xui]
  - Клиент уже отключён в 3X-UI → [already-disabled]

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
    # Dry-run: показать, какие клиенты будут деактивированы:
    .venv-3.12/bin/python scripts/disable_inactive_vless_configs.py

    # Apply: деактивировать клиентов в 3X-UI:
    .venv-3.12/bin/python scripts/disable_inactive_vless_configs.py --apply
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
logger = logging.getLogger('disable_inactive_vless')


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
) -> dict[str, tuple[int, py3xui.Client]] | None:
    """Connect to a 3X-UI panel and return {uuid: (inbound_id, Client)} for all clients.

    Sets client.inbound_id on each Client object (py3xui doesn't do this automatically).
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

    clients: dict[str, tuple[int, py3xui.Client]] = {}
    for inbound in inbounds:
        for client in (inbound.settings.clients or []):
            uuid = str(client.id)
            client.inbound_id = inbound.id  # required for client.update()
            clients[uuid] = (inbound.id, client)

    logger.info('server=%-30s inbounds=%d clients=%d', server_id, len(inbounds), len(clients))
    return clients


async def fetch_inactive_vless_configs(pool: asyncpg.Pool) -> list[asyncpg.Record]:
    """Fetch vless configs whose owner has no active subscription."""
    async with pool.acquire() as conn:
        return await conn.fetch(
            """
            SELECT c.id, c.client_id, c.server_id, c.link
            FROM configurations c
            WHERE c.link LIKE 'vless://%'
              AND NOT EXISTS (
                SELECT 1 FROM clients_subscriptions cs
                WHERE cs.client_id = c.client_id
                  AND cs.expiration_date > NOW()
              )
            ORDER BY c.id;
            """
        )


async def disable_xui_client(
    api: py3xui.AsyncApi,
    client: py3xui.Client,
) -> bool:
    """Set client.enable = False and push the update to 3X-UI."""
    try:
        client.enable = False
        await api.client.update(str(client.id), client)
        return True
    except Exception as e:
        logger.error('[disable-error] uuid=%s error=%s', client.id, e)
        return False


async def main(apply: bool) -> int:
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
        server_clients: dict[str, dict[str, tuple[int, py3xui.Client]] | None] = {}
        server_apis: dict[str, py3xui.AsyncApi] = {}
        for server in servers:
            sid = server['id']
            server_clients[sid] = await fetch_server_clients(server)
            # Keep a logged-in API instance for apply mode
            api = py3xui.AsyncApi(
                server['api_url'],
                server['api_login'],
                server['api_password'],
                use_tls_verify=False,
            )
            server_apis[sid] = api

        inactive_configs = await fetch_inactive_vless_configs(pool)
        logger.info('Found %d inactive vless configurations in DB', len(inactive_configs))

        # Counters
        already_disabled = skipped = missing_xui = 0
        to_disable: list[tuple[str, py3xui.Client]] = []  # (server_id, client)

        for row in inactive_configs:
            config_id = row['id']
            client_id = row['client_id']
            server_id = row['server_id']
            link = row['link']

            uuid = urlparse(link).username
            if not uuid:
                logger.warning('[parse-error] id=%-6s link=%.80s', config_id, link)
                skipped += 1
                continue

            if server_id not in server_clients:
                logger.info('[skipped]          id=%-6s client_id=%-8s server=%-30s (no api_url)',
                            config_id, client_id, server_id)
                skipped += 1
                continue

            known = server_clients[server_id]
            if known is None:
                logger.info('[skipped]          id=%-6s client_id=%-8s server=%-30s (login failed)',
                            config_id, client_id, server_id)
                skipped += 1
                continue

            if uuid not in known:
                logger.info('[missing-xui]      id=%-6s client_id=%-8s server=%-30s uuid=%s',
                            config_id, client_id, server_id, uuid)
                missing_xui += 1
                continue

            _inbound_id, client = known[uuid]
            if not client.enable:
                logger.info('[already-disabled] id=%-6s client_id=%-8s server=%-30s uuid=%s',
                            config_id, client_id, server_id, uuid)
                already_disabled += 1
            else:
                logger.info('[needs-disable]    id=%-6s client_id=%-8s server=%-30s uuid=%s',
                            config_id, client_id, server_id, uuid)
                to_disable.append((server_id, client))

        logger.info('--- summary ---')
        logger.info('total inactive vless configs: %d', len(inactive_configs))
        logger.info('already disabled: %d', already_disabled)
        logger.info('needs disable:    %d', len(to_disable))
        logger.info('missing in xui:   %d', missing_xui)
        logger.info('skipped:          %d', skipped)

        if not to_disable:
            logger.info('Nothing to disable.')
            return 0

        if apply:
            # Re-login for apply (session may have timed out during dry-run scan)
            for server in servers:
                sid = server['id']
                if sid in server_apis:
                    try:
                        await server_apis[sid].login()
                    except Exception as e:
                        logger.error('[relogin-error] server=%-30s error=%s', sid, e)

            disabled_count = 0
            for server_id, client in to_disable:
                api = server_apis[server_id]
                ok = await disable_xui_client(api, client)
                if ok:
                    logger.info('[disabled]         server=%-30s uuid=%s', server_id, client.id)
                    disabled_count += 1
            logger.info('Disabled %d clients in 3X-UI.', disabled_count)
        else:
            logger.info('[dry-run] Would disable %d clients in 3X-UI. Pass --apply to apply.',
                        len(to_disable))

    finally:
        await pool.close()

    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true',
                        help='actually disable clients (default: dry-run)')
    args = parser.parse_args()
    sys.exit(asyncio.run(main(apply=args.apply)))
