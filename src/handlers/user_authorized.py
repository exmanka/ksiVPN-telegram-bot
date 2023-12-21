from random import choice
from aiogram import Dispatcher
from aiogram.types import Message
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Text
from aiogram.utils.exceptions import MessageToDeleteNotFound
from src.middlewares import user_mw
from src.keyboards import user_authorized_kb
from src.states import user_authorized_fsm
from src.database import postgesql_db
from src.services import service_functions, messages, aiomoney
from bot_init import bot, YOOMONEY_TOKEN


@user_mw.authorized_only()
async def subscription_status(message: Message):
    """Send message with subscription status."""

    # if admin hasn't still sent client's first configuration
    if await postgesql_db.is_subscription_not_started(message.from_user.id):
        await message.answer('Подписка еще не активирована, так как администратор пока что не прислал конфигурацию! Не переживайте, отчет времени истечения подписки начнется только после ее получения!')
        return

    # if subscription is acive
    if await postgesql_db.is_subscription_active(message.from_user.id):
        await message.answer('Подписка активна!')

    # if subsctiption is inactive
    else:
        await message.answer('Подписка деактивирована :/')

    await message.answer(f'Срок окончания действия подписки: {await postgesql_db.get_subscription_expiration_date(message.from_user.id)}.')


@user_mw.authorized_only()
async def submenu_fsm_cancel(message: Message, state: FSMContext = None):
    """Cancel FSM state for submenu and return to menu keyboard regardless of machine state."""
    if state:
        await state.finish()
    await message.answer('Возврат в главное меню', reply_markup=user_authorized_kb.menu_kb)


@user_mw.authorized_only()
async def sub_renewal_fsm_start(message: Message):
    """Start FSM for subscription renewal and show subscription renewal keyboard."""
    await user_authorized_fsm.PaymentMenu.menu.set()
    await message.answer('Переход в меню продления подписки!', reply_markup=user_authorized_kb.sub_renewal_kb)


@user_mw.authorized_only()
@user_mw.antiflood(rate_limit=2)
async def sub_renewal_months_1(message: Message, state: FSMContext):
    """Create subscription renewal payment for 1 month."""
    await service_functions.sub_renewal(message, state, months_number=1, discount=0.)


@user_mw.authorized_only()
@user_mw.antiflood(rate_limit=2)
async def sub_renewal_months_3(message: Message, state: FSMContext):
    """Create subscription renewal payment for 3 months."""
    await service_functions.sub_renewal(message, state, months_number=3, discount=.1)


@user_mw.authorized_only()
@user_mw.antiflood(rate_limit=2)
async def sub_renewal_months_12(message: Message, state: FSMContext):
    """Create subscription renewal payment for 12 months."""
    await service_functions.sub_renewal(message, state, months_number=12, discount=.15)


@user_mw.authorized_only()
@user_mw.antiflood(rate_limit=2)
async def sub_renewal_payment_history(message: Message):
    """Send messages with successful payments history."""
    payment_history = await postgesql_db.get_payments_successful_info(await postgesql_db.get_clientID_by_telegramID(message.from_user.id))
    is_payment_found = False

    # send message for every successful payment
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
async def sub_renewal_submenu_fsm_cancel(message: Message, state: FSMContext):
    """Cancel FSM state for subscription renewal, try to delete payment message and return to subscription renewal keyboard."""
    # get last user's payment's telegram message id
    last_payment_message_id = await postgesql_db.get_payment_last_message_id(await postgesql_db.get_clientID_by_telegramID(message.from_user.id))

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
async def sub_renewal_verification(message: Message, state: FSMContext):
    """Verify client's payments (per last hour) are successful according to YooMoney information."""
    wallet = aiomoney.YooMoneyWallet(YOOMONEY_TOKEN)

    # get client's initiated payments for last n minutes
    client_id = await postgesql_db.get_clientID_by_telegramID(message.from_user.id)
    client_payments_ids = await postgesql_db.get_paymentIDs_last(client_id, minutes=60)
    await message.answer('Проверяю все созданные платежи за последний час!')

    is_payment_found = False
    for [payment_id] in client_payments_ids:

        # if payment wasn't added to db as successful and payment is successful according to Yoomoney:
        if await postgesql_db.get_payment_status(payment_id) == False and await wallet.check_payment_on_successful(payment_id):

            # update payment in db as successful
            months_number = await postgesql_db.get_payment_months_number(payment_id)
            await postgesql_db.update_payment_successful(payment_id, client_id, months_number)

            # answer to a client
            await state.set_state(user_authorized_fsm.PaymentMenu.menu)
            await message.answer(f'Оплата по заказу с id {payment_id} найдена!', reply_markup=user_authorized_kb.sub_renewal_kb)

            # notify admin about successful payment and check referral reward for other client
            await service_functions.notify_admin_payment_success(client_id, months_number)
            await service_functions.check_referral_reward(client_id)

            is_payment_found = True

    if not is_payment_found:
        await message.answer('К сожалению, я не смог найти оплаченные заказы :/\n\nИспользуйте команду /restore_payments, чтобы проверить платежи за все время!')


@user_mw.authorized_only()
async def account_fsm_start(message: Message):
    """Start FSM for account menu and show account menu keyboard."""
    await user_authorized_fsm.AccountMenu.menu.set()
    await message.answer('Переход в личный кабинет!', reply_markup=user_authorized_kb.account_kb)


@user_mw.authorized_only()
async def account_client_info(message: Message):
    """Send message with information about client."""
    _, name, surname, username, _, register_date_parsed, *_ = await postgesql_db.get_client_info_by_telegramID(message.from_user.id)
    answer_text = f'Вот что я о Вас знаю:\n\n'
    answer_text += f'<b>Имя</b>: {name}\n'

    # if user has surname
    if surname is not None:
        answer_text += f'<b>Фамилия</b>: {surname}\n'

    # if user has username
    if username is not None:
        answer_text += f'<b>Ник</b>: {username}\n'

    answer_text += f'<b>Телеграм ID</b>: {message.from_user.id}\n'
    answer_text += f'<b>Дата регистрации</b>: {register_date_parsed}'

    await message.answer(answer_text, parse_mode='HTML')


@user_mw.authorized_only()
async def account_subscription_info(message: Message):
    """Send message with information about client's subscription."""
    _, title, description, price = await postgesql_db.get_subscription_info_by_clientID(await postgesql_db.get_clientID_by_telegramID(message.from_user.id))
    await message.answer(f'<b>{title}</b>\n\n{description}\n\nСтоимость: {int(price)}₽ в месяц.', parse_mode='HTML')


@user_mw.authorized_only()
async def account_configurations_fsm_start(message: Message, state: FSMContext):
    """Start FSM for account configurations menu and show account configurations menu keyboard."""
    await state.set_state(user_authorized_fsm.AccountMenu.configs)
    await message.answer('Меню конфигураций', reply_markup=user_authorized_kb.config_kb)


@user_mw.authorized_only()
async def account_ref_program_fsm_start(message: Message, state: FSMContext):
    """Start FSM for account referral program menu and show account referral program menu keyboard."""
    await state.set_state(user_authorized_fsm.AccountMenu.ref_program)
    await message.answer(messages.messages_dict['ref_program']['text'], reply_markup=user_authorized_kb.ref_program_kb, parse_mode='HTML')


@user_mw.authorized_only()
async def account_promo_fsm_start(message: Message, state: FSMContext):
    """Start FSM for account promocodes menu and show account promocodes menu keyboard."""
    await state.set_state(user_authorized_fsm.AccountMenu.promo)
    await message.answer('Отлично, теперь введите промокод!', reply_markup=user_authorized_kb.promo_kb)


@user_mw.authorized_only()
async def account_settings_fsm_start(message: Message, state: FSMContext):
    """Start FSM for account settings menu and show account settings menu keyboard."""
    await state.set_state(user_authorized_fsm.AccountMenu.settings)
    await message.answer('Перехожу в настройки', reply_markup=user_authorized_kb.settings_kb)


@user_mw.authorized_only()
async def account_submenu_fsm_cancel(message: Message, state: FSMContext):
    """Cancel FSM state for account submenu and return to account menu keyboard."""
    await state.set_state(user_authorized_fsm.AccountMenu.menu)
    await message.answer('Возврат в личный кабинет', reply_markup=user_authorized_kb.account_kb)


@user_mw.authorized_only()
async def account_configurations_info(message: Message):
    """Send messages with all client's available configurations."""
    configurations_info = await postgesql_db.get_configurations_info(await postgesql_db.get_clientID_by_telegramID(message.from_user.id))
    await message.answer(f'Информация о всех ваших конфигурациях, теперь не нужно искать их по диалогу с ботом!\n\nВсего конфигураций <b>{len(configurations_info)}</b>.',
                         parse_mode='HTML')

    # send message for every configuration
    for file_type, date_of_receipt, os, is_chatgpt_available, name, country, city, bandwidth, ping, telegram_file_id in configurations_info:
        await service_functions.send_configuration(message.from_user.id, file_type, date_of_receipt, os, is_chatgpt_available, name, country, city, bandwidth, ping, telegram_file_id)

    await message.answer('Напоминаю правила (/rules):\n1. Одно устройство - одна конфигурация.\n2. Конфигурациями делиться с другими людьми запрещено!')


@user_mw.authorized_only()
async def account_configurations_submenu_fsm_cancel(message: Message, state: FSMContext):
    """Cancel FSM state for account configurations submenu and return to account configurations menu keyboard."""
    await state.set_state(user_authorized_fsm.AccountMenu.configs)
    await message.answer('Возврат в меню конфигураций', reply_markup=user_authorized_kb.config_kb)


@user_mw.authorized_only()
async def account_configurations_request_fsm_start(message: Message):
    """Start FSM for account configurations request menu, show account configurations request keyboard and request client's platform."""
    # if client's subscription is not active
    if not await postgesql_db.is_subscription_active(message.from_user.id):
        await message.answer('Для запроса новой конфигурации необходимо продлить подписку!')
        return

    answer_text = 'Понадобиться ответить на 3 вопроса, чтобы запросить новую конфигурацию у администратора!\n\n'
    answer_text += f'В данный момент у Вас <b>{await postgesql_db.get_configurations_number(await postgesql_db.get_clientID_by_telegramID(message.from_user.id))}</b> конфигураций.'
    await message.answer(answer_text, parse_mode='HTML')

    await user_authorized_fsm.ConfigMenu.platform.set()
    await message.answer('Выберите свою платформу', reply_markup=user_authorized_kb.config_platform_kb)


@user_mw.authorized_only()
async def account_configurations_request_platform(message: Message, state: FSMContext):
    """Change account configurations request FSM state, save client's platform and request user's OS."""
    async with state.proxy() as data:
        data['platform'] = message.text

    # if client chooses smartphone option
    if message.text == '\U0001F4F1 Смартфон':
        await message.answer('Укажите операционную систему', reply_markup=user_authorized_kb.config_mobile_os_kb)

    # if client chooses pc option
    else:
        await message.answer('Укажите операционную систему', reply_markup=user_authorized_kb.config_desktop_os_kb)

    await state.set_state(user_authorized_fsm.ConfigMenu.os)


@user_mw.authorized_only()
async def account_configurations_request_os(message: Message, state: FSMContext):
    """Change account configurations request FSM state, save client's OS and request client's ChatGPT option."""
    async with state.proxy() as data:
        data['os_name'] = message.text

    await state.set_state(user_authorized_fsm.ConfigMenu.chatgpt)
    await message.answer('Используете ли Вы ChatGPT?', reply_markup=user_authorized_kb.config_chatgpt_kb)


@user_mw.authorized_only()
async def account_configurations_request_chatgpt_info(message: Message):
    """Send message with information about ChatGPT."""
    await message.answer('<b>ChatGPT</b> — нейронная сеть в виде чат-бота, способная отвечать на сложные вопросы и вести осмысленный диалог!',
                         parse_mode='HTML')


@user_mw.authorized_only()
async def account_configurations_request_chatgpt(message: Message, state: FSMContext):
    """Change FSM state to account configurations menu, save client's ChatGPT option and send information about client's new configuration request to admin."""
    async with state.proxy() as data:
        data['chatgpt'] = message.text

        # send information about client's new configuration request to admin
        await service_functions.send_configuration_request_to_admin({'fullname': message.from_user.full_name, 'username': message.from_user.username,
                                                                     'id': message.from_user.id}, data._data, is_new_user=False)

    await message.answer('Отлично! Теперь ждем ответа от разработчика: в скором времени он проверит ваши конфигурации и вышлет новую!',
                         reply_markup=user_authorized_kb.config_kb)
    await message.answer('Пожалуйста, не забывайте, что он тоже человек, и периодически спит (хотя на самом деле крайне редко). Не переживайте, отчет времени истечения подписки начнется только после получения конфигурации!')
    await state.set_state(user_authorized_fsm.AccountMenu.configs)


@user_mw.authorized_only()
async def account_settings_submenu_fsm_cancel(message: Message, state: FSMContext):
    """Cancel FSM state for account settings submenu and return to account settings menu keyboard."""
    await state.set_state(user_authorized_fsm.AccountMenu.settings)
    await message.answer('Возвращаю в настройки', reply_markup=user_authorized_kb.settings_kb)


@user_mw.authorized_only()
async def account_settings_chatgpt(message: Message, state: FSMContext):
    """Change account settings FSM state and show dinamic account settings ChatGPT mode keyboard."""
    await state.set_state(user_authorized_fsm.SettingsMenu.chatgpt)
    await message.answer('Переход в меню настройки режима ChatGPT', reply_markup=await user_authorized_kb.settings_chatgpt(message.from_user.id))


@user_mw.authorized_only()
async def account_settings_chatgpt_mode(message: Message, state: FSMContext):
    """Turn on/off client's ChatGPT mode for answering unrecognized messages."""
    # update ChatGPT mode status and get current ChatGPT mode status
    chatgpt_mode_status: bool = await postgesql_db.update_chatgpt_mode(message.from_user.id)

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
async def account_settings_notifications(message: Message, state: FSMContext):
    """Change account settings FSM state and show dinamic account settings notifications keyboard."""
    client_id = await postgesql_db.get_clientID_by_telegramID(message.from_user.id)
    await state.set_state(user_authorized_fsm.SettingsMenu.notifications)
    await message.answer('Переход в меню настройки уведомлений', reply_markup=await user_authorized_kb.settings_notifications(client_id))


@user_mw.authorized_only()
async def account_settings_notifications_1d(message: Message):
    """Turn on/off client's receiving notifications 1 day before subscription expiration."""
    client_id = await postgesql_db.get_clientID_by_telegramID(message.from_user.id)
    expiration_in_1d_state = await postgesql_db.update_notifications_1d(client_id)

    # if user turned option on
    if expiration_in_1d_state:
        await message.answer('Отправка уведомления за 1 день до срока окончания подписки включена!', reply_markup=await user_authorized_kb.settings_notifications(client_id))

    # if user turned option off
    else:
        await message.answer('Отправка уведомления за 1 день до срока окончания подписки выключена!', reply_markup=await user_authorized_kb.settings_notifications(client_id))


@user_mw.authorized_only()
async def account_settings_notifications_3d(message: Message):
    """Turn on/off client's receiving notifications 3 days before subscription expiration."""
    client_id = await postgesql_db.get_clientID_by_telegramID(message.from_user.id)
    expiration_in_3d_state = await postgesql_db.update_notifications_3d(client_id)

    # if user turned option on
    if expiration_in_3d_state:
        await message.answer('Отправка уведомления за 3 дня до срока окончания подписки включена!', reply_markup=await user_authorized_kb.settings_notifications(client_id))

    # if user turned option off
    else:
        await message.answer('Отправка уведомления за 3 дня до срока окончания подписки выключена!', reply_markup=await user_authorized_kb.settings_notifications(client_id))


@user_mw.authorized_only()
async def account_settings_notifications_7d(message: Message):
    """Turn on/off client's receiving notifications 7 days before subscription expiration."""
    client_id = await postgesql_db.get_clientID_by_telegramID(message.from_user.id)
    expiration_in_7d_state = await postgesql_db.update_notifications_7d(client_id)

    # if user turned option on
    if expiration_in_7d_state:
        await message.answer('Отправка уведомления за 7 дней до срока окончания подписки включена!', reply_markup=await user_authorized_kb.settings_notifications(client_id))

    # if user turned option off
    else:
        await message.answer('Отправка уведомления за 7 дней до срока окончания подписки выключена!', reply_markup=await user_authorized_kb.settings_notifications(client_id))


@user_mw.authorized_only()
async def account_ref_program_info(message: Message):
    """Send message with information about client's participation in referral program."""
    who_invited_client = await postgesql_db.get_invited_by_client_info(message.from_user.id)
    who_was_invited_by_client = await postgesql_db.get_invited_clients_list(message.from_user.id)

    # if someone invited client into project
    if who_invited_client:
        name, username = who_invited_client

        # if someone has username
        if username:
            await message.answer(f'Вы были приглашены пользователем {name} {username}')
        else:
            await message.answer(f'Вы были приглашены пользователем {name}')

    # if nobody invited client into project
    else:
        await message.answer('Ого! Вы сами узнали о существовании данного проекта и зарегистрировались без приглашения от другого пользователя!')

    # if client invited someone into project
    if who_was_invited_by_client:
        answer_message = 'Приглашенные Вами пользователи, которые вступили в проект:\n\n'
        for idx, (name, username) in enumerate(who_was_invited_by_client):

            # if invited client has username
            if name:
                answer_message += f'{idx + 1}. Пользователь {name} {username}\n'
            else:
                answer_message += f'{idx + 1}. Пользователь {name}\n'
        await message.answer(answer_message)

    # if client hasn't invited other clients yet
    else:
        await message.answer('Вы еще не пригласили ни одного пользователя. Рассказывайте о нашем проекте друзьям и получайте бесплатные месяца подписки!')


@user_mw.authorized_only()
async def account_ref_program_invite(message: Message):
    """Send message with random invite text from messages.py."""
    ref_promocode = await postgesql_db.get_referral_promo(message.from_user.id)
    text = choice(messages.messages_dict['ref_program_invites']['text'])
    text = text.replace('<refcode>', '<code>' + ref_promocode + '</code>')
    await message.answer(text, parse_mode='HTML')


@user_mw.authorized_only()
async def account_ref_program_promocode(message: Message):
    """Send message with client's own referral promocode."""
    await message.answer(f'Ваш реферальный промокод: <code>{await postgesql_db.get_referral_promo(message.from_user.id)}</code>', parse_mode='HTML')


@user_mw.authorized_only()
async def account_promo_check(message: Message, state: FSMContext):
    """Check entered promocode is valid, send information about successfuly entered promocode, update subscription period for client.

    If specified promocode is local promocode, it can also change subscription type for client.
    """
    # if promo is referral
    if await postgesql_db.is_referral_promo(message.text):
        await message.answer('К сожалению, вводить реферальные промокоды можно только при регистрации ;(')
        return

    # get information about promocode
    client_id = await postgesql_db.get_clientID_by_telegramID(message.from_user.id)
    global_promo_info = await postgesql_db.get_global_promo_info(message.text)
    local_promo_info = await postgesql_db.get_local_promo_info(message.text)

    # if promo is global and exists in system
    if global_promo_info:
        global_promo_id, *_, bonus_time, bonus_time_parsed = global_promo_info

        # if global promo wasn't entered by client before
        if not await postgesql_db.is_global_promo_already_entered(client_id, global_promo_id):

            # if global promo didn't expire
            if await postgesql_db.is_global_promo_valid(global_promo_id):

                # if global promo still has available activations number
                if await postgesql_db.is_global_promo_has_remaining_activations(global_promo_id):

                    await postgesql_db.insert_client_entered_global_promo(client_id, global_promo_id, bonus_time)
                    await service_functions.send_admin_info_promo_entered(client_id, message.text, 'global')
                    await message.answer(f'Ура! Промокод на {bonus_time_parsed} дней бесплатной подписки принят!', reply_markup=user_authorized_kb.account_kb)
                    await state.set_state(user_authorized_fsm.AccountMenu.menu)

                else:
                    await message.answer('К сожалению, число возможных активаций данного промокода исчерпано :(')

            else:
                await message.answer('К сожалению, срок действия промокода истек :(')

        else:
            await message.answer('Вы уже вводили данный промокод ранее!')

    # if promo is local and exists in system
    elif local_promo_info:
        local_promo_id, *_, bonus_time, bonus_time_parsed, provided_sub_id = local_promo_info

        # if local promo accessible by client
        if await postgesql_db.is_local_promo_accessible(client_id, local_promo_id):

            # if local promo wasn't entered by client before
            if not await postgesql_db.is_local_promo_already_entered(client_id, local_promo_id):

                # if local promo didn't expire
                if await postgesql_db.is_local_promo_valid(local_promo_id):

                    await postgesql_db.insert_client_entered_local_promo(client_id, local_promo_id, bonus_time)
                    await service_functions.send_admin_info_promo_entered(client_id, message.text, 'local')
                    answer_message = f'Ура! Специальный промокод на {bonus_time_parsed} дней бесплатной подписки принят!'

                    # if local promo changes client's subscription
                    if provided_sub_id:
                        await postgesql_db.update_client_subscription(client_id, provided_sub_id)
                        _, title, _, price = await postgesql_db.get_subscription_info_by_subID(provided_sub_id)
                        answer_message += f'\n\nТип вашей подписки сменен на «<b>{title}</b>» со стоимостью {int(price)}₽/мес!'

                    await message.answer(answer_message, parse_mode='HTML', reply_markup=user_authorized_kb.account_kb)
                    await state.set_state(user_authorized_fsm.AccountMenu.menu)

                else:
                    await message.answer('К сожалению, срок действия специального промокода истек :(')

            else:
                await message.answer('Вы уже вводили данный специальный промокод ранее!')

        else:
            await message.answer('К сожалению, Вы не можете использовать данный специальный промокод ((')

    # if promo not found in system
    else:
        await message.answer('Такого промокода нет! Попробуйте ввести его еще раз')


@user_mw.authorized_only()
async def account_promo_info(message: Message):
    """Send message with information about entered by client promocodes."""
    ref_promos, global_promos, local_promos = await postgesql_db.get_client_entered_promos(await postgesql_db.get_clientID_by_telegramID(message.from_user.id))
    await message.answer('Информация о введенных промокодах!')

    answer_message = ''

    # information about entered referral promocode
    if ref_promos:
        ref_promo_phrase, client_creator_name = ref_promos
        answer_message += f"Использованный реферальный промокод:\n<b>{ref_promo_phrase}</b> от пользователя {client_creator_name}.\n\n"

    # information about entered global promocodes
    if global_promos:
        answer_message += 'Использованные общедоступные промокоды:\n'
        for idx, (global_promo_phrase, bonus_time_parsed, date_of_entry_parsed) in enumerate(global_promos):
            answer_message += f"{idx + 1}. Промокод <b>{global_promo_phrase}</b> на {bonus_time_parsed} бесплатных дней подписки. Был введен {date_of_entry_parsed}.\n"
        answer_message += '\n'

    # information about entered local promocodes
    if local_promos:
        answer_message += 'Использованные специальные промокоды:\n'
        for idx, (local_promo_phrase, bonus_time_parsed, date_of_entry_parsed) in enumerate(local_promos):
            answer_message += f"{idx + 1}. Промокод <b>{local_promo_phrase}</b> на {bonus_time_parsed} бесплатных дней подписки. Был введен {date_of_entry_parsed}.\n"
        answer_message += '\n'

    # user hasn't entered promocodes at all
    if answer_message == '':
        await message.answer('Вы еще не вводили ни одного промокода. Следите за новостями!')

    else:
        await message.answer(answer_message, parse_mode='HTML')


@user_mw.authorized_only()
async def show_project_rules(message: Message):
    """Send message with information about project rules."""
    await message.answer(messages.messages_dict['project_rules']['text'], parse_mode='HTML')


@user_mw.authorized_only()
async def restore_payments(message: Message):
    """Try to verify client's payments (per whole time) are successful according to YooMoney information."""

    # get client's initiated payments for all time
    wallet = aiomoney.YooMoneyWallet(YOOMONEY_TOKEN)
    client_id = await postgesql_db.get_clientID_by_telegramID(message.from_user.id)
    client_payments_ids = await postgesql_db.get_paymentIDs(client_id)

    is_payment_found = False
    for [payment_id] in client_payments_ids:

        # if payment wasn't added to db as successful and payment is successful according to Yoomoney:
        if await postgesql_db.get_payment_status(payment_id) == False and await wallet.check_payment_on_successful(payment_id):

            # update payment in db as successful
            months_number = await postgesql_db.get_payment_months_number(payment_id)
            await postgesql_db.update_payment_successful(payment_id, client_id, months_number)

            # answer to a client
            await message.answer(f'Ура! Оплата по заказу с id {payment_id} найдена!')

            # notify admin about successful payment and check referral reward for other client
            await service_functions.notify_admin_payment_success(client_id, months_number)
            await service_functions.check_referral_reward(client_id)

            is_payment_found = True

    if not is_payment_found:
        answer_text = 'К сожалению, я не смог найти оплаченные заказы :/\n\n'
        answer_text += 'Возможно, Вы еще не завершили оплату, либо информация об оплате все еще в пути!\n\n'
        answer_text += 'Если Вы уверены, что оплата была совершена, обратитесь в раздел помощи /help'
        await message.answer(answer_text)


def register_handlers_authorized_client(dp: Dispatcher):
    dp.register_message_handler(subscription_status, Text(equals='Статус подписки'))
    dp.register_message_handler(submenu_fsm_cancel, Text(equals='Возврат в главное меню'), state=[None,
                                                                                                  user_authorized_fsm.AccountMenu.menu,
                                                                                                  user_authorized_fsm.PaymentMenu.menu])
    dp.register_message_handler(sub_renewal_fsm_start, Text(equals='\u2764\uFE0F\u200D\U0001F525 Продлить подписку!'))
    dp.register_message_handler(sub_renewal_months_1, Text(equals='1 месяц'), state=user_authorized_fsm.PaymentMenu.menu)
    dp.register_message_handler(sub_renewal_months_3, Text(equals='3 месяца (-10%)'), state=user_authorized_fsm.PaymentMenu.menu)
    dp.register_message_handler(sub_renewal_months_12, Text(equals='12 месяцев (-15%)'), state=user_authorized_fsm.PaymentMenu.menu)
    dp.register_message_handler(sub_renewal_payment_history, Text(equals='История оплаты'), state=user_authorized_fsm.PaymentMenu.menu)
    dp.register_message_handler(sub_renewal_submenu_fsm_cancel, Text(equals='Отмена оплаты'), state=[None,
                                                                                                     user_authorized_fsm.PaymentMenu.verification])
    dp.register_message_handler(sub_renewal_verification, Text(equals='Проверить оплату'), state=user_authorized_fsm.PaymentMenu.verification)
    dp.register_message_handler(account_fsm_start, Text(equals='Личный кабинет'))
    dp.register_message_handler(account_client_info, Text(equals='О пользователе'), state=user_authorized_fsm.AccountMenu.menu)
    dp.register_message_handler(account_subscription_info, Text(equals='О подписке'), state=user_authorized_fsm.AccountMenu.menu)
    dp.register_message_handler(account_submenu_fsm_cancel, Text(equals='Вернуться'), state=[None,
                                                                                             user_authorized_fsm.AccountMenu.configs,
                                                                                             user_authorized_fsm.AccountMenu.ref_program,
                                                                                             user_authorized_fsm.AccountMenu.settings])
    dp.register_message_handler(account_submenu_fsm_cancel, Text(equals='Отмена ввода'), state=[None,
                                                                                                user_authorized_fsm.AccountMenu.promo])
    dp.register_message_handler(account_ref_program_fsm_start, Text(equals='Реферальная программа'), state=user_authorized_fsm.AccountMenu.menu)
    dp.register_message_handler(account_promo_fsm_start, Text(equals='Ввести промокод'), state=user_authorized_fsm.AccountMenu.menu)
    dp.register_message_handler(account_configurations_fsm_start, Text(equals='Конфигурации'), state=user_authorized_fsm.AccountMenu.menu)
    dp.register_message_handler(account_settings_fsm_start, Text(equals='Настройки'), state=user_authorized_fsm.AccountMenu.menu)
    dp.register_message_handler(account_ref_program_info, Text(equals='Участие в реферальной программе'), state=user_authorized_fsm.AccountMenu.ref_program)
    dp.register_message_handler(account_ref_program_invite, Text(equals='Сгенерировать приглашение *'), state=user_authorized_fsm.AccountMenu.ref_program)
    dp.register_message_handler(account_ref_program_promocode, Text(equals='Показать реферальный промокод'), state=user_authorized_fsm.AccountMenu.ref_program)
    dp.register_message_handler(account_promo_info, Text(equals='Использованные промокоды'), state=user_authorized_fsm.AccountMenu.promo)
    dp.register_message_handler(account_promo_check, state=user_authorized_fsm.AccountMenu.promo)
    dp.register_message_handler(account_configurations_info, Text(equals='Текущие конфигурации'), state=user_authorized_fsm.AccountMenu.configs)
    dp.register_message_handler(account_configurations_submenu_fsm_cancel, Text(equals='Отмена выбора'), state=[None,
                                                                                                                user_authorized_fsm.ConfigMenu.platform,
                                                                                                                user_authorized_fsm.ConfigMenu.os,
                                                                                                                user_authorized_fsm.ConfigMenu.chatgpt])
    dp.register_message_handler(account_configurations_request_fsm_start, Text(equals='Запросить новую конфигурацию'), state=user_authorized_fsm.AccountMenu.configs)
    dp.register_message_handler(account_configurations_request_platform, Text(equals=['\U0001F4F1 Смартфон', '\U0001F4BB ПК']), state=user_authorized_fsm.ConfigMenu.platform)
    dp.register_message_handler(account_configurations_request_os, Text(equals=['Android', 'IOS (IPhone)', 'Windows', 'macOS', 'Linux']), state=user_authorized_fsm.ConfigMenu.os)
    dp.register_message_handler(account_configurations_request_chatgpt_info, Text(equals='Что это?', ignore_case=True), state=user_authorized_fsm.ConfigMenu.chatgpt)
    dp.register_message_handler(account_configurations_request_chatgpt, Text(equals=['Использую', 'Не использую']), state=user_authorized_fsm.ConfigMenu.chatgpt)
    dp.register_message_handler(account_settings_submenu_fsm_cancel, Text(equals='Обратно'), state=[None,
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
