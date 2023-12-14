from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime
from src.database.postgesql_db import get_notifications_status, get_user_parsed_tuple_by_telegramID, show_configurations_info, find_clientID_by_telegramID
from src.services import service_functions
from bot_init import bot, ADMIN_ID


async def send_subscription_expiration_notifications():
    clients_notifications_status = get_notifications_status()
    for telegram_id, sub_expiration_date, is_sub_expiration_now, is_sub_expiration_in_1d, is_sub_expiration_in_3d, is_sub_expiration_in_7d in clients_notifications_status:

        # if client's subscription expires between [CURRENT_TIMESTAMP, CURRENT_TIMESTAMP + INTERVAL '30 minutes')
        if is_sub_expiration_now:
            await bot.send_message(telegram_id, 'Срок действия подписки закончися!')

            _, name, surname, username, _ = get_user_parsed_tuple_by_telegramID(telegram_id)
            configurations_info = show_configurations_info(find_clientID_by_telegramID(telegram_id)[0])
            answer_message = f'Срок действия подписки пользователя {name} {surname} {username} <code>{telegram_id}</code> истек!\n\n'
            answer_message += f'Отключите его конфигурации (всего их <b>{len(configurations_info)}</b>)!'
            await bot.send_message(ADMIN_ID, answer_message, parse_mode='HTML')

            for file_type, date_of_receipt, os, is_chatgpt_available, name, country, city, bandwidth, ping, telegram_file_id in configurations_info:
                await service_functions.send_configuration(ADMIN_ID, file_type, date_of_receipt, os, is_chatgpt_available, name, country, city, bandwidth, ping, telegram_file_id)

        # if client's subscription expires between [CURRENT_TIMESTAMP + INTERVAL '1 day', CURRENT_TIMESTAMP + INTERVAL '1 day 30 minutes')
        if is_sub_expiration_in_1d:
            await bot.send_message(telegram_id, f'Уведомляю: cрок действия подписки закончится через 1 сутки, {sub_expiration_date}!')

            _, name, surname, username, _ = get_user_parsed_tuple_by_telegramID(telegram_id)
            await bot.send_message(ADMIN_ID,
                                   f'Срок действия подписки пользователя {name} {surname} {username} <code>{telegram_id}</code> истекает через 1 сутки!',
                                   parse_mode='HTML')

        # if client's subscription expires between [CURRENT_TIMESTAMP + INTERVAL '3 days', CURRENT_TIMESTAMP + INTERVAL '3 days 30 minutes')
        if is_sub_expiration_in_3d:
            await bot.send_message(telegram_id, f'Уведомляю: срок действия подписки закончится через 3 дня, {sub_expiration_date}!')

            _, name, surname, username, _ = get_user_parsed_tuple_by_telegramID(telegram_id)
            await bot.send_message(ADMIN_ID,
                                   f'Срок действия подписки пользователя {name} {surname} {username} <code>{telegram_id}</code> истекает через 3 дня!',
                                   parse_mode='HTML')


        # if client's subscription expires between [CURRENT_TIMESTAMP + INTERVAL '7 days', CURRENT_TIMESTAMP + INTERVAL '7 days 30 minutes')
        if is_sub_expiration_in_7d:
            await bot.send_message(telegram_id, f'Уведомляю: срок действия подписки закончится через 7 дней, {sub_expiration_date}!')

            _, name, surname, username, _ = get_user_parsed_tuple_by_telegramID(telegram_id)
            await bot.send_message(ADMIN_ID,
                                   f'Срок действия подписки пользователя {name} {surname} {username} <code>{telegram_id}</code> истекает через 7 дней!',
                                   parse_mode='HTML')


async def scheduler_start():
    global scheduler
    scheduler = AsyncIOScheduler()
    scheduler.add_job(send_subscription_expiration_notifications, 'interval', minutes=30, next_run_time=datetime.now())
    scheduler.start()

    print('Scheduler has been successfully launched!')
