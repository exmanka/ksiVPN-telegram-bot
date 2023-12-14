from bot_init import bot, YOOMONEY_TOKEN, ADMIN_ID
from aiogram import types, Dispatcher
from random import choice
from asyncio import sleep
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Text
from aiogram.utils.exceptions import MessageToDeleteNotFound
from src.keyboards import user_authorized_kb
from src.database import postgesql_db
from src.services.messages import messages_dict
from src.states import user_authorized_fsm
from src.middlewares import user_mw
from src.handlers.admin import send_user_info
from src.services.aiomoney import YooMoneyWallet, PaymentSource
from src.services import service_functions


async def already_registered_system(message: types.Message):
    await message.answer('Ух ты! Вы уже есть в нашей системе! Телепортируем в личный кабинет!', reply_markup=user_authorized_kb.menu_kb)

async def autocheck_payment_status(payment_id: int):
    wallet = YooMoneyWallet(YOOMONEY_TOKEN)

    # wait for user to redirect to Yoomoney site first 10 seconds
    await sleep(10)

    # after that check Yoomoney payment status using linear equation
    k = 0.04
    b = 1
    for x in range(100):
        if await wallet.check_payment_on_successful(payment_id):
            return 'success'
        await sleep(k * x + b)
        
    return 'failure'
            
async def sub_renewal(message: types.Message, state: FSMContext, months_number: int, discount: float):

    # get client_id by telegramID
    client_id = postgesql_db.find_clientID_by_telegramID(message.from_user.id)[0]

    # get client's sub info
    sub_id, sub_title, _, sub_price = postgesql_db.show_subscription_info(client_id)[0]

    # count payment sum
    payment_price = max(sub_price * months_number * (1 - discount), 2)

    # create entity in db table payments and getting payment_id
    payment_id = postgesql_db.insert_user_payment(client_id, sub_id, payment_price, months_number)[0]

    # use aiomoney for payment link creation
    wallet = YooMoneyWallet(YOOMONEY_TOKEN)
    payment_form = await wallet.create_payment_form(
            amount_rub=payment_price,
            unique_label=payment_id,
            payment_source=PaymentSource.YOOMONEY_WALLET,
            success_redirect_url="https://t.me/ksiVPN_bot"
        )

    # answer with ReplyKeyboardMarkup
    await message.answer('Ура, жду оплаты подписки', reply_markup=user_authorized_kb.sub_renewal_verification_kb)
    await state.set_state(user_authorized_fsm.PaymentMenu.verification)

    # answer with InlineKeyboardMarkup with link to payment
    answer_message = f'Подписка: <b>{sub_title}</b>\n'
    if discount:
        answer_message += f'Продление на {months_number} месяцев.\n\n'
        answer_message += f'<b>Сумма к оплате: {payment_price}₽</b> (скидка {sub_price * months_number * discount}₽).\n\n'
    else:
        answer_message += f'Продление на {months_number} месяц.\n\n'
        answer_message += f'<b>Сумма к оплате: {payment_price}₽</b>\n\n'
    
    answer_message += f'Уникальный идентификатор платежа: <b>{payment_id}</b>.'
    message_info = await message.answer(answer_message, parse_mode='HTML',
                                        reply_markup=InlineKeyboardMarkup().\
                                            add(InlineKeyboardButton('Оплатить', url=payment_form.link_for_customer)))
    
    postgesql_db.update_payment_telegram_message_id(payment_id, message_info['message_id'])
    
    # run payment autochecker for 310 seconds
    client_last_payment_status = await autocheck_payment_status(payment_id)

    # if autochecker returns successful payment info
    if client_last_payment_status == 'success':
        postgesql_db.update_payment_successful(payment_id, client_id, months_number)
        await state.set_state(user_authorized_fsm.PaymentMenu.menu)

        # try to delete payment message
        try:
            await bot.delete_message(message.chat.id, message_info['message_id'])

        # if already deleted
        except MessageToDeleteNotFound as _t:
                    pass

        # if not already deleted
        finally:
            await message.answer(f'Оплата произведена успешно!\n\nid: {payment_id}', reply_markup=user_authorized_kb.sub_renewal_kb)

@user_mw.authorized_only()
async def subscription_status(message: types.Message):
    if postgesql_db.is_subscription_not_started(message.from_user.id):
        await message.answer('Подписка еще не активирована, так как администратор пока что не прислал конфигурацию!')
        return
    
    if postgesql_db.is_subscription_active(message.from_user.id):
        await message.answer('Подписка активна!')
    else:
        await message.answer('Подписка деактивирована :/')
    
    await message.answer(f'Срок окончания действия подписки: {postgesql_db.show_subscription_expiration_date(message.from_user.id)[0]}.')

@user_mw.authorized_only()
async def submenu_cm_cancel(message: types.Message, state: FSMContext = None):
    '''
    Return to the menu regardless of whether there is a machine state
    '''

    if state:
        await state.finish()
    await message.answer('Возврат в главное меню', reply_markup=user_authorized_kb.menu_kb)

@user_mw.authorized_only()
async def sub_renewal_cm_start(message: types.Message):
    await user_authorized_fsm.PaymentMenu.menu.set()
    await message.answer('Переход в меню продления подписки!', reply_markup=user_authorized_kb.sub_renewal_kb)

@user_mw.authorized_only()
@user_mw.antiflood(rate_limit=2)
async def sub_renewal_months_1(message: types.Message, state: FSMContext):
    await sub_renewal(message, state, months_number=1, discount=0.)

@user_mw.authorized_only()
@user_mw.antiflood(rate_limit=2)
async def sub_renewal_months_3(message: types.Message, state: FSMContext):
    await sub_renewal(message, state, months_number=3, discount=.1)

@user_mw.authorized_only()
@user_mw.antiflood(rate_limit=2)
async def sub_renewal_months_12(message: types.Message, state: FSMContext):
    await sub_renewal(message, state, months_number=12, discount=.15)

@user_mw.authorized_only()
@user_mw.antiflood(rate_limit=2)
async def sub_renewal_payment_history(message: types.Message):
    payment_history = postgesql_db.get_user_payments(postgesql_db.find_clientID_by_telegramID(message.from_user.id)[0])

    is_payment_found = False
    for payment_id, sub_title, payment_price, payment_months_number, payment_date in payment_history:
        answer_message = f'Оплата подписки <b>{sub_title}</b> за <b>{payment_date}</b>\n\n'
        answer_message += f'За {payment_months_number} месяца подписки Вы заплатили <b>{payment_price}₽</b>.\n\n'
        answer_message += f'Уникальный идентификатор платежа: <b>{payment_id}</b>.'
        await message.answer(answer_message, parse_mode='HTML')

        is_payment_found = True

    # if user has no successful payments
    if not is_payment_found:
        await message.answer('К сожалению, не удалось найти информацию о поступивших платежах :/.\nВоспользуйтесь командой /restore_payments, чтобы восстановить платеж!')

@user_mw.authorized_only()
async def sub_renewal_submenu_cm_cancel(message: types.Message, state: FSMContext):

    # get last user's payment's telegram message id
    last_payment_message_id = postgesql_db.get_last_user_payment_message_id(postgesql_db.find_clientID_by_telegramID(message.from_user.id)[0])[0]

    # try to delete payment message
    try:
        await bot.delete_message(message.chat.id, last_payment_message_id)

    # if already deleted
    except MessageToDeleteNotFound as _t:
        pass

    finally:
        # update state and keyboard
        await state.set_state(user_authorized_fsm.PaymentMenu.menu)
        await message.answer('Оплата отменена!', reply_markup=user_authorized_kb.sub_renewal_kb)

@user_mw.authorized_only()
async def sub_renewal_verification(message: types.Message, state: FSMContext):
    wallet = YooMoneyWallet(YOOMONEY_TOKEN)

    # client's initiated payments for last n minutes
    client_id = postgesql_db.find_clientID_by_telegramID(message.from_user.id)[0]
    client_payments_ids = postgesql_db.get_last_user_payments_ids(client_id, minutes=60)
    await message.answer('Проверяю все созданные платежи за последний час!')

    is_payment_found = False
    for [payment_id] in client_payments_ids:

        # if payment wasn't added to db as successful and payment is successful according to Yoomoney:
        if postgesql_db.get_payment_status(payment_id)[0] == False and await wallet.check_payment_on_successful(payment_id):
            months_number = postgesql_db.get_payment_months_number(payment_id)[0]
            postgesql_db.update_payment_successful(payment_id, client_id, months_number)

            await state.set_state(user_authorized_fsm.PaymentMenu.menu)
            await message.answer(f'Оплата по заказу с id {payment_id} найдена!', reply_markup=user_authorized_kb.sub_renewal_kb)

            is_payment_found = True

    if not is_payment_found:
        await message.answer('К сожалению, я не смог найти оплаченные заказы :/\n\nИспользуйте команду /restore_payments, чтобы проверить платежи за все время!')

@user_mw.authorized_only()
async def account_cm_start(message: types.Message):
    await user_authorized_fsm.AccountMenu.menu.set()
    await message.answer('Переход в личный кабинет!', reply_markup=user_authorized_kb.account_kb)

@user_mw.authorized_only()
async def account_user_info(message: types.Message):
    name, surname, username, telegram_id, register_date = postgesql_db.show_user_info(message.from_user.id)
    tmp_string = f'Вот что я о Вас знаю:\n\n'
    tmp_string += f'<b>Имя</b>: {name}\n'

    # if user has surname
    if surname is not None:
        tmp_string += f'<b>Фамилия</b>: {surname}\n'

    # if user has username
    if username is not None:
        tmp_string += f'<b>Ник</b>: {username}\n'

    tmp_string += f'<b>Телеграм ID</b>: {telegram_id}\n'
    tmp_string += f'<b>Дата регистрации</b>: {register_date}'

    await message.answer(tmp_string, parse_mode='HTML')

@user_mw.authorized_only()
async def account_subscription_info(message: types.Message):
    _, title, description, price = postgesql_db.show_subscription_info(postgesql_db.find_clientID_by_telegramID(message.from_user.id)[0])[0]
    await message.answer(f'<b>{title}</b>\n\n{description}\n\nСтоимость: {int(price)}₽ в месяц.', parse_mode='HTML')

@user_mw.authorized_only()
async def account_configurations_cm_start(message: types.Message, state: FSMContext):
    await state.set_state(user_authorized_fsm.AccountMenu.configs)
    await message.answer('Меню конфигураций', reply_markup=user_authorized_kb.config_kb)

@user_mw.authorized_only()
async def account_ref_program_cm_start(message: types.Message, state:FSMContext):
    await state.set_state(user_authorized_fsm.AccountMenu.ref_program)
    await message.answer(messages_dict['ref_program']['text'], reply_markup=user_authorized_kb.ref_program_kb, parse_mode='HTML')

@user_mw.authorized_only()
async def account_promo_cm_start(message: types.Message, state: FSMContext):
    await state.set_state(user_authorized_fsm.AccountMenu.promo)
    await message.answer('Отлично, теперь введите промокод!', reply_markup=user_authorized_kb.promo_kb)

@user_mw.authorized_only()
async def account_settings_cm_start(message: types.Message, state: FSMContext):
    await state.set_state(user_authorized_fsm.AccountMenu.settings)
    await message.answer('Перехожу в настройки', reply_markup=user_authorized_kb.settings_kb)

@user_mw.authorized_only()
async def account_submenu_cm_cancel(message: types.Message, state: FSMContext):
    '''
    Return to account menu from promocode FSM and referal program FSM
    '''
    
    await state.set_state(user_authorized_fsm.AccountMenu.menu)
    await message.answer('Возврат в личный кабинет', reply_markup=user_authorized_kb.account_kb)

@user_mw.authorized_only()
async def account_configurations_info(message: types.Message):
    configurations_info = postgesql_db.show_configurations_info(postgesql_db.find_clientID_by_telegramID(message.from_user.id)[0])
    await message.answer(f'Информация о всех ваших конфигурациях, теперь не нужно искать их по диалогу с ботом!\n\nВсего конфигураций <b>{len(configurations_info)}</b>.',
                         parse_mode='HTML')

    for file_type, date_of_receipt, os, is_chatgpt_available, name, country, city, bandwidth, ping, telegram_file_id in configurations_info:
        answer_text = await service_functions.create_configuration_description(date_of_receipt, os, is_chatgpt_available, name, country, city, bandwidth, ping)

        # if config was generated as photo
        if file_type == 'photo':
            await bot.send_photo(message.from_user.id, telegram_file_id, answer_text, parse_mode='HTML', protect_content=True)

        # if config was generated as document
        elif file_type == 'document':
            await bot.send_document(message.from_user.id, telegram_file_id, caption=answer_text, parse_mode='HTML', protect_content=True)

        # if config was generated as link
        else:
            answer_text = f'<code>{telegram_file_id}</code>\n\n' + answer_text
            await bot.send_message(message.from_user.id, answer_text, parse_mode='HTML')

    await message.answer('Напоминаю правила (/rules):\n1. Одно устройство - одна конфигурация.\n2. Конфигурациями делиться с другими людьми запрещено!')

@user_mw.authorized_only()
async def account_configurations_submenu_cm_cancel(message: types.Message, state: FSMContext):
    await state.set_state(user_authorized_fsm.AccountMenu.configs)
    await message.answer('Возврат в меню конфигураций', reply_markup=user_authorized_kb.config_kb)

@user_mw.authorized_only()
async def account_configurations_request_cm_start(message: types.Message):
    if not postgesql_db.is_subscription_active(message.from_user.id):
        await message.answer('Для запроса новой конфигурации необходимо продлить подписку!')
        return

    answer_text = 'Понадобиться ответить на 3 вопроса, чтобы запросить новую конфигурацию у администратора!\n\n'
    answer_text += f'В данный момент у Вас <b>{postgesql_db.show_configurations_number(postgesql_db.find_clientID_by_telegramID(message.from_user.id)[0])[0]}</b> конфигураций.'
    await message.answer(answer_text, parse_mode='HTML')
    
    await user_authorized_fsm.ConfigMenu.platform.set()
    await message.answer('Выберите свою платформу', reply_markup=user_authorized_kb.config_platform_kb)

@user_mw.authorized_only()
async def account_configurations_request_platform(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['platform'] = message.text

    if message.text == '\U0001F4F1 Смартфон':
        await message.answer('Укажите операционную систему', reply_markup=user_authorized_kb.config_mobile_os_kb)
    else:
        await message.answer('Укажите операционную систему', reply_markup=user_authorized_kb.config_desktop_os_kb)

    await state.set_state(user_authorized_fsm.ConfigMenu.os)

@user_mw.authorized_only()
async def account_configurations_request_os(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['os_name'] = message.text

    await state.set_state(user_authorized_fsm.ConfigMenu.chatgpt)
    await message.answer('Используете ли Вы ChatGPT?', reply_markup=user_authorized_kb.config_chatgpt_kb)

@user_mw.authorized_only()
async def account_configurations_request_chatgpt_info(message: types.Message):
    await message.answer('<b>ChatGPT</b> — нейронная сеть в виде чат-бота, способная отвечать на сложные вопросы и вести осмысленный диалог!',
                            parse_mode='HTML')
    
@user_mw.authorized_only()
async def account_configurations_request_chatgpt(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['chatgpt'] = message.text

        await send_user_info({'fullname': message.from_user.full_name, 'username': message.from_user.username,\
                            'id': message.from_user.id}, data._data, is_new_user=False)

    
    await message.answer(f'Отлично! Теперь ждем ответа от разработчика: в скором времени он проверит ваши конфигурации и вышлет новую!',
                            reply_markup=user_authorized_kb.config_kb)
    await message.answer(f'Пожалуйста, не забывайте, что он тоже человек, и периодически спит (хотя на самом деле крайне редко)')

    await state.set_state(user_authorized_fsm.AccountMenu.configs)

@user_mw.authorized_only()
async def account_settings_submenu_cm_cancel(message: types.Message, state: FSMContext):
    await state.set_state(user_authorized_fsm.AccountMenu.settings)
    await message.answer('Возвращаю в настройки', reply_markup=user_authorized_kb.settings_kb)

@user_mw.authorized_only()
async def account_settings_chatgpt(message: types.Message, state: FSMContext):
    await state.set_state(user_authorized_fsm.SettingsMenu.chatgpt)
    await message.answer('Переход в меню настройки режима ChatGPT', reply_markup=await user_authorized_kb.settings_chatgpt(message.from_user.id))

@user_mw.authorized_only()
async def account_settings_chatgpt_mode(message: types.Message, state: FSMContext):
    chatgpt_mode_status: bool = postgesql_db.update_chatgpt_mode(message.from_user.id)[0]

    # if user switches ChatGPT mode from settings
    if await state.get_state() == user_authorized_fsm.SettingsMenu.chatgpt.state:
        reply_keyboard = await user_authorized_kb.settings_chatgpt(message.from_user.id)

    # if user switches ChatGPT mode using command
    else:
        reply_keyboard = None

    # if user turned option on
    if chatgpt_mode_status:
        await message.answer('Режим ChatGPT для бота включен!', reply_markup=reply_keyboard)

    # if user turned option off
    else:
        await message.answer('Режим ChatGPT для бота выключен!', reply_markup=reply_keyboard)

@user_mw.authorized_only()
async def account_settings_notifications(message: types.Message, state: FSMContext):
    client_id = postgesql_db.find_clientID_by_telegramID(message.from_user.id)[0]
    await state.set_state(user_authorized_fsm.SettingsMenu.notifications)
    await message.answer('Переход в меню настройки уведомлений', reply_markup=await user_authorized_kb.settings_notifications(client_id))

@user_mw.authorized_only()
async def account_settings_notifications_1d(message: types.Message):
    client_id = postgesql_db.find_clientID_by_telegramID(message.from_user.id)[0]
    expiration_in_1d_state = postgesql_db.update_notifications_1d(client_id)[0]

    # if user turned option on
    if expiration_in_1d_state:
        await message.answer('Отправка уведомления за 1 день до срока окончания подписки включена!', reply_markup=await user_authorized_kb.settings_notifications(client_id))

    # if user turned option off
    else:
        await message.answer('Отправка уведомления за 1 день до срока окончания подписки выключена!', reply_markup=await user_authorized_kb.settings_notifications(client_id))

@user_mw.authorized_only()
async def account_settings_notifications_3d(message: types.Message):
    client_id = postgesql_db.find_clientID_by_telegramID(message.from_user.id)[0]
    expiration_in_3d_state = postgesql_db.update_notifications_3d(client_id)[0]

    # if user turned option on
    if expiration_in_3d_state:
        await message.answer('Отправка уведомления за 3 дня до срока окончания подписки включена!', reply_markup=await user_authorized_kb.settings_notifications(client_id))

    # if user turned option off
    else:
        await message.answer('Отправка уведомления за 3 дня до срока окончания подписки выключена!', reply_markup=await user_authorized_kb.settings_notifications(client_id))

@user_mw.authorized_only()
async def account_settings_notifications_7d(message: types.Message):
    client_id = postgesql_db.find_clientID_by_telegramID(message.from_user.id)[0]
    expiration_in_7d_state = postgesql_db.update_notifications_7d(client_id)[0]

    # if user turned option on
    if expiration_in_7d_state:
        await message.answer('Отправка уведомления за 7 дней до срока окончания подписки включена!', reply_markup=await user_authorized_kb.settings_notifications(client_id))

    # if user turned option off
    else:
        await message.answer('Отправка уведомления за 7 дней до срока окончания подписки выключена!', reply_markup=await user_authorized_kb.settings_notifications(client_id))
    

@user_mw.authorized_only()
async def account_ref_program_info(message: types.Message):
    invited_by_user = postgesql_db.show_invited_by_user_info(message.from_user.id)
    invited_users_list = postgesql_db.show_invited_users_list(message.from_user.id)

    if invited_by_user:
        if invited_by_user[1]:  # username exists
            await message.answer(f'Вы были приглашены пользователем {invited_by_user[0]} {invited_by_user[1]}')
        else:
            await message.answer(f'Вы были приглашены пользователем {invited_by_user[0]}')
    else:
        await message.answer('Ого! Вы сами узнали о существовании данного проекта и зарегистрировались без приглашения от другого пользователя!')

    if invited_users_list:
        tmp_string = 'Приглашенные Вами пользователи, которые вступили в проект:\n\n'
        for idx, row in enumerate(invited_users_list):
            if row[1]:  # username exists
                tmp_string += f'{idx + 1}. Пользователь {row[0]} {row[1]}\n'
            else:
                tmp_string += f'{idx + 1}. Пользователь {row[0]}\n'

        await message.answer(tmp_string)
    else:
        await message.answer('Вы еще не пригласили ни одного пользователя. Рассказывайте о нашем проекте друзьям и получайте бесплатные месяца подписки!')

@user_mw.authorized_only()
async def account_ref_program_invite(message: types.Message):
    ref_promocode = postgesql_db.show_referral_promocode(message.from_user.id)[0]
    text = choice(messages_dict['ref_program_invites']['text'])
    text = text.replace('<refcode>', '<code>' + ref_promocode + '</code>')
    await message.answer(text, parse_mode='HTML')

@user_mw.authorized_only()
async def account_ref_program_promocode(message: types.Message):
    await message.answer(f'Ваш реферальный промокод: <code>{postgesql_db.show_referral_promocode(message.from_user.id)[0]}</code>', parse_mode='HTML')

async def send_admin_info_promo_entered(client_id: int, phrase: str, promo_type: str):
    name, surname, username, telegram_id, _ = postgesql_db.get_user_info_by_clientID(client_id)
    answer_message = f'Пользователем {name} {surname} {username} <code>{telegram_id}</code> был введен '

    if promo_type == 'global':
        id, _, expiration_date_parsed, _, bonus_time_parsed = postgesql_db.get_global_promo_parsed_tuple_by_phrase(phrase)
        answer_message += f'глобальный промокод с ID {id} на {bonus_time_parsed} дней подписки, заканчивающийся {expiration_date_parsed}.'

    elif promo_type == 'local':
        id, _, expiration_date_parsed, _, bonus_time_parsed, provided_sub_id = postgesql_db.get_local_promo_parsed_tuple_by_phrase(phrase)
        _, _, _, price = postgesql_db.get_subscription_info_by_subID(provided_sub_id)
        answer_message += f'специальный промокод с ID {id} на {bonus_time_parsed} дней подписки, предоставляющий подписку за {int(price)}₽/мес., '
        answer_message += f'заканчивающийся {expiration_date_parsed}'

    else:
        raise Exception('ввведен неверный тип промокода')
    
    await bot.send_message(ADMIN_ID, answer_message, parse_mode='HTML')

@user_mw.authorized_only()
async def account_promo_check(message: types.Message, state: FSMContext):

    # if promo is referral
    if postgesql_db.check_referral_promo(message.text):
        await message.answer('К сожалению, вводить реферальные промокоды можно только при регистрации ;(')
        return
    
    client_id = postgesql_db.find_clientID_by_telegramID(message.from_user.id)[0]
    promo_local_id = postgesql_db.check_local_promo_exists(message.text)
    promo_global_id = postgesql_db.check_global_promo_exists(message.text)

    # if promo is global and exists in system
    if promo_global_id:

        # if global promo wasn't entered by user before
        if not postgesql_db.is_global_promo_already_entered(client_id, promo_global_id[0]):
            promo_bonus_time = postgesql_db.check_global_promo_valid(promo_global_id[0])

            # if global promo didn't expire
            if promo_bonus_time:
                postgesql_db.insert_user_entered_global_promo(client_id, promo_global_id[0], promo_bonus_time[0])
                await message.answer(f'Ура! Промокод на {promo_bonus_time[1]} дней бесплатной подписки принят!', reply_markup=user_authorized_kb.account_kb)
                await send_admin_info_promo_entered(client_id, message.text, 'global')
                await state.set_state(user_authorized_fsm.AccountMenu.menu)

            else:
                await message.answer('К сожалению, срок действия промокода истек :(')

        else:
            await message.answer('Вы уже вводили данный промокод ранее!')
            

    # if promo is local and exists in system
    elif promo_local_id:
        is_accessible_and_already_entered = postgesql_db.check_local_promo_accessible(client_id, promo_local_id[0])

        # if local promo accessible
        if is_accessible_and_already_entered:

            # if local promo wasn't entered by user before
            if not is_accessible_and_already_entered[0]:
                promo_local_bonus_time = postgesql_db.check_local_promo_valid(promo_local_id[0])

                # if local promo didn't expire
                if promo_local_bonus_time:
                    bonus_time, bonus_time_parsed, provided_sub_id = promo_local_bonus_time
                    postgesql_db.insert_user_entered_local_promo(client_id, promo_local_id[0], bonus_time)

                    answer_message = f'Ура! Специальный промокод на {bonus_time_parsed} дней бесплатной подписки принят!'

                    # if local promo changes client's subscription
                    if provided_sub_id:
                        postgesql_db.update_client_subscription(client_id, provided_sub_id)
                        _, title, _, price = postgesql_db.get_subscription_info_by_subID(provided_sub_id)
                        answer_message += f'\n\nТип вашей подписки сменен на «<b>{title}</b>» со стоимостью {int(price)}₽/мес!'

                    await message.answer(answer_message, parse_mode='HTML', reply_markup=user_authorized_kb.account_kb)
                    await send_admin_info_promo_entered(client_id, message.text, 'local')
                    await state.set_state(user_authorized_fsm.AccountMenu.menu)
                
                else:
                    await message.answer('К сожалению, срок действия специального промокода истек :(')

            else:
                await message.answer('Вы уже вводили данный специальный промокод ранее!')

        else:
            await message.answer('К сожалению, Вы не можете использовать данный специальный промокод ((')


    # promo not found in system
    else:
        await message.answer('Такого промокода нет! Попробуйте ввести его еще раз')

@user_mw.authorized_only()
async def account_promo_info(message: types.Message, state: FSMContext):
    promo_info = postgesql_db.show_entered_promos(postgesql_db.find_clientID_by_telegramID(message.from_user.id)[0])
    await message.answer('Информация о введенных промокодах!')
    tmp_string = ''

    # info about entered referral promocode
    if promo_info['ref']:
        tmp_string += f"Использованный реферальный промокод:\n<b>{promo_info['ref'][0]}</b> от пользователя {promo_info['ref'][1]}.\n\n"

    # info about entered global promocodes
    if promo_info['global']:
        tmp_string += 'Использованные общедоступные промокоды:\n'
        for idx, row in enumerate(promo_info['global']):
            tmp_string += f"{idx + 1}. Промокод <b>{row[0]}</b> на {row[1]} бесплатных дней подписки. Был введен {row[2]}.\n"
        tmp_string += '\n'

    # info about entered local promocodes
    if promo_info['local']:
        tmp_string += 'Использованные специальные промокоды:\n'
        for idx, row in enumerate(promo_info['local']):
            tmp_string += f"{idx + 1}. Промокод <b>{row[0]}</b> на {row[1]} бесплатных дней подписки. Был введен {row[2]}.\n"
        tmp_string += '\n'

    # user hasn't entered promocodes at all
    if tmp_string == '':
        await message.answer('Вы еще не вводили ни одного промокода. Следите за новостями!')
    else:
        await message.answer(tmp_string, parse_mode='HTML')
    
@user_mw.authorized_only()
async def show_project_rules(message: types.Message):
    await message.answer(messages_dict['project_rules']['text'], parse_mode='HTML')

@user_mw.authorized_only()
async def restore_payments(message: types.Message):
    wallet = YooMoneyWallet(YOOMONEY_TOKEN)
    client_id = postgesql_db.find_clientID_by_telegramID(message.from_user.id)[0]
    client_payments_ids = postgesql_db.get_user_payments_ids(client_id)

    is_payment_found = False
    for [payment_id] in client_payments_ids:

        # if payment wasn't added to db as successful and payment is successful according to Yoomoney:
        if postgesql_db.get_payment_status(payment_id)[0] == False and await wallet.check_payment_on_successful(payment_id):
            months_number = postgesql_db.get_payment_months_number(payment_id)[0]
            postgesql_db.update_payment_successful(payment_id, client_id, months_number)

            await message.answer(f'Ура! Оплата по заказу с id {payment_id} найдена!')

            is_payment_found = True

    if not is_payment_found:
        answer_text = 'К сожалению, я не смог найти оплаченные заказы :/\n\n'
        answer_text += 'Возможно, Вы еще не завершили оплату, либо информация об оплате все еще в пути!\n\n'
        answer_text += 'Если Вы уверены, что оплата была совершена, обратитесь в раздел помощи /help'
        await message.answer(answer_text)


def register_handlers_authorized_client(dp: Dispatcher):
    dp.register_message_handler(subscription_status, Text(equals='Статус подписки'))
    dp.register_message_handler(submenu_cm_cancel, Text(equals='Возврат в главное меню'), state=[None,
                                                                                                 user_authorized_fsm.AccountMenu.menu,
                                                                                                 user_authorized_fsm.PaymentMenu.menu])
    dp.register_message_handler(sub_renewal_cm_start, Text(equals='\u2764\uFE0F\u200D\U0001F525 Продлить подписку!'))
    dp.register_message_handler(sub_renewal_months_1, Text(equals='1 месяц'), state=user_authorized_fsm.PaymentMenu.menu)
    dp.register_message_handler(sub_renewal_months_3, Text(equals='3 месяца (-10%)'), state=user_authorized_fsm.PaymentMenu.menu)
    dp.register_message_handler(sub_renewal_months_12, Text(equals='12 месяцев (-15%)'), state=user_authorized_fsm.PaymentMenu.menu)
    dp.register_message_handler(sub_renewal_payment_history, Text(equals='История оплаты'), state=user_authorized_fsm.PaymentMenu.menu)
    dp.register_message_handler(sub_renewal_submenu_cm_cancel, Text(equals='Отмена оплаты'), state=[None,
                                                                                                    user_authorized_fsm.PaymentMenu.verification])
    dp.register_message_handler(sub_renewal_verification, Text(equals='Проверить оплату'), state=user_authorized_fsm.PaymentMenu.verification)
    dp.register_message_handler(account_cm_start, Text(equals='Личный кабинет'))
    dp.register_message_handler(account_user_info, Text(equals='О пользователе'), state=user_authorized_fsm.AccountMenu.menu)
    dp.register_message_handler(account_subscription_info, Text(equals='О подписке'), state=user_authorized_fsm.AccountMenu.menu)
    dp.register_message_handler(account_submenu_cm_cancel, Text(equals='Вернуться'), state=[None,
                                                                                            user_authorized_fsm.AccountMenu.configs,
                                                                                            user_authorized_fsm.AccountMenu.ref_program,
                                                                                            user_authorized_fsm.AccountMenu.settings])
    dp.register_message_handler(account_submenu_cm_cancel, Text(equals='Отмена ввода'), state=[None,
                                                                                               user_authorized_fsm.AccountMenu.promo])
    dp.register_message_handler(account_configurations_cm_start, Text(equals='Конфигурации'), state=user_authorized_fsm.AccountMenu.menu)
    dp.register_message_handler(account_ref_program_cm_start, Text(equals='Реферальная программа'), state=user_authorized_fsm.AccountMenu.menu)
    dp.register_message_handler(account_promo_cm_start, Text(equals='Ввести промокод'), state=user_authorized_fsm.AccountMenu.menu)
    dp.register_message_handler(account_settings_cm_start, Text(equals='Настройки'), state=user_authorized_fsm.AccountMenu.menu)
    dp.register_message_handler(account_ref_program_info, Text(equals='Участие в реферальной программе'), state=user_authorized_fsm.AccountMenu.ref_program)
    dp.register_message_handler(account_ref_program_invite, Text(equals='Сгенерировать приглашение *'), state=user_authorized_fsm.AccountMenu.ref_program)
    dp.register_message_handler(account_ref_program_promocode, Text(equals='Показать реферальный промокод'), state=user_authorized_fsm.AccountMenu.ref_program)
    dp.register_message_handler(account_promo_info, Text(equals='Использованные промокоды'), state=user_authorized_fsm.AccountMenu.promo)
    dp.register_message_handler(account_promo_check, state=user_authorized_fsm.AccountMenu.promo)
    dp.register_message_handler(account_configurations_info, Text(equals='Текущие конфигурации'), state=user_authorized_fsm.AccountMenu.configs)
    dp.register_message_handler(account_configurations_submenu_cm_cancel, Text(equals='Отмена выбора'), state=[None,
                                                                                                               user_authorized_fsm.ConfigMenu.platform,
                                                                                                               user_authorized_fsm.ConfigMenu.os,
                                                                                                               user_authorized_fsm.ConfigMenu.chatgpt])
    dp.register_message_handler(account_configurations_request_cm_start, Text(equals='Запросить новую конфигурацию'), state=user_authorized_fsm.AccountMenu.configs)
    dp.register_message_handler(account_configurations_request_platform, Text(equals=['\U0001F4F1 Смартфон', '\U0001F4BB ПК']), state=user_authorized_fsm.ConfigMenu.platform)
    dp.register_message_handler(account_configurations_request_os, Text(equals=['Android', 'IOS (IPhone)', 'Windows', 'macOS', 'Linux']), state=user_authorized_fsm.ConfigMenu.os)
    dp.register_message_handler(account_configurations_request_chatgpt_info, Text(equals='Что это?', ignore_case=True), state=user_authorized_fsm.ConfigMenu.chatgpt)
    dp.register_message_handler(account_configurations_request_chatgpt, Text(equals=['Использую', 'Не использую']), state=user_authorized_fsm.ConfigMenu.chatgpt)
    dp.register_message_handler(account_settings_submenu_cm_cancel, Text(equals='Обратно'), state=[None,
                                                                                                   user_authorized_fsm.SettingsMenu.chatgpt,
                                                                                                   user_authorized_fsm.SettingsMenu.notifications])
    dp.register_message_handler(account_settings_chatgpt, Text(equals='Режим ChatGPT'), state=user_authorized_fsm.AccountMenu.settings)
    dp.register_message_handler(account_settings_chatgpt_mode, Text(equals=['Выключить', 'Включить']), state=user_authorized_fsm.SettingsMenu.chatgpt)
    dp.register_message_handler(account_settings_notifications, Text(equals='Уведомления'), state=user_authorized_fsm.AccountMenu.settings)
    dp.register_message_handler(account_settings_notifications_1d, Text(equals=['Выключить за 1 день', 'Включить за 1 день']), state=user_authorized_fsm.SettingsMenu.notifications)
    dp.register_message_handler(account_settings_notifications_3d, Text(equals=['Выключить за 3 дня', 'Включить за 3 дня']), state=user_authorized_fsm.SettingsMenu.notifications)
    dp.register_message_handler(account_settings_notifications_7d, Text(equals=['Выключить за 7 дней', 'Включить за 7 дней']), state=user_authorized_fsm.SettingsMenu.notifications)
    dp.register_message_handler(show_project_rules, Text(equals='Правила'))
    dp.register_message_handler(show_project_rules, commands=['rules'], state='*')
    dp.register_message_handler(restore_payments, commands=['restore_payments'], state='*')
    dp.register_message_handler(account_settings_chatgpt_mode, commands=['chatgpt_mode'], state='*')