from bot_init import bot
from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Text
from src.database import postgesql_db
from src.keyboards import user_unauthorized_kb
from src.middlewares import user_mw
from src.states import user_unauthorized_fsm
from src.handlers.admin import send_user_info
from src.keyboards.user_authorized_kb import menu_kb
from src.services.messages import messages_dict
from src.services import service_functions


@user_mw.unauthorized_only()
async def fsm_cancel(message: types.Message, state: FSMContext):
    """Cancel finite-state machine state for registration."""
    await state.finish()
    await message.answer('Возврат в главное меню', reply_markup=user_unauthorized_kb.welcome_kb)

@user_mw.unauthorized_only()
async def authorization_fsm_start(message: types.Message):
    await message.answer('Для подключения мне необходимо определить Вашу конфигурацию.\n\n<b>Задам 4 коротких вопроса!</b>', parse_mode='HTML')
    await user_unauthorized_fsm.RegistrationFSM.platform.set()
    await message.answer('Выберите свою платформу', reply_markup=user_unauthorized_kb.reg_platform_kb)

@user_mw.unauthorized_only()
async def authorization_take_platform(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['platform'] = message.text

    if message.text == '\U0001F4F1 Смартфон':
        await message.answer('Укажите операционную систему', reply_markup=user_unauthorized_kb.reg_mobile_os_kb)
    else:
        await message.answer('Укажите операционную систему', reply_markup=user_unauthorized_kb.reg_desktop_os_kb)
    
    await state.set_state(user_unauthorized_fsm.RegistrationFSM.os)

@user_mw.unauthorized_only()
async def authorization_take_os(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['os_name'] = message.text

    await state.set_state(user_unauthorized_fsm.RegistrationFSM.chatgpt)
    await message.answer('Используете ли Вы ChatGPT?', reply_markup=user_unauthorized_kb.reg_chatgpt_kb)

@user_mw.unauthorized_only()
async def authorization_show_info_chatgpt(message: types.Message):
    await message.answer('<b>ChatGPT</b> — нейронная сеть в виде чат-бота, способная отвечать на сложные вопросы и вести осмысленный диалог!',
                            parse_mode='HTML')

@user_mw.unauthorized_only()
async def authorization_take_chatgpt(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['chatgpt'] = message.text

    await state.set_state(user_unauthorized_fsm.RegistrationFSM.promo)
    await message.answer('И последний шаг: введите реферальный промокод, если он имеется', reply_markup=user_unauthorized_kb.reg_ref_promo_kb)

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

@user_mw.unauthorized_only()
async def authorization_promo_yes(message: types.Message, state: FSMContext):
    if await postgesql_db.is_referral_promo(message.text):
        async with state.proxy() as data:
            data['promo'] = message.text

        _, client_creator_id, provided_sub_id, _, bonus_time_parsed = await postgesql_db.get_refferal_promo_info_by_phrase(message.text)
        client_creator_name, *_ = await postgesql_db.get_client_info_by_clientID(client_creator_id)
        _, title, description, price = await postgesql_db.get_subscription_info_by_subID(provided_sub_id)
        await service_functions.notify_client_new_referal(client_creator_id, message.from_user.first_name, message.from_user.username)

        await message.answer(f'Промокод от пользователя {client_creator_name}, дающий {bonus_time_parsed} дней бесплатной подписки, принят!\n\n', parse_mode='HTML')

        answer_message = 'Информация о Вашей подписке:\n\n'
        answer_message += f'<b>{title}</b>\n'
        answer_message += f'{description}\n\n'
        answer_message += f'Стоимость: {int(price)}₽ в месяц.'

        await message.answer(answer_message, parse_mode='HTML')
        
        await authorization_complete(message, state)
    else:
        await message.answer('Такого промокода нет! Попробуйте ввести его еще раз')

        async with state.proxy() as data:
            data['promo'] = None

@user_mw.unauthorized_only()
async def authorization_promo_no(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['promo'] = None

    await authorization_complete(message, state)
    await message.answer('<b>Чтобы получить конфигурацию, Вам нужно продлить подписку!</b>', parse_mode='HTML')

def register_handlers_unauthorized_client(dp : Dispatcher):
    dp.register_message_handler(fsm_cancel, Text(equals='Отмена', ignore_case=True), state=[None,
                                                                                           user_unauthorized_fsm.RegistrationFSM.platform,
                                                                                           user_unauthorized_fsm.RegistrationFSM.os,
                                                                                           user_unauthorized_fsm.RegistrationFSM.chatgpt,
                                                                                           user_unauthorized_fsm.RegistrationFSM.promo])
    dp.register_message_handler(authorization_fsm_start, Text(equals='\U0001f525 Подключиться!', ignore_case=True))
    dp.register_message_handler(authorization_take_platform, Text(equals=['\U0001F4F1 Смартфон', '\U0001F4BB ПК']), state=user_unauthorized_fsm.RegistrationFSM.platform)
    dp.register_message_handler(authorization_take_os, Text(equals=['Android', 'IOS (IPhone)', 'Windows', 'macOS', 'Linux']), state=user_unauthorized_fsm.RegistrationFSM.os)
    dp.register_message_handler(authorization_show_info_chatgpt, Text(equals='Что это?', ignore_case=True), state=user_unauthorized_fsm.RegistrationFSM.chatgpt)
    dp.register_message_handler(authorization_take_chatgpt, Text(equals=['Использую', 'Не использую']), state=user_unauthorized_fsm.RegistrationFSM.chatgpt)
    dp.register_message_handler(authorization_promo_no, Text(equals='Нет промокода'), state=user_unauthorized_fsm.RegistrationFSM.promo)
    dp.register_message_handler(authorization_promo_yes, state=user_unauthorized_fsm.RegistrationFSM.promo)