"""One-off script: clean up disabled de02 configs for users who were migrated to de03/de04.

Назначение
----------
При аварийной миграции с de02 (ksivpn-germany-2p) на de03/de04 конфигурации создавались
без учёта лимита max_configurations. В результате у пользователей осталась старая отключённая
конфигурация на de02 и одна/несколько активных новых на de03/de04.

Скрипт удаляет отключённые de02-конфигурации из БД и 3X-UI — но только если:
  1. Пользователь имеет активную подписку.
  2. Клиент в 3X-UI de02 отключён (enable=False).
  3. У того же пользователя есть хотя бы одна включённая (enable=True) конфигурация
     на de03 или de04, то есть миграция уже завершена.

Затрагиваются только строки с `link LIKE 'vless://%'`.

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
    # Dry-run: показать, что будет удалено:
    .venv-3.12/bin/python scripts/cleanup_de02_after_migration.py

    # Apply: удалить из 3X-UI и БД:
    .venv-3.12/bin/python scripts/cleanup_de02_after_migration.py --apply
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
logger = logging.getLogger('cleanup_de02')

DE02 = 'ksivpn-germany-2p'
DE_NEW = frozenset({'ksivpn-germany-3p', 'ksivpn-germany-4p'})
TARGET_SERVERS = [DE02, *sorted(DE_NEW)]


async def fetch_target_servers(pool: asyncpg.Pool) -> list[asyncpg.Record]:
    """Fetch de02, de03, de04 server records with API credentials."""
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT id, api_url, api_login, api_password FROM servers "
            "WHERE id = ANY($1::varchar[]) "
            "  AND api_url IS NOT NULL AND api_login IS NOT NULL AND api_password IS NOT NULL "
            "ORDER BY id;",
            TARGET_SERVERS,
        )


async def fetch_server_clients(
    server: asyncpg.Record,
) -> dict[str, tuple[int, py3xui.Client]] | None:
    """Connect to a 3X-UI panel and return {uuid: (inbound_id, Client)} for all clients.

    Sets client.inbound_id on each Client object (required for update/delete calls).
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
            client.inbound_id = inbound.id  # required for API calls
            clients[uuid] = (inbound.id, client)

    enabled_count = sum(1 for _, c in clients.values() if c.enable)
    logger.info('server=%-30s inbounds=%d clients=%d (enabled=%d)',
                server_id, len(inbounds), len(clients), enabled_count)
    return clients


async def fetch_active_sub_configs(pool: asyncpg.Pool) -> list[asyncpg.Record]:
    """Fetch de02/de03/de04 vless configs for users who have an active subscription."""
    async with pool.acquire() as conn:
        return await conn.fetch(
            """
            SELECT c.id, c.client_id, c.server_id, c.link
            FROM configurations c
            WHERE c.link LIKE 'vless://%'
              AND c.server_id = ANY($1::varchar[])
              AND EXISTS (
                SELECT 1 FROM clients_subscriptions cs
                WHERE cs.client_id = c.client_id
                  AND cs.expiration_date > NOW()
              )
            ORDER BY c.client_id, c.server_id, c.id;
            """,
            TARGET_SERVERS,
        )


async def delete_xui_client(
    api: py3xui.AsyncApi,
    inbound_id: int,
    uuid: str,
) -> bool:
    """Delete a client from 3X-UI."""
    try:
        await api.client.delete(inbound_id, uuid)
        return True
    except Exception as e:
        logger.error('[delete-xui-error] inbound=%-4s uuid=%s error=%s', inbound_id, uuid, e)
        return False


async def delete_db_configs(pool: asyncpg.Pool, ids: list[int]) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM configurations WHERE id = ANY($1::int[]);",
            ids,
        )


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
        servers = await fetch_target_servers(pool)
        found_ids = {s['id'] for s in servers}
        for sid in TARGET_SERVERS:
            if sid not in found_ids:
                logger.warning('Server %s not found or has no API credentials — will be skipped', sid)

        # Connect to each 3X-UI panel
        server_clients: dict[str, dict[str, tuple[int, py3xui.Client]] | None] = {}
        server_apis: dict[str, py3xui.AsyncApi] = {}
        for server in servers:
            sid = server['id']
            server_clients[sid] = await fetch_server_clients(server)
            server_apis[sid] = py3xui.AsyncApi(
                server['api_url'],
                server['api_login'],
                server['api_password'],
                use_tls_verify=False,
            )

        db_configs = await fetch_active_sub_configs(pool)
        logger.info('Found %d de02/de03/de04 vless configs for active-subscription users',
                    len(db_configs))

        # Step 1: determine which client_ids have an enabled config on de03 or de04
        users_active_on_new: set[int] = set()
        for row in db_configs:
            if row['server_id'] not in DE_NEW:
                continue
            uuid = urlparse(row['link']).username
            if not uuid:
                continue
            sid = row['server_id']
            if sid not in server_clients or server_clients[sid] is None:
                continue
            if uuid in server_clients[sid]:
                _, client = server_clients[sid][uuid]
                if client.enable:
                    users_active_on_new.add(row['client_id'])

        logger.info('Users with an enabled config on de03/de04: %d', len(users_active_on_new))

        # Step 2: classify de02 configs
        to_delete_ids: list[int] = []
        to_delete_xui: list[tuple[int, str]] = []  # (inbound_id, uuid)
        enabled_skip = no_migration_skip = missing_xui = 0

        de02_configs = [r for r in db_configs if r['server_id'] == DE02]
        logger.info('de02 configs for active-subscription users: %d', len(de02_configs))

        de02_clients = server_clients.get(DE02)

        for row in de02_configs:
            config_id = row['id']
            client_id = row['client_id']
            uuid = urlparse(row['link']).username
            if not uuid:
                logger.warning('[parse-error]       id=%-6s link=%.80s', config_id, row['link'])
                continue

            if de02_clients is None:
                logger.info('[skipped]           id=%-6s client_id=%-8s (de02 login failed)',
                            config_id, client_id)
                continue

            if uuid not in de02_clients:
                logger.info('[missing-xui]       id=%-6s client_id=%-8s uuid=%s',
                            config_id, client_id, uuid)
                missing_xui += 1
                continue

            inbound_id, client = de02_clients[uuid]

            if client.enable:
                logger.info('[enabled-skip]      id=%-6s client_id=%-8s uuid=%s'
                            '  (still active on de02)',
                            config_id, client_id, uuid)
                enabled_skip += 1
                continue

            if client_id not in users_active_on_new:
                logger.info('[no-migration-skip] id=%-6s client_id=%-8s uuid=%s'
                            '  (no active de03/de04 config)',
                            config_id, client_id, uuid)
                no_migration_skip += 1
                continue

            logger.info('[to-delete]         id=%-6s client_id=%-8s uuid=%s'
                        '  (disabled on de02, migrated to de03/de04)',
                        config_id, client_id, uuid)
            to_delete_ids.append(config_id)
            to_delete_xui.append((inbound_id, uuid))

        logger.info('--- summary ---')
        logger.info('de02 configs (active sub):  %d', len(de02_configs))
        logger.info('to delete:                  %d', len(to_delete_ids))
        logger.info('enabled-skip:               %d', enabled_skip)
        logger.info('no-migration-skip:           %d', no_migration_skip)
        logger.info('missing-xui:                %d', missing_xui)

        if not to_delete_ids:
            logger.info('Nothing to delete.')
            return 0

        if apply:
            # Re-login before deleting (session may have expired during scan)
            try:
                await server_apis[DE02].login()
            except Exception as e:
                logger.error('[relogin-error] server=%s error=%s', DE02, e)
                return 1

            deleted_xui = 0
            for inbound_id, uuid in to_delete_xui:
                ok = await delete_xui_client(server_apis[DE02], inbound_id, uuid)
                if ok:
                    logger.info('[deleted-xui] inbound=%-4s uuid=%s', inbound_id, uuid)
                    deleted_xui += 1

            await delete_db_configs(pool, to_delete_ids)
            logger.info('Deleted %d clients from 3X-UI de02.', deleted_xui)
            logger.info('Deleted %d configurations from DB.', len(to_delete_ids))
        else:
            logger.info('[dry-run] Would delete %d configs from DB and 3X-UI. '
                        'Pass --apply to apply.', len(to_delete_ids))

    finally:
        await pool.close()

    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true',
                        help='actually delete (default: dry-run)')
    args = parser.parse_args()
    sys.exit(asyncio.run(main(apply=args.apply)))
