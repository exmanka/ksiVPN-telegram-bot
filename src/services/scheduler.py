import logging
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram.types.input_file import InputFile
from src.database import postgres_dbms
from src.services import internal_functions
from bot_init import bot, ADMIN_ID, BACKUP_PATH_NAME


logger = logging.getLogger(__name__)


async def apscheduler_start():
    """Run apscheduler and add tasks."""
    global scheduler
    scheduler = AsyncIOScheduler()
    scheduler.add_job(send_subscription_expiration_notifications, 'cron', minute='0,30')
    scheduler.add_job(send_database_backup, 'cron', hour=20, minute=30, timezone='Europe/Moscow')
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
    for telegram_id, sub_expiration_date, is_sub_expiration_now, is_sub_expiration_in_1d, is_sub_expiration_in_3d, is_sub_expiration_in_7d in clients_notifications_status:

        # if client's subscription expires between [CURRENT_TIMESTAMP, CURRENT_TIMESTAMP + INTERVAL '30 minutes')
        if is_sub_expiration_now:

            # send message to client
            await bot.send_message(telegram_id, 'Срок действия подписки закончися!')

            # send message to admin
            _, name, surname, username, *_ = await postgres_dbms.get_client_info_by_telegramID(telegram_id)
            configurations_info = await postgres_dbms.get_configurations_info(await postgres_dbms.get_clientID_by_telegramID(telegram_id))
            answer_message = f'Срок действия подписки пользователя {name} {surname} {username} <code>{telegram_id}</code> истек!\n\n'
            answer_message += f'Отключите его конфигурации (всего их <b>{len(configurations_info)}</b>)!'
            await bot.send_message(ADMIN_ID, answer_message, parse_mode='HTML')

            # send client's configurations to admin
            for file_type, date_of_receipt, os, is_chatgpt_available, name, country, city, bandwidth, ping, telegram_file_id in configurations_info:
                await internal_functions.send_configuration(ADMIN_ID, file_type, date_of_receipt, os, is_chatgpt_available, name, country, city, bandwidth, ping, telegram_file_id)

        # if client's subscription expires between [CURRENT_TIMESTAMP + INTERVAL '1 day', CURRENT_TIMESTAMP + INTERVAL '1 day 30 minutes')
        if is_sub_expiration_in_1d:

            # send message to client
            await bot.send_message(telegram_id, f'Уведомляю: cрок действия подписки закончится через 1 сутки, {sub_expiration_date}!')

            # send message to admin
            _, name, surname, username, *_ = await postgres_dbms.get_client_info_by_telegramID(telegram_id)
            await bot.send_message(ADMIN_ID,
                                   f'Срок действия подписки пользователя {name} {surname} {username} <code>{telegram_id}</code> истекает через 1 сутки!',
                                   parse_mode='HTML')

        # if client's subscription expires between [CURRENT_TIMESTAMP + INTERVAL '3 days', CURRENT_TIMESTAMP + INTERVAL '3 days 30 minutes')
        if is_sub_expiration_in_3d:

            # send message to client
            await bot.send_message(telegram_id, f'Уведомляю: срок действия подписки закончится через 3 дня, {sub_expiration_date}!')

            # send message to admin
            _, name, surname, username, *_ = await postgres_dbms.get_client_info_by_telegramID(telegram_id)
            await bot.send_message(ADMIN_ID,
                                   f'Срок действия подписки пользователя {name} {surname} {username} <code>{telegram_id}</code> истекает через 3 дня!',
                                   parse_mode='HTML')

        # if client's subscription expires between [CURRENT_TIMESTAMP + INTERVAL '7 days', CURRENT_TIMESTAMP + INTERVAL '7 days 30 minutes')
        if is_sub_expiration_in_7d:

            # send message to client
            await bot.send_message(telegram_id, f'Уведомляю: срок действия подписки закончится через 7 дней, {sub_expiration_date}!')

            # send message to admin
            _, name, surname, username, *_ = await postgres_dbms.get_client_info_by_telegramID(telegram_id)
            await bot.send_message(ADMIN_ID,
                                   f'Срок действия подписки пользователя {name} {surname} {username} <code>{telegram_id}</code> истекает через 7 дней!',
                                   parse_mode='HTML')


async def send_database_backup():
    """Send document to admin with database backup."""
    logger.info('A database backup is being sent')
    await bot.send_document(ADMIN_ID, InputFile(BACKUP_PATH_NAME), caption=f'Бэкап за {datetime.now().strftime("%d.%m.%y %H:%M")}')
