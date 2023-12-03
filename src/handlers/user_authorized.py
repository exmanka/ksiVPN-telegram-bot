from bot_init import bot
from aiogram import types, Dispatcher
from random import choice
from aiogram.types import ReplyKeyboardRemove
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Text
from src.keyboards import user_authorized_kb
from src.database import postgesql_db
from src.services.messages import messages_dict
from src.states import user_authorized_fsm
from src.middlewares import user_mw
from src.handlers.admin import send_user_info


async def already_registered_system(message: types.Message):
    await message.answer('Ух ты! Вы уже есть в нашей системе! Телепортируем в личный кабинет!', reply_markup=user_authorized_kb.menu_kb)

@user_mw.authorized_only()
async def subscription_status(message: types.Message):
    if postgesql_db.is_subscription_active(message.from_user.id):
        await message.answer('Подписка активна!')
    else:
        await message.answer('Подписка деактивирована :/')
    
    await message.answer(f'Срок окончания действия подписки: {postgesql_db.show_subscription_expiration_date(message.from_user.id)[0]}.')

@user_mw.authorized_only()
async def account_cm_cancel(message: types.Message, state: FSMContext = None):
    '''
    Return to the menu regardless of whether there is a machine state
    '''

    if state:
        await state.finish()
    await message.answer('Возврат в главное меню', reply_markup=user_authorized_kb.menu_kb)

@user_mw.authorized_only()
async def account_cm_start(message: types.Message):
    await user_authorized_fsm.AccountMenu.account_menu.set()
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
async def account_promo_enter(message: types.Message, state: FSMContext):
    await state.set_state(user_authorized_fsm.AccountMenu.account_promo)
    await message.answer('Отлично, теперь введите промокод!', reply_markup=user_authorized_kb.promo_kb)

@user_mw.authorized_only()
async def account_submenu_cm_cancel(message: types.Message, state: FSMContext):
    '''
    Return to account menu from promocode FSM and referal program FSM
    '''
    
    current_state = await state.get_state()
    if current_state is not None:
        await state.set_state(user_authorized_fsm.AccountMenu.account_menu)

    await message.answer('Возврат в личный кабинет', reply_markup=user_authorized_kb.account_kb)

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
                await state.set_state(user_authorized_fsm.AccountMenu.account_menu)

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
                    await state.set_state(user_authorized_fsm.AccountMenu.account_menu)
                
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
async def account_ref_program(message: types.Message, state:FSMContext):
    await state.set_state(user_authorized_fsm.AccountMenu.account_ref_program)
    await message.answer(messages_dict['ref_program']['text'], reply_markup=user_authorized_kb.ref_program_kb, parse_mode='HTML')
    
@user_mw.authorized_only()
async def show_project_rules(message: types.Message):
    await message.answer(messages_dict['project_rules']['text'], parse_mode='HTML')

def register_handlers_authorized_client(dp: Dispatcher):
    dp.register_message_handler(subscription_status, Text(equals='Статус подписки'))
    dp.register_message_handler(account_cm_cancel, Text(equals='Возврат в главное меню'), state=user_authorized_fsm.AccountMenu.account_menu)
    dp.register_message_handler(account_cm_cancel, Text(equals='Возврат в главное меню'))
    dp.register_message_handler(account_cm_start, Text(equals='Личный кабинет'))
    dp.register_message_handler(account_user_info, Text(equals='Информация о пользователе'), state=user_authorized_fsm.AccountMenu.account_menu)
    dp.register_message_handler(account_subscription_info, Text(equals='Информация о подписке'), state=user_authorized_fsm.AccountMenu.account_menu)
    dp.register_message_handler(account_configurations_info, Text(equals='Конфигурации'), state=user_authorized_fsm.AccountMenu.account_menu)
    dp.register_message_handler(account_ref_program, Text(equals='Реферальная программа'), state=user_authorized_fsm.AccountMenu.account_menu)
    dp.register_message_handler(account_promo_enter, Text(equals='Ввести промокод'), state=user_authorized_fsm.AccountMenu.account_menu)
    dp.register_message_handler(account_submenu_cm_cancel, Text(equals='Отмена ввода'), state=user_authorized_fsm.AccountMenu.account_promo)
    dp.register_message_handler(account_submenu_cm_cancel, Text(equals='Отмена ввода'))
    dp.register_message_handler(account_submenu_cm_cancel, Text(equals='Вернуться'), state=user_authorized_fsm.AccountMenu.account_ref_program)
    dp.register_message_handler(account_submenu_cm_cancel, Text(equals='Вернуться'))
    dp.register_message_handler(account_ref_program_info, Text(equals='Участие в реферальной программе'), state=user_authorized_fsm.AccountMenu.account_ref_program)
    dp.register_message_handler(account_ref_program_invite, Text(equals='Сгенерировать приглашение *'), state=user_authorized_fsm.AccountMenu.account_ref_program)
    dp.register_message_handler(account_ref_program_promocode, Text(equals='Показать реферальный промокод'), state=user_authorized_fsm.AccountMenu.account_ref_program)
    dp.register_message_handler(account_promo_info, Text(equals='Использованные промокоды'), state=user_authorized_fsm.AccountMenu.account_promo)
    dp.register_message_handler(account_promo_check, state=user_authorized_fsm.AccountMenu.account_promo)
    dp.register_message_handler(show_project_rules, Text(equals='Правила'))
    dp.register_message_handler(show_project_rules, commands=['rules'], state='*')