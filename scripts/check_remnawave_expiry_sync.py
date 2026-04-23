"""Проверка синхронизации времени подписки между БД бота и Remnawave Panel.

Для каждого клиента с записью в `clients_remnawave` скрипт сравнивает
`clients_subscriptions.expiration_date` (БД бота) с `expire_at` (Remnawave Panel).
Расхождение > TOLERANCE_SECONDS считается рассинхронизацией.

По умолчанию — только проверка (чтение).
Ключ --apply обновляет `expire_at` в панели для всех клиентов с расхождением.

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
    REMNAWAVE_BASE_URL
    REMNAWAVE_TOKEN
    REMNAWAVE_CADDY_TOKEN  — необязательно

Переменные окружения (Timezone):
    BOT_TZ  — таймзона, в которой бот хранит даты (по умолчанию 'Europe/Moscow')

Использование:
    # Только проверка:
    .venv-3.12/bin/python scripts/check_remnawave_expiry_sync.py
    .venv-3.12/bin/python scripts/check_remnawave_expiry_sync.py --only-mismatches

    # Проверка + синхронизация расхождений:
    .venv-3.12/bin/python scripts/check_remnawave_expiry_sync.py --apply
    .venv-3.12/bin/python scripts/check_remnawave_expiry_sync.py --apply --tolerance 120
"""
import argparse
import asyncio
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import asyncpg
from remnawave import RemnawaveSDK
from remnawave.exceptions import ApiError as RemnawaveApiError
from remnawave.models import UpdateUserRequestDto


logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger('check_remnawave_expiry_sync')

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

DEFAULT_TOLERANCE_SECONDS = 60


def _build_sdk() -> RemnawaveSDK:
    if not REMNAWAVE_BASE_URL:
        raise SystemExit("REMNAWAVE_BASE_URL is not set")
    if not REMNAWAVE_TOKEN:
        raise SystemExit("REMNAWAVE_TOKEN is not set")
    kwargs: dict = {"base_url": REMNAWAVE_BASE_URL, "token": REMNAWAVE_TOKEN}
    if REMNAWAVE_CADDY_TOKEN:
        kwargs["caddy_token"] = REMNAWAVE_CADDY_TOKEN
    return RemnawaveSDK(**kwargs)


def _to_utc(dt: datetime) -> datetime:
    """Convert naive datetime (stored in BOT_TZ) to UTC-aware datetime."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=BOT_TZ).astimezone(timezone.utc)
    return dt.astimezone(timezone.utc)


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

async def _get_provisioned_clients(conn: asyncpg.Connection) -> list[asyncpg.Record]:
    """Return clients that have a remnawave record, with their subscription expiry."""
    return await conn.fetch(
        '''
        SELECT c.id          AS client_id,
               c.telegram_id,
               c.username,
               cs.expiration_date,
               cr.remnawave_uuid
        FROM clients c
        JOIN clients_subscriptions cs ON cs.client_id = c.id
        JOIN clients_remnawave cr     ON cr.client_id = c.id
        ORDER BY c.id;
        ''')


# ---------------------------------------------------------------------------
# Panel helpers
# ---------------------------------------------------------------------------

async def _update_panel_expiry(sdk: RemnawaveSDK,
                               remnawave_uuid: uuid.UUID,
                               expire_at_utc: datetime) -> None:
    dto = UpdateUserRequestDto(uuid=remnawave_uuid, expire_at=expire_at_utc)
    await sdk.users.update_user(dto)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main(tolerance_seconds: int, only_mismatches: bool, apply: bool) -> None:
    for req_var, name in [(POSTGRES_DB, 'POSTGRES_DB'),
                          (POSTGRES_USER, 'POSTGRES_USER'),
                          (POSTGRES_PASSWORD, 'POSTGRES_PASSWORD')]:
        if not req_var:
            raise SystemExit(f"{name} is not set")

    sdk = _build_sdk()
    tolerance = timedelta(seconds=tolerance_seconds)

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
            clients = await _get_provisioned_clients(conn)

        mode_str = "apply" if apply else "check"
        logger.info(
            "Mode: %s | Checking %d provisioned client(s) | tolerance=%ds | bot_tz=%s",
            mode_str, len(clients), tolerance_seconds, BOT_TZ,
        )

        total = ok = mismatch = fixed = fix_failed = error = 0

        for row in clients:
            total += 1
            client_id: int = row['client_id']
            telegram_id: int = row['telegram_id']
            username: str | None = row['username']
            expiration_date: datetime = row['expiration_date']
            remnawave_uuid: uuid.UUID = row['remnawave_uuid']

            user_label = f"@{username}" if username else f"tg_{telegram_id}"
            db_expiry = _to_utc(expiration_date)

            try:
                panel_user = await sdk.users.get_user_by_uuid(str(remnawave_uuid))
                panel_expiry: datetime = panel_user.expire_at.astimezone(timezone.utc)

                diff = abs(db_expiry - panel_expiry)

                if diff <= tolerance:
                    ok += 1
                    if not only_mismatches:
                        logger.info(
                            "OK       client_id=%-4s  %-20s  db=%s  panel=%s",
                            client_id, user_label,
                            db_expiry.strftime('%Y-%m-%d %H:%M:%S'),
                            panel_expiry.strftime('%Y-%m-%d %H:%M:%S'),
                        )
                else:
                    mismatch += 1
                    direction = (
                        "db>panel" if db_expiry > panel_expiry else "db<panel"
                    )
                    logger.warning(
                        "MISMATCH client_id=%-4s  %-20s"
                        "  db=%s  panel=%s  diff=%s  (%s)",
                        client_id, user_label,
                        db_expiry.strftime('%Y-%m-%d %H:%M:%S'),
                        panel_expiry.strftime('%Y-%m-%d %H:%M:%S'),
                        str(diff).split('.')[0],
                        direction,
                    )

                    if apply:
                        try:
                            await _update_panel_expiry(sdk, remnawave_uuid, db_expiry)
                            fixed += 1
                            logger.info(
                                "         → fixed: panel expire_at set to %s",
                                db_expiry.strftime('%Y-%m-%d %H:%M:%S'),
                            )
                        except RemnawaveApiError as fix_exc:
                            fix_failed += 1
                            errors_detail = (
                                f" | validation_errors={fix_exc.error.errors}"
                                if fix_exc.error.errors else ""
                            )
                            logger.error(
                                "         → fix FAILED: %s%s", fix_exc, errors_detail,
                            )
                        except Exception as fix_exc:
                            fix_failed += 1
                            logger.error("         → fix FAILED: %s", fix_exc)

            except RemnawaveApiError as exc:
                error += 1
                logger.error(
                    "ERROR    client_id=%-4s  remnawave_uuid=%s: %s",
                    client_id, remnawave_uuid, exc,
                )
            except Exception as exc:
                error += 1
                logger.error(
                    "ERROR    client_id=%-4s  remnawave_uuid=%s: %s",
                    client_id, remnawave_uuid, exc,
                )

        if apply:
            logger.info(
                "Result: total=%d  ok=%d  mismatch=%d  fixed=%d  fix_failed=%d  error=%d",
                total, ok, mismatch, fixed, fix_failed, error,
            )
        else:
            logger.info(
                "Result: total=%d  ok=%d  mismatch=%d  error=%d"
                "  (re-run with --apply to fix mismatches)",
                total, ok, mismatch, error,
            )

    finally:
        await pool.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Check (and optionally fix) expiry sync between bot DB and Remnawave Panel.')
    parser.add_argument(
        '--apply', action='store_true',
        help='Update panel expire_at for all mismatched clients (default: check only)',
    )
    parser.add_argument(
        '--tolerance', type=int, default=DEFAULT_TOLERANCE_SECONDS,
        metavar='SECONDS',
        help=f'Max allowed difference in seconds (default: {DEFAULT_TOLERANCE_SECONDS})',
    )
    parser.add_argument(
        '--only-mismatches', action='store_true',
        help='Print only mismatched and errored clients (suppress OK lines)',
    )
    args = parser.parse_args()
    asyncio.run(main(
        tolerance_seconds=args.tolerance,
        only_mismatches=args.only_mismatches,
        apply=args.apply,
    ))
