import os
import apscheduler
import logging
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram.types.input_file import InputFile
from src.database import postgres_dbms
from src.services import internal_functions, localization as loc
from bot_init import bot, ADMIN_ID, TIMEZONE, BACKUP_PATH


logger = logging.getLogger(__name__)
apscheduler_logger = logging.getLogger(apscheduler.__name__).setLevel(logging.WARNING)


async def apscheduler_start():
    """Run apscheduler and add tasks."""
    global scheduler
    scheduler = AsyncIOScheduler()
    scheduler.add_job(send_subscription_expiration_notifications, 'cron', minute='0,30')
    scheduler.add_job(send_database_backup, 'cron', hour=23, minute=00, timezone=TIMEZONE)
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
    for telegram_id, _, is_sub_expiration_now, is_sub_expiration_in_1d, is_sub_expiration_in_3d, is_sub_expiration_in_7d in clients_notifications_status:

        # if client's subscription expires between [CURRENT_TIMESTAMP, CURRENT_TIMESTAMP + INTERVAL '30 minutes')
        if is_sub_expiration_now:
            client_id, name, surname, username, *_ = await postgres_dbms.get_client_info_by_telegramID(telegram_id)
            logger.info(f'Send message to client: {telegram_id} {name}. Subscription has expired.')

            # send message to client
            await bot.send_message(telegram_id, loc.auth.msgs['sub_expired'], 'HTML')

            # send message to admin
            # convert surname and username for beautiful formatting
            surname_str = await internal_functions.format_none_string(surname)
            username_str = await internal_functions.format_none_string(username)
            configurations_info = await postgres_dbms.get_configurations_info(await postgres_dbms.get_clientID_by_telegramID(telegram_id))
            await bot.send_message(ADMIN_ID,
                                   loc.admn.msgs['sub_expired'].format(len(configurations_info), client_id, username_str, name, surname_str, telegram_id),
                                   parse_mode='HTML')

            # send client's configurations to admin
            for file_type, date_of_receipt, os, is_chatgpt_available, name, country, city, bandwidth, ping, telegram_file_id in configurations_info:
                await internal_functions.send_configuration(ADMIN_ID, file_type, date_of_receipt, os, is_chatgpt_available, name, country, city, bandwidth, ping, telegram_file_id)

        # if client's subscription expires between [CURRENT_TIMESTAMP + INTERVAL '1 day', CURRENT_TIMESTAMP + INTERVAL '1 day 30 minutes')
        if is_sub_expiration_in_1d:
            client_id, name, surname, username, *_ = await postgres_dbms.get_client_info_by_telegramID(telegram_id)
            logger.info(f'Send message to client: {telegram_id} {name}. Subscription expires in 1 day.')

            # send message to client
            await bot.send_message(telegram_id, loc.auth.msgs['sub_expires_1d'], 'HTML')

            # send message to admin
            # convert surname and username for beautiful formatting
            surname_str = await internal_functions.format_none_string(surname)
            username_str = await internal_functions.format_none_string(username)
            await bot.send_message(ADMIN_ID,
                                   loc.admn.msgs['sub_expires_1d'].format(client_id, username_str, name, surname_str, telegram_id),
                                   parse_mode='HTML')

        # if client's subscription expires between [CURRENT_TIMESTAMP + INTERVAL '3 days', CURRENT_TIMESTAMP + INTERVAL '3 days 30 minutes')
        if is_sub_expiration_in_3d:
            client_id, name, surname, username, *_ = await postgres_dbms.get_client_info_by_telegramID(telegram_id)
            logger.info(f'Send message to client: {telegram_id} {name}. Subscription expires in 3 days.')

            # send message to client
            await bot.send_message(telegram_id, loc.auth.msgs['sub_expires_3d'], 'HTML')

            # send message to admin
            # convert surname and username for beautiful formatting
            surname_str = await internal_functions.format_none_string(surname)
            username_str = await internal_functions.format_none_string(username)
            await bot.send_message(ADMIN_ID,
                                   loc.admn.msgs['sub_expires_3d'].format(client_id, username_str, name, surname_str, telegram_id),
                                   parse_mode='HTML')

        # if client's subscription expires between [CURRENT_TIMESTAMP + INTERVAL '7 days', CURRENT_TIMESTAMP + INTERVAL '7 days 30 minutes')
        if is_sub_expiration_in_7d:
            client_id, name, surname, username, *_ = await postgres_dbms.get_client_info_by_telegramID(telegram_id)
            logger.info(f'Send message to client: {telegram_id} {name}. Subscription expires in 7 days.')

            # send message to client
            await bot.send_message(telegram_id, loc.auth.msgs['sub_expires_7d'], 'HTML')

            # send message to admin
            # convert surname and username for beautiful formatting
            surname_str = await internal_functions.format_none_string(surname)
            username_str = await internal_functions.format_none_string(username)
            await bot.send_message(ADMIN_ID,
                                   loc.admn.msgs['sub_expires_7d'].format(client_id, username_str, name, surname_str, telegram_id),
                                   parse_mode='HTML')


async def send_database_backup():
    """Send document to admin with database backup."""
    logger.info('Sending database backup to admin via telegram')
    backup_path_name: str = os.path.join(BACKUP_PATH, 'db-backup.gz')
    await bot.send_document(ADMIN_ID, InputFile(backup_path_name), caption=f'Backup for {datetime.now().strftime("%d.%m.%y %H:%M")}')
