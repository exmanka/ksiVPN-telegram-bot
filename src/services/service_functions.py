from bot_init import bot, ADMIN_ID
from src.database import postgesql_db
from aiogram import types
from aiogram.dispatcher import FSMContext
from src.keyboards.admin_kb import configuration
from src.keyboards.user_authorized_kb import menu_kb

async def create_configuration_description(date_of_receipt: str,
                                           os: str,
                                           is_chatgpt_available: bool,
                                           name: str,
                                           country: str,
                                           city: str,
                                           bandwidth: int,
                                           ping: int,
                                           link: str | None = None) -> str:

    answer_text = ''

    if link:
        answer_text += f'<code>{link}</code>\n\n'

    answer_text += f'<b>Создана</b>: {date_of_receipt}\n'

    # creating answer text with ChatGPT option
    if is_chatgpt_available:
        answer_text += f'<b>Платформа</b>: {os} с доступом к ChatGPT\n'

    # creating answer text without ChatGPT option
    else:
        answer_text += f'<b>Платформа</b>: {os}\n'

    answer_text += f'<b>Протокол</b>: {name}\n'
    answer_text += f'<b>Локация VPN</b>: {country}, {city}, скорость до {bandwidth} Мбит/с, ожидаемый пинг {ping} мс.'

    return answer_text

async def send_configuration(telegram_id: int,
                             file_type: str,
                             date_of_receipt: str,
                             os: str,
                             is_chatgpt_available: bool,
                             name: str,
                             country: str,
                             city: str,
                             bandwidth: int,
                             ping: int,
                             telegram_file_id: str):
    
    answer_text = await create_configuration_description(date_of_receipt, os, is_chatgpt_available, name, country, city, bandwidth, ping)

    # if config was generated as photo
    if file_type == 'photo':
        await bot.send_photo(telegram_id, telegram_file_id, answer_text, parse_mode='HTML', protect_content=True)

    # if config was generated as document
    elif file_type == 'document':
        await bot.send_document(telegram_id, telegram_file_id, caption=answer_text, parse_mode='HTML', protect_content=True)

    # if config was generated as link
    elif file_type == 'link':
        answer_text = f'<code>{telegram_file_id}</code>\n\n' + answer_text
        await bot.send_message(telegram_id, answer_text, parse_mode='HTML')

    else:
        raise Exception('указан неверный тип файла')
    
async def notify_admin_payment_success(client_id: int, months_number: int):
    answer_message = f'<b>Успешное продление подписки на {months_number} мес!</b>\n\n'
    name, surname, username, telegram_id, *_ = await postgesql_db.get_client_info_by_clientID(client_id)
    answer_message += f'<b>Имя</b>: <code>{name}</code>\n'
    answer_message += f'<b>Фамилия</b>: <code>{surname}</code>\n'
    answer_message += f'<b>Тег</b>: {username}\n'
    answer_message += f'<b>Telegram ID:</b> <code>{telegram_id}</code>\n'
    answer_message += f'<b>Client ID:</b> <code>{client_id}</code>'

    await bot.send_message(ADMIN_ID, answer_message, parse_mode='HTML')

async def notify_client_new_referal(client_creator_id: int, referal_client_name: str, referal_client_username: str | None = None):
    answer_message = ''

    # if client's nickname is specified
    if referal_client_username is not None:

        # if client's nickname doesn't start from '@'
        if referal_client_username[0] != '@':
            referal_client_username = '@' + referal_client_username
        
        answer_message += f'<b>Ух-ты! Пользователь {referal_client_name} {referal_client_username} использовал Ваш реферальный промокод при регистрации!</b>\n\n'

    else:
        answer_message += f'<b>Ух-ты! Пользователь {referal_client_name} использовал Ваш реферальный промокод при регистрации!</b>\n\n'

    *_, bonus_time_parsed = await postgesql_db.get_refferal_promo_info_by_clientCreatorID(client_creator_id)
    answer_message += f'После того, как он внесет первую плату, вы получите {bonus_time_parsed} дней подписки бесплатно!'

    client_creator_telegram_id = await postgesql_db.get_telegramID_by_clientID(client_creator_id)
    await bot.send_message(client_creator_telegram_id, answer_message, parse_mode='HTML')

async def check_referral_reward(ref_client_id: int):
    _, paid_months_counter, *_ = await postgesql_db.get_clients_subscriptions_info_by_clientID(ref_client_id)
    ref_client_name, _, ref_client_username, *_, used_ref_promo_id, _ = await postgesql_db.get_client_info_by_clientID(ref_client_id)

    # if client paid for subscription for the first time and used referral pormo
    if paid_months_counter == 1 and used_ref_promo_id:
        _, client_creator_id, *_ = await postgesql_db.get_refferal_promo_info_by_promoID(used_ref_promo_id)
        await postgesql_db.add_subscription_time(client_creator_id, days=30)

        answer_message = ''

        # if referral client's nickname is specified
        if ref_client_username is not None:
            answer_message += f'Вау! Пользователь {ref_client_name} {ref_client_username}, присоединившийся к проекту по Вашему реферальному промокоду, впервые оплатил подписку!\n\n'

        else:
            answer_message += f'Вау! Пользователь {ref_client_name}, присоединившийся к проекту по Вашему реферальному промокоду, впервые оплатил подписку!\n\n'

        answer_message += '<b>Вы получаете месяц подписки бесплатно!</b>'

        client_creator_telegram_id = await postgesql_db.get_telegramID_by_clientID(client_creator_id)
        await bot.send_message(client_creator_telegram_id, answer_message, parse_mode='HTML')

async def send_user_info(user: dict, choice: dict, is_new_user: bool):
    if is_new_user:
        
        answer_message = f"<b>Имя</b>: <code>{user['fullname']}</code>\n"
        answer_message += f"<b>Тэг</b>: @{user['username']}\n"
        answer_message += f"<b>ID</b>: <code>{user['id']}</code>\n"

        if choice['promo'] is None:
            answer_message += '<b>Пользователь не вводил промокод, конфигурацию можно отправить ТОЛЬКО ПОСЛЕ ОПЛАТЫ ПОДПИСКИ ИЛИ ВВОДА ПРОМОКОДА</b>\n'

        else:
            _, client_creator_id, provided_sub_id, _, bonus_time_parsed = await postgesql_db.get_refferal_promo_info_by_phrase(choice['promo'])
            client_creator_name, client_creator_surname, client_creator_username, client_creator_telegram_id, *_  = await postgesql_db.get_client_info_by_clientID(client_creator_id)
            *_, price = await postgesql_db.get_subscription_info_by_subID(provided_sub_id)

            answer_message += f"<b>Промокод</b>: <code>{choice['promo']}</code> от пользователя {client_creator_name} {client_creator_surname} {client_creator_username} "
            answer_message += f"<code>{client_creator_telegram_id}</code> на {bonus_time_parsed} бесплатных дней по подписке {int(price)}₽/мес.\n"


        answer_message += f"<b>Конфигурация</b>: {choice['platform'][2:]}, {choice['os_name']}, {choice['chatgpt']} ChatGPT\n\n"
        answer_message += f"<b>Запрос на подключение от нового пользователя!</b>"
                                

        await bot.send_message(ADMIN_ID, answer_message,
                               reply_markup=await configuration(user['id']),
                               parse_mode='HTML')
        
    else:
        await bot.send_message(ADMIN_ID,
                                f"<b>Имя</b>: <code>{user['fullname']}</code>\n"
                                f"<b>Тэг</b>: @{user['username']}\n"
                                f"<b>ID</b>: <code>{user['id']}</code>\n"
                                f"<b>Конфигурация</b>: {choice['platform'][2:]}, {choice['os_name']}, {choice['chatgpt']} ChatGPT\n\n"
                                f"<b>Запрос дополнительной конфигурации от пользователя!</b>",
                                reply_markup=await configuration(user['id']),
                                parse_mode='HTML')

async def authorization_complete(message: types.Message, state: FSMContext):
    used_ref_promo_id = None
    provided_sub_id = None
    bonus_time = None
    user = message.from_user

    async with state.proxy() as data:
        if phrase := data['promo']:
            used_ref_promo_id, _, provided_sub_id, bonus_time, _ = await postgesql_db.get_refferal_promo_info_by_phrase(phrase)

        await postgesql_db.insert_client(user.first_name, user.id, user.last_name, user.username, used_ref_promo_id, provided_sub_id, bonus_time)
        await send_user_info({'fullname': user.full_name, 'username': user.username, 'id': user.id}, data._data, is_new_user=True)

    await message.answer(f'Отлично! Теперь ждем ответа от разработчика: в скором времени он проверит Вашу регистрацию и вышлет конфигурацию! А пока вы можете исследовать бота!',
                         reply_markup=menu_kb)
    await message.answer(f'Пожалуйста, не забывайте, что он тоже человек, и периодически спит (хотя на самом деле крайне редко)')
    
    await state.finish()