from bot_init import bot, YOOMONEY_TOKEN
from aiogram import types, Dispatcher
from random import choice
from asyncio import sleep
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Text
from src.keyboards import user_authorized_kb
from src.database import postgesql_db
from src.services.messages import messages_dict
from src.states import user_authorized_fsm
from src.middlewares import user_mw
from src.handlers.admin import send_user_info
from src.services.aiomoney import YooMoneyWallet, PaymentSource


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
            

@user_mw.authorized_only()
async def subscription_status(message: types.Message):
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
async def sub_renewal_months_1(message: types.Message, state: FSMContext):

    # get client_id by telegramID
    client_id = postgesql_db.find_clientID_by_telegramID(message.from_user.id)[0]

    # get client's sub info
    sub_id, sub_title, _, sub_price = postgesql_db.show_subscription_info(client_id)[0]

    # count payment sum
    months_number = 1
    discount = 0.0
    payment_price = sub_price * months_number * (1 - discount)

    # create entity in db table payments and getting payment_id
    payment_id = postgesql_db.insert_user_payment(client_id, sub_id, payment_price, months_number)[0]

    # use aiomoney for payment link creation
    wallet = YooMoneyWallet(YOOMONEY_TOKEN)
    payment_form = await wallet.create_payment_form(
            amount_rub=2,
            unique_label=payment_id,
            payment_source=PaymentSource.YOOMONEY_WALLET,
            success_redirect_url="https://github.com/fofmow/aiomoney"
        )

    # answer with ReplyKeyboardMarkup
    await message.answer('Ура, жду оплаты подписки', reply_markup=user_authorized_kb.sub_renewal_verification_kb)
    await state.set_state(user_authorized_fsm.PaymentMenu.verification)

    # answer with InlineKeyboardMarkup with link to payment
    answer_message = f'Подписка: <b>{sub_title}</b>\nПродление на {months_number} месяц.\n\n<b>Сумма к оплате: {payment_price}₽</b>\n\nУникальный идентификатор платежа: {payment_id}.'
    await message.answer(answer_message, parse_mode='HTML',
                         reply_markup=InlineKeyboardMarkup().\
                            add(InlineKeyboardButton('Оплатить', url=payment_form.link_for_customer)))
    
    # run payment autochecker for 505 seconds
    client_last_payment_status = await autocheck_payment_status(payment_id)

    # if autochecker returns successful payment info
    if client_last_payment_status == 'success':
        postgesql_db.update_payment_successful(payment_id, client_id, months_number)
        await state.set_state(user_authorized_fsm.PaymentMenu.menu)
        await message.answer(f'Оплата произведена успешно!\n\nid: {payment_id}', reply_markup=user_authorized_kb.sub_renewal_kb)

@user_mw.authorized_only()
async def sub_renewal_months_3(message: types.Message, state: FSMContext):
    pass

@user_mw.authorized_only()
async def sub_renewal_months_12(message: types.Message, state: FSMContext):
    pass

@user_mw.authorized_only()
async def sub_renewal_submenu_cm_cancel(message: types.Message, state: FSMContext):
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
    user_info = postgesql_db.show_user_info(message.from_user.id)[0]
    tmp_string = f'Вот что я о Вас знаю:\n\nИмя: {user_info[0]}\n'

    # if user has surname
    if not user_info[1]:
        tmp_string += f'Фамилия: {user_info[0][1]}\n'

    # if user has username
    if not user_info[2]:
        tmp_string += f'Ник: @{user_info[2]}\n'

    tmp_string += f'Телеграм ID: {user_info[3]}\nДата регистрации: {user_info[4]}'
    await message.answer(tmp_string)

@user_mw.authorized_only()
async def account_subscription_info(message: types.Message):
    subscription_info = postgesql_db.show_subscription_info(postgesql_db.find_clientID_by_telegramID(message.from_user.id)[0])[0]
    await message.answer(f'<b>{subscription_info[0]}</b>\n\n{subscription_info[1]}\n\nСтоимость: {subscription_info[2]}₽ в месяц.', parse_mode='HTML')

@user_mw.authorized_only()
async def account_configurations(message: types.Message, state: FSMContext):
    await state.set_state(user_authorized_fsm.AccountMenu.configs)
    await message.answer('Меню конфигураций', reply_markup=user_authorized_kb.config_kb)

@user_mw.authorized_only()
async def account_ref_program(message: types.Message, state:FSMContext):
    await state.set_state(user_authorized_fsm.AccountMenu.ref_program)
    await message.answer(messages_dict['ref_program']['text'], reply_markup=user_authorized_kb.ref_program_kb, parse_mode='HTML')

@user_mw.authorized_only()
async def account_promo(message: types.Message, state: FSMContext):
    await state.set_state(user_authorized_fsm.AccountMenu.promo)
    await message.answer('Отлично, теперь введите промокод!', reply_markup=user_authorized_kb.promo_kb)

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

    for config in configurations_info:
        answer_text = ''
        answer_text += f'<b>Создана</b>: {config[1]}\n'

        # creating answer text with ChatGPT option
        if config[3]:
            answer_text += f'<b>Платформа</b>: {config[2]} с доступом к ChatGPT\n'

        # creating answer text without ChatGPT option
        else:
            answer_text += f'<b>Платформа</b>: {config[2]}\n'

        answer_text += f'<b>Протокол</b>: {config[4]}\n'
        answer_text += f'<b>Локация VPN</b>: {config[5]}, {config[6]}, скорость до {config[7]} Мбит/с, ожидаемый пинг {config[8]} мс.'

        # if config was generated as photo
        if config[0] == 'photo':
            await bot.send_photo(message.from_user.id, config[9], answer_text, parse_mode='HTML', protect_content=True)

        # if config was generated as document
        elif config[0] == 'document':
            await bot.send_document(message.from_user.id, config[9], caption=answer_text, parse_mode='HTML', protect_content=True)

        # if config was generated as link
        else:
            answer_text = f'<code>{config[9]}</code>\n\n' + answer_text
            await bot.send_message(message.from_user.id, answer_text, parse_mode='HTML')

    await message.answer('Напоминаю правила (/rules):\n1. Одно устройство - одна конфигурация.\n2. Конфигурациями делиться с другими людьми запрещено!')

@user_mw.authorized_only()
async def account_configurations_submenu_cm_cancel(message: types.Message, state: FSMContext):
    await state.set_state(user_authorized_fsm.AccountMenu.configs)
    await message.answer('Возврат в меню конфигураций', reply_markup=user_authorized_kb.config_kb)

@user_mw.authorized_only()
async def account_configurations_request_cm_start(message: types.Message):
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

    
    await message.answer(f'Отлично! Теперь ждем ответа от разработчика: в скором времени он проверит Вашу регистрацию и вышлет конфигурацию!',
                            reply_markup=user_authorized_kb.config_kb)
    await message.answer(f'Пожалуйста, не забывайте, что он тоже человек, и периодически спит (хотя на самом деле крайне редко)')

    await state.set_state(user_authorized_fsm.AccountMenu.configs)

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
                    postgesql_db.insert_user_entered_local_promo(client_id, promo_local_id[0], promo_local_bonus_time[0])
                    await message.answer(f'Ура! Специальный промокод на {promo_local_bonus_time[1]} дней бесплатной подписки принят!', reply_markup=user_authorized_kb.account_kb)
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
    dp.register_message_handler(sub_renewal_months_3, Text(equals='3 месяца (-15%)'), state=user_authorized_fsm.PaymentMenu.menu)
    dp.register_message_handler(sub_renewal_months_12, Text(equals='12 месяцев (-30%)'), state=user_authorized_fsm.PaymentMenu.menu)
    dp.register_message_handler(sub_renewal_submenu_cm_cancel, Text(equals='Отмена оплаты'), state=[None,
                                                                                                    user_authorized_fsm.PaymentMenu.verification])
    dp.register_message_handler(sub_renewal_verification, Text(equals='Проверить оплату'), state=user_authorized_fsm.PaymentMenu.verification)
    dp.register_message_handler(account_cm_start, Text(equals='Личный кабинет'))
    dp.register_message_handler(account_user_info, Text(equals='Информация о пользователе'), state=user_authorized_fsm.AccountMenu.menu)
    dp.register_message_handler(account_subscription_info, Text(equals='Информация о подписке'), state=user_authorized_fsm.AccountMenu.menu)
    dp.register_message_handler(account_configurations, Text(equals='Конфигурации'), state=user_authorized_fsm.AccountMenu.menu)
    dp.register_message_handler(account_ref_program, Text(equals='Реферальная программа'), state=user_authorized_fsm.AccountMenu.menu)
    dp.register_message_handler(account_promo, Text(equals='Ввести промокод'), state=user_authorized_fsm.AccountMenu.menu)
    dp.register_message_handler(account_submenu_cm_cancel, Text(equals='Вернуться'), state=[None,
                                                                                            user_authorized_fsm.AccountMenu.configs,
                                                                                            user_authorized_fsm.AccountMenu.ref_program])
    dp.register_message_handler(account_submenu_cm_cancel, Text(equals='Отмена ввода'), state=[None,
                                                                                               user_authorized_fsm.AccountMenu.promo])
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
    dp.register_message_handler(show_project_rules, Text(equals='Правила'))
    dp.register_message_handler(show_project_rules, commands=['rules'], state='*')
    dp.register_message_handler(restore_payments, commands=['restore_payments'], state='*')