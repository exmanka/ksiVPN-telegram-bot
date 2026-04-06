"""One-off script: delete vless configurations whose IP is not in any known server.

Назначение
----------
Сравнивает IP-адреса из `configurations.link` (vless://uuid@IP:PORT?...) с IP-адресами
из `servers.api_url` (https://IP:PORT/...). Конфигурации, чей IP отсутствует в таблице
серверов, считаются устаревшими и удаляются.

Затрагиваются только строки с `link LIKE 'vless://%'` — WireGuard-конфиги
(текст или telegram file_id) не трогаются.

Переменные окружения:
    POSTGRES_HOST     — хост БД (по умолчанию 'ksivpn-tgbot-postgres')
    POSTGRES_PORT     — порт БД (по умолчанию 5432)
    POSTGRES_DB       — имя БД
    POSTGRES_USER
    POSTGRES_PASSWORD

Использование:
    python scripts/delete_orphan_vless_configs.py            # dry-run
    python scripts/delete_orphan_vless_configs.py --apply    # реально удалять из БД
"""
import argparse
import asyncio
import logging
import os
import sys
from urllib.parse import urlparse

import asyncpg


logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger('delete_orphan_vless_configs')


async def fetch_vless_rows(pool: asyncpg.Pool) -> list[asyncpg.Record]:
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT id, client_id, link FROM configurations WHERE link LIKE 'vless://%' ORDER BY id;"
        )


async def fetch_server_ips(pool: asyncpg.Pool) -> set[str]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT api_url FROM servers WHERE api_url IS NOT NULL;"
        )
    ips: set[str] = set()
    for row in rows:
        hostname = urlparse(row['api_url']).hostname
        if hostname:
            ips.add(hostname)
        else:
            logger.warning('Could not parse hostname from api_url: %s', row['api_url'])
    return ips


async def delete_configs(pool: asyncpg.Pool, ids: list[int]) -> None:
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

    orphan_ids: list[int] = []
    parse_errors: list[tuple[int, str]] = []

    try:
        known_ips = await fetch_server_ips(pool)
        logger.info('Known server IPs (%d): %s', len(known_ips), sorted(known_ips))

        rows = await fetch_vless_rows(pool)
        logger.info('Found %d vless configurations', len(rows))

        for row in rows:
            config_id = row['id']
            link = row['link']
            hostname = urlparse(link).hostname

            if not hostname:
                logger.warning('config id=%s: could not parse IP from link: %s...', config_id, link[:60])
                parse_errors.append((config_id, link[:60]))
                continue

            if hostname not in known_ips:
                orphan_ids.append(config_id)
                logger.info(
                    '[orphan] id=%-6s client_id=%-8s ip=%-20s link=%.80s',
                    config_id, row['client_id'], hostname, link,
                )

        logger.info('=== summary ===')
        logger.info('total vless configs:  %d', len(rows))
        logger.info('parse errors:         %d', len(parse_errors))
        logger.info('orphans found:        %d', len(orphan_ids))

        if not orphan_ids:
            logger.info('Nothing to delete.')
            return 0

        if apply:
            await delete_configs(pool, orphan_ids)
            logger.info('Deleted %d orphan configurations.', len(orphan_ids))
        else:
            logger.info('[dry-run] Would delete %d configurations. Pass --apply to actually delete.', len(orphan_ids))

    finally:
        await pool.close()

    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='actually delete from DB (default: dry-run)')
    args = parser.parse_args()
    sys.exit(asyncio.run(main(apply=args.apply)))
