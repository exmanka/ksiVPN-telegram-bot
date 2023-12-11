from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime
from src.database.postgesql_db import get_notifications_status
from bot_init import bot


async def send_subscription_expiration_notifications():
    clients_notifications_status = get_notifications_status()
    for telegram_id, is_sub_expiration_now, is_sub_expiration_in_1d, is_sub_expiration_in_3d, is_sub_expiration_in_7d in clients_notifications_status:

        # if client's subscription expires between [CURRENT_TIMESTAMP, CURRENT_TIMESTAMP + INTERVAL '30 minutes')
        if is_sub_expiration_now:
            await bot.send_message(telegram_id, 'Срок действия подписки закончися!')

        # if client's subscription expires between [CURRENT_TIMESTAMP + INTERVAL '1 day', CURRENT_TIMESTAMP + INTERVAL '1 day 30 minutes')
        if is_sub_expiration_in_1d:
            await bot.send_message(telegram_id, 'Срок действия подписки закончится через 1 сутки!')

        # if client's subscription expires between [CURRENT_TIMESTAMP + INTERVAL '3 days', CURRENT_TIMESTAMP + INTERVAL '3 days 30 minutes')
        if is_sub_expiration_in_3d:
            await bot.send_message(telegram_id, 'Срок действия подписки закончится через 3 дня!')

        # if client's subscription expires between [CURRENT_TIMESTAMP + INTERVAL '7 days', CURRENT_TIMESTAMP + INTERVAL '7 days 30 minutes')
        if is_sub_expiration_in_7d:
            await bot.send_message(telegram_id, 'Срок действия подписки закончится через 7 дней!')


async def scheduler_start():
    global scheduler
    scheduler = AsyncIOScheduler()
    scheduler.start()
    scheduler.add_job(send_subscription_expiration_notifications, 'interval', minutes=30, next_run_time=datetime.now())

    print('Scheduler has been successfully launched!')
