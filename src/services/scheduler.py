from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime
from src.database.postgesql_db import get_notifications_status
from bot_init import bot


async def send_subscription_expiration_notifications():
    clients_notifications_status = get_notifications_status()
    for telegram_id, sub_expiration_date, is_sub_expiration_now, is_sub_expiration_in_1d, is_sub_expiration_in_3d, is_sub_expiration_in_7d in clients_notifications_status:

        # if client's subscription expires between [CURRENT_TIMESTAMP, CURRENT_TIMESTAMP + INTERVAL '30 minutes')
        if is_sub_expiration_now:
            await bot.send_message(telegram_id, 'Срок действия подписки закончися!')

        # if client's subscription expires between [CURRENT_TIMESTAMP + INTERVAL '1 day', CURRENT_TIMESTAMP + INTERVAL '1 day 30 minutes')
        if is_sub_expiration_in_1d:
            await bot.send_message(telegram_id, f'Уведомляю: cрок действия подписки закончится через 1 сутки, {sub_expiration_date}!')

        # if client's subscription expires between [CURRENT_TIMESTAMP + INTERVAL '3 days', CURRENT_TIMESTAMP + INTERVAL '3 days 30 minutes')
        if is_sub_expiration_in_3d:
            await bot.send_message(telegram_id, f'Уведомляю: срок действия подписки закончится через 3 дня, {sub_expiration_date}!')

        # if client's subscription expires between [CURRENT_TIMESTAMP + INTERVAL '7 days', CURRENT_TIMESTAMP + INTERVAL '7 days 30 minutes')
        if is_sub_expiration_in_7d:
            await bot.send_message(telegram_id, f'Уведомляю: срок действия подписки закончится через 7 дней, {sub_expiration_date}!')


async def scheduler_start():
    global scheduler
    scheduler = AsyncIOScheduler()
    scheduler.add_job(send_subscription_expiration_notifications, 'interval', minutes=30, next_run_time=datetime.now())
    scheduler.start()

    print('Scheduler has been successfully launched!')
