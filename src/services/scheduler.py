import asyncio
import os
import shutil
import apscheduler
import logging
from datetime import datetime
from pathlib import Path
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram.types import FSInputFile
from src.database import postgres_dbms
from src.services import internal_functions, localization as loc
from src.config import settings
from src.runtime import bot


logger = logging.getLogger(__name__)
apscheduler_logger = logging.getLogger(apscheduler.__name__).setLevel(logging.WARNING)


async def apscheduler_start():
    """Run apscheduler and add tasks."""
    global scheduler
    scheduler = AsyncIOScheduler(timezone=settings.tz)
    scheduler.add_job(send_subscription_expiration_notifications, 'cron', minute='0,30')
    scheduler.add_job(send_database_backup, 'cron', hour=23, minute=00)
    scheduler.start()
    logger.info('Scheduler has been successfully launched!')


async def apscheduler_finish():
    """Shut down apscheduler."""
    scheduler.shutdown(wait=False)
    logger.info('Scheduler has been successfully shut down!')


async def send_subscription_expiration_notifications():
    """Send messages to clients with expiring subscription."""
    logger.info('Messages are being sent to clients with an expiring subscription period')
    clients_notifications_status = await postgres_dbms.get_notifications_status()

    # for every client in db
    for telegram_id, is_sub_expiration_now, is_sub_expiration_in_1d, is_sub_expiration_in_3d, is_sub_expiration_in_7d in clients_notifications_status:

        # if client's subscription expires between [CURRENT_TIMESTAMP, CURRENT_TIMESTAMP + INTERVAL '30 minutes')
        if is_sub_expiration_now:
            client_id, name, surname, username, *_ = await postgres_dbms.get_client_info_by_telegramID(telegram_id)
            logger.info(f'Send message to client: {telegram_id} {name}. Subscription has expired.')

            # send message to client
            await internal_functions.safe_deliver(
                lambda: bot.send_message(telegram_id, loc.auth.msgs['sub_expired']),
                telegram_id=telegram_id,
            )

            # send message to admin
            # convert surname and username for beautiful formatting
            surname_str = await internal_functions.format_none_string(surname)
            username_str = await internal_functions.format_none_string(username)
            configurations_info = await postgres_dbms.get_configurations_info(await postgres_dbms.get_clientID_by_telegramID(telegram_id))
            await bot.send_message(settings.bot.admin_id,
                                   loc.admn.msgs['sub_expired'].format(len(configurations_info), client_id, username_str, name, surname_str, telegram_id))

            # send client's configurations to admin
            for file_type, date_of_receipt, os, name, country, city, bandwidth, ping, available_services, link, config_id, server_name in configurations_info:
                await internal_functions.send_configuration(settings.bot.admin_id, file_type, date_of_receipt, os, name, country, city, bandwidth, ping, available_services, link, config_id, server_name)

        # if client's subscription expires between [CURRENT_TIMESTAMP + INTERVAL '1 day', CURRENT_TIMESTAMP + INTERVAL '1 day 30 minutes')
        if is_sub_expiration_in_1d:
            client_id, name, surname, username, *_ = await postgres_dbms.get_client_info_by_telegramID(telegram_id)
            logger.info(f'Send message to client: {telegram_id} {name}. Subscription expires in 1 day.')

            # send message to client
            await internal_functions.safe_deliver(
                lambda: bot.send_message(telegram_id, loc.auth.msgs['sub_expires_1d']),
                telegram_id=telegram_id,
            )

            # send message to admin
            # convert surname and username for beautiful formatting
            surname_str = await internal_functions.format_none_string(surname)
            username_str = await internal_functions.format_none_string(username)
            await bot.send_message(settings.bot.admin_id,
                                   loc.admn.msgs['sub_expires_1d'].format(client_id, username_str, name, surname_str, telegram_id))

        # if client's subscription expires between [CURRENT_TIMESTAMP + INTERVAL '3 days', CURRENT_TIMESTAMP + INTERVAL '3 days 30 minutes')
        if is_sub_expiration_in_3d:
            client_id, name, surname, username, *_ = await postgres_dbms.get_client_info_by_telegramID(telegram_id)
            logger.info(f'Send message to client: {telegram_id} {name}. Subscription expires in 3 days.')

            # send message to client
            await internal_functions.safe_deliver(
                lambda: bot.send_message(telegram_id, loc.auth.msgs['sub_expires_3d']),
                telegram_id=telegram_id,
            )

            # send message to admin
            # convert surname and username for beautiful formatting
            surname_str = await internal_functions.format_none_string(surname)
            username_str = await internal_functions.format_none_string(username)
            await bot.send_message(settings.bot.admin_id,
                                   loc.admn.msgs['sub_expires_3d'].format(client_id, username_str, name, surname_str, telegram_id))

        # if client's subscription expires between [CURRENT_TIMESTAMP + INTERVAL '7 days', CURRENT_TIMESTAMP + INTERVAL '7 days 30 minutes')
        if is_sub_expiration_in_7d:
            client_id, name, surname, username, *_ = await postgres_dbms.get_client_info_by_telegramID(telegram_id)
            logger.info(f'Send message to client: {telegram_id} {name}. Subscription expires in 7 days.')

            # send message to client
            await internal_functions.safe_deliver(
                lambda: bot.send_message(telegram_id, loc.auth.msgs['sub_expires_7d']),
                telegram_id=telegram_id,
            )

            # send message to admin
            # convert surname and username for beautiful formatting
            surname_str = await internal_functions.format_none_string(surname)
            username_str = await internal_functions.format_none_string(username)
            await bot.send_message(settings.bot.admin_id,
                                   loc.admn.msgs['sub_expires_7d'].format(client_id, username_str, name, surname_str, telegram_id))


def _purge_old_backups(directory: Path, keep: int) -> None:
    """Remove oldest db-backup-*.gz files in *directory*, keeping only the *keep* most recent."""
    files = sorted(directory.glob('db-backup-*.gz'))
    for old_file in files[:-keep]:
        old_file.unlink()
        logger.info('Purged old backup: %s', old_file)


async def send_database_backup():
    """Dump the database via ``pg_dump`` and rotate backups using Grandfather-Father-Son scheme.

    Rotation tiers (all stored under ``settings.backup.path``):
      - Son  (daily):   daily/db-backup-YYYY-MM-DD.gz — keep 7 files
      - Father (weekly): weekly/db-backup-YYYY-WXX.gz  — keep 4 files, taken every Sunday
      - Grandfather (monthly): monthly/db-backup-YYYY-MM.gz — keep 12 files, taken on the 1st
    """
    logger.info('Running pg_dump and sending database backup to admin via telegram (GFS rotation)')

    now = datetime.now()
    base = Path(settings.backup.path)
    daily_dir = base / 'daily'
    weekly_dir = base / 'weekly'
    monthly_dir = base / 'monthly'
    for d in (daily_dir, weekly_dir, monthly_dir):
        d.mkdir(parents=True, exist_ok=True)

    daily_path = daily_dir / f'db-backup-{now.strftime("%Y-%m-%d")}.gz'

    env = os.environ.copy()
    env['PGPASSWORD'] = settings.connections.postgres.password.get_secret_value()

    # pg_dump stdout → gzip stdin → daily_path. Run as a shell pipeline via
    # /bin/sh so we don't have to stitch two asyncio subprocesses together manually.
    cmd = (
        'pg_dump '
        f'-h {settings.connections.postgres.host} '
        f'-U {settings.connections.postgres.user} '
        '--no-password --clean --if-exists --format=plain '
        f'{settings.connections.postgres.db} '
        f'| gzip > {daily_path}'
    )
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        logger.error('pg_dump failed (code=%s): %s', proc.returncode, stderr.decode(errors='replace'))
        return

    # Weekly: copy daily backup every Sunday (weekday 6), keep 4 weeks
    if now.weekday() == 6:
        weekly_path = weekly_dir / f'db-backup-{now.strftime("%Y-W%W")}.gz'
        shutil.copy2(daily_path, weekly_path)
        _purge_old_backups(weekly_dir, keep=4)

    # Monthly: copy daily backup on the 1st of the month, keep 12 months
    if now.day == 1:
        monthly_path = monthly_dir / f'db-backup-{now.strftime("%Y-%m")}.gz'
        shutil.copy2(daily_path, monthly_path)
        _purge_old_backups(monthly_dir, keep=12)

    # Purge old daily backups, keep 7 days
    _purge_old_backups(daily_dir, keep=7)

    await bot.send_document(
        settings.bot.admin_id,
        FSInputFile(daily_path),
        caption=f'Backup for {now.strftime("%d.%m.%y %H:%M")}',
    )
