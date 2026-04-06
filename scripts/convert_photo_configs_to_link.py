"""One-off script: convert `configurations` rows with file_type='photo' to file_type='link'.

Назначение
----------
До рефакторинга таблицы `configurations` некоторые конфиги хранились как photo —
это были QR-коды (WireGuard и VLESS), отправленные в Telegram и сохранённые как
telegram file_id в колонке `link` (после миграции 003).

Проблема с прямой загрузкой: в базе лежит file_id наименьшей миниатюры (photo[0],
~90x90 пикселей) — слишком мало для декодирования QR. Решение: отправить photo
в указанный чат (DECODE_CHAT_ID), получить Message обратно, взять photo[-1]
(наибольший размер), скачать и декодировать. Отправленное сообщение сразу удаляется.

Скрипт:
1. Выбирает все строки с file_type = 'photo'.
2. Для каждой отправляет маленький file_id в DECODE_CHAT_ID и берёт photo[-1].
3. Скачивает большую версию, декодирует QR (pyzbar + Pillow).
4. UPDATE configurations SET link = <decoded>, file_type = 'link' WHERE id = ...
5. Удаляет временное сообщение из чата.
6. В конце печатает сводку (успех / пропуски с причинами).

Запускать 1-2 раза после применения migrations/003_configurations_rename_link.sql
и ДО применения migrations/004_configurations_drop_photo_enum.sql.

Зависимости (ставить локально — скрипт одноразовый, в прод-образ не тянем):
    pip install pyzbar Pillow asyncpg aiogram==2.25.1
    # macOS: brew install zbar
    # debian/ubuntu: apt-get install libzbar0

Переменные окружения:
    BOT_TOKEN        — токен того же бота, который загружал photo-конфиги
    DECODE_CHAT_ID   — Telegram ID чата для временной отправки фото (обычно ADMIN_ID)
    POSTGRES_HOST    — хост БД (по умолчанию 'ksivpn-tgbot-postgres')
    POSTGRES_PORT    — порт БД (по умолчанию 5432)
    POSTGRES_DB      — имя БД
    POSTGRES_USER
    POSTGRES_PASSWORD

Использование:
    python scripts/convert_photo_configs_to_link.py            # dry-run
    python scripts/convert_photo_configs_to_link.py --apply    # реально писать в БД
"""
import argparse
import asyncio
import logging
import os
import sys
from io import BytesIO

import asyncpg
from aiogram import Bot
from aiogram.utils.exceptions import RetryAfter, TelegramAPIError

try:
    from PIL import Image
    from pyzbar.pyzbar import decode as qr_decode
except ImportError as e:
    sys.stderr.write(
        f'Missing dependency: {e}. Install with: pip install pyzbar Pillow\n'
        '(and the native zbar library — see the module docstring)\n'
    )
    sys.exit(1)


logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger('convert_photo_configs')


async def fetch_photo_rows(pool: asyncpg.Pool) -> list[asyncpg.Record]:
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT id, link FROM configurations WHERE file_type = 'photo' ORDER BY id;"
        )


async def update_row_to_link(pool: asyncpg.Pool, config_id: int, new_link: str) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE configurations SET link = $1, file_type = 'link' WHERE id = $2;",
            new_link, config_id,
        )


async def send_photo_safe(bot: Bot, chat_id: int, file_id: str):
    """Send photo, respecting Telegram rate limits."""
    while True:
        try:
            return await bot.send_photo(chat_id, file_id)
        except RetryAfter as e:
            logger.warning('Rate limited, waiting %s s...', e.timeout)
            await asyncio.sleep(e.timeout)


async def decode_photo_to_link(bot: Bot, file_id: str, decode_chat_id: int) -> str:
    """Send photo to decode_chat_id, download the largest PhotoSize, decode QR."""
    msg = await send_photo_safe(bot, decode_chat_id, file_id)
    largest = msg.photo[-1]
    try:
        tg_file = await bot.get_file(largest.file_id)
        buf = BytesIO()
        await bot.download_file(tg_file.file_path, destination=buf)
        buf.seek(0)
        image = Image.open(buf)

        results = qr_decode(image) or qr_decode(image.convert('L'))
        if not results:
            raise ValueError(f'no QR code detected in image ({largest.width}x{largest.height})')

        return results[0].data.decode('utf-8', errors='replace').strip()
    finally:
        try:
            await bot.delete_message(decode_chat_id, msg.message_id)
        except TelegramAPIError:
            pass


async def main(apply: bool) -> int:
    bot_token = os.environ['BOT_TOKEN']
    decode_chat_id = int(os.environ['DECODE_CHAT_ID'])

    pool = await asyncpg.create_pool(
        host=os.environ.get('POSTGRES_HOST', 'ksivpn-tgbot-postgres'),
        port=int(os.environ.get('POSTGRES_PORT', '5432')),
        database=os.environ['POSTGRES_DB'],
        user=os.environ['POSTGRES_USER'],
        password=os.environ['POSTGRES_PASSWORD'],
        min_size=1,
        max_size=2,
    )
    bot = Bot(token=bot_token)

    converted: list[int] = []
    skipped: list[tuple[int, str]] = []

    try:
        rows = await fetch_photo_rows(pool)
        logger.info('Found %d rows with file_type=photo', len(rows))
        if not rows:
            logger.info('Nothing to convert.')
            return 0

        for i, row in enumerate(rows, 1):
            config_id = row['id']
            file_id = row['link']

            if i % 50 == 0:
                logger.info('Progress: %d/%d (converted=%d, skipped=%d)',
                            i, len(rows), len(converted), len(skipped))

            try:
                new_link = await decode_photo_to_link(bot, file_id, decode_chat_id)
            except (TelegramAPIError, ValueError, OSError) as e:
                logger.warning('config id=%s: decode failed: %s', config_id, e)
                skipped.append((config_id, str(e)))
                continue

            if apply:
                try:
                    await update_row_to_link(pool, config_id, new_link)
                except asyncpg.UniqueViolationError as e:
                    logger.warning('config id=%s: UNIQUE conflict, skipping: %s', config_id, e)
                    skipped.append((config_id, f'unique conflict: {e}'))
                    continue
                logger.debug('config id=%s: updated -> %s...', config_id, new_link[:40])
            else:
                logger.info('[dry-run] id=%s -> %s...', config_id, new_link[:60])

            converted.append(config_id)

            # небольшая пауза чтобы не флудить в чат
            await asyncio.sleep(0.05)

    finally:
        await bot.close()
        await pool.close()

    logger.info('=== summary ===')
    logger.info('total:     %d', len(converted) + len(skipped))
    logger.info('converted: %d%s', len(converted), ' (dry-run)' if not apply else '')
    logger.info('skipped:   %d', len(skipped))
    for cid, reason in skipped:
        logger.info('  - id=%s: %s', cid, reason)

    return 0 if not skipped else 2


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='actually write changes to DB (default: dry-run)')
    args = parser.parse_args()
    sys.exit(asyncio.run(main(apply=args.apply)))
