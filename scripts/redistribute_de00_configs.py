"""One-off script: reassign vless configurations from de00 to the correct real server.

Назначение
----------
`ksivpn-germany-0p` (alias `de00`) — фейковый сервер без `api_url`, оставшийся
после переноса. Часть конфигураций числится за ним, хотя `link` указывает на
IP реального сервера (de01–de04, es01, us01 и т.д.).

Скрипт строит карту IP → server_id из всех серверов с `api_url`, затем для каждой
конфигурации из de00 определяет правильный сервер по IP из `link` и обновляет
`server_id`. Конфигурации, чей IP не найден ни в одном сервере, помечаются как
[unresolved] и не трогаются.

Затрагиваются только строки с `link LIKE 'vless://%'` и `server_id = 'ksivpn-germany-0p'`.

Переменные окружения:
    POSTGRES_HOST     — хост БД (по умолчанию 'ksivpn-tgbot-postgres')
    POSTGRES_PORT     — порт БД (по умолчанию 5432)
    POSTGRES_DB       — имя БД
    POSTGRES_USER
    POSTGRES_PASSWORD

Использование:
    python scripts/redistribute_de00_configs.py            # dry-run
    python scripts/redistribute_de00_configs.py --apply    # реально обновить server_id
"""
import argparse
import asyncio
import logging
import os
import sys
from urllib.parse import urlparse

import asyncpg


logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger('redistribute_de00_configs')

SOURCE_SERVER = 'ksivpn-germany-0p'


async def fetch_ip_to_server_map(pool: asyncpg.Pool) -> dict[str, str]:
    """Build {ip: server_id} from all servers that have api_url."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, api_url FROM servers WHERE api_url IS NOT NULL;"
        )
    ip_map: dict[str, str] = {}
    for row in rows:
        hostname = urlparse(row['api_url']).hostname
        if hostname:
            ip_map[hostname] = row['id']
        else:
            logger.warning('Could not parse hostname from api_url: %s', row['api_url'])
    return ip_map


async def fetch_source_rows(pool: asyncpg.Pool) -> list[asyncpg.Record]:
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT id, client_id, link FROM configurations "
            "WHERE server_id = $1 AND link LIKE 'vless://%' ORDER BY id;",
            SOURCE_SERVER,
        )


async def update_server_id(pool: asyncpg.Pool, config_id: int, new_server_id: str) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE configurations SET server_id = $1 WHERE id = $2;",
            new_server_id, config_id,
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

    resolved: list[tuple[int, str]] = []   # (config_id, new_server_id)
    unresolved: list[tuple[int, str]] = [] # (config_id, ip or reason)

    try:
        ip_map = await fetch_ip_to_server_map(pool)
        logger.info('Known server IP map (%d entries):', len(ip_map))
        for ip, sid in sorted(ip_map.items()):
            logger.info('  %s → %s', ip, sid)

        rows = await fetch_source_rows(pool)
        logger.info('Found %d vless configurations under %s', len(rows), SOURCE_SERVER)

        for row in rows:
            config_id = row['id']
            link = row['link']
            hostname = urlparse(link).hostname

            if not hostname:
                logger.warning('[parse-error] id=%-6s link=%.60s', config_id, link)
                unresolved.append((config_id, 'parse error'))
                continue

            correct_server = ip_map.get(hostname)
            if not correct_server:
                logger.info(
                    '[unresolved] id=%-6s client_id=%-8s ip=%-20s link=%.80s',
                    config_id, row['client_id'], hostname, link,
                )
                unresolved.append((config_id, hostname))
                continue

            logger.info(
                '[resolved]   id=%-6s client_id=%-8s ip=%-20s → %-26s link=%.60s',
                config_id, row['client_id'], hostname, correct_server, link,
            )
            resolved.append((config_id, correct_server))

        logger.info('=== summary ===')
        logger.info('total found:  %d', len(rows))
        logger.info('resolved:     %d', len(resolved))
        logger.info('unresolved:   %d', len(unresolved))

        if not resolved:
            logger.info('Nothing to update.')
            return 0

        if apply:
            for config_id, new_server_id in resolved:
                await update_server_id(pool, config_id, new_server_id)
            logger.info('Updated %d configurations.', len(resolved))
        else:
            logger.info('[dry-run] Would update %d configurations. Pass --apply to apply.', len(resolved))

    finally:
        await pool.close()

    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='actually update server_id in DB (default: dry-run)')
    args = parser.parse_args()
    sys.exit(asyncio.run(main(apply=args.apply)))
