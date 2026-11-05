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
from src.payments.runtime import payment_service
from src.config import settings
from src.runtime import bot


logger = logging.getLogger(__name__)
apscheduler_logger = logging.getLogger(apscheduler.__name__).setLevel(logging.WARNING)


async def apscheduler_start():
    """Run apscheduler and add tasks."""
    global scheduler
    scheduler = AsyncIOScheduler(timezone=settings.tz)
    scheduler.add_job(_purge_subscription_events, 'cron', hour=23, minute=30)
    scheduler.add_job(send_database_backup, 'cron', hour=23, minute=00)
    # Payment-reconciler: catches webhooks the bot missed (extended downtime,
    # mis-registered URL). Provider retries cover transient blips; this is the
    # belt-and-braces. Runs every 2 minutes — light DB query + at most one
    # provider call per still-pending payment in the last 30 minutes.
    scheduler.add_job(_reconcile_pending_payments, 'cron', minute='*/2')
    scheduler.start()
    logger.info('Scheduler has been successfully launched!')


async def _reconcile_pending_payments() -> None:
    """APScheduler wrapper around :meth:`PaymentService.poll_pending`."""
    try:
        await payment_service.poll_pending(minutes=30)
    except Exception:
        logger.exception('Payment reconciler tick failed; will retry next interval')


async def apscheduler_finish():
    """Shut down apscheduler."""
    scheduler.shutdown(wait=False)
    logger.info('Scheduler has been successfully shut down!')


async def _purge_subscription_events() -> None:
    """Delete processed subscription events older than 90 days."""
    try:
        deleted = await postgres_dbms.purge_done_subscription_events(days=90)
        logger.info('Purged %d processed subscription events', deleted)
    except Exception:
        logger.exception('Subscription events purge failed; will retry tomorrow')


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
