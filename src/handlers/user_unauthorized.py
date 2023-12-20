from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Text
from src.middlewares import user_mw
from src.keyboards import user_unauthorized_kb
from src.states import user_unauthorized_fsm
from src.database import postgesql_db
from src.services import service_functions


@user_mw.unauthorized_only()
async def fsm_cancel(message: types.Message, state: FSMContext):
    """Cancel FSM state for registration."""
    await state.finish()
    await message.answer('Возврат в главное меню', reply_markup=user_unauthorized_kb.welcome_kb)


@user_mw.unauthorized_only()
async def authorization_fsm_start(message: types.Message):
    """Start FSM for registration and request user's platform."""
    await message.answer('Для подключения мне необходимо определить Вашу конфигурацию.\n\n<b>Задам 4 коротких вопроса!</b>', parse_mode='HTML')
    await message.answer('Выберите свою платформу', reply_markup=user_unauthorized_kb.reg_platform_kb)
    await user_unauthorized_fsm.RegistrationFSM.platform.set()


@user_mw.unauthorized_only()
async def authorization_take_platform(message: types.Message, state: FSMContext):
    """Change FSM state, save user's platform and request user's OS."""
    async with state.proxy() as data:
        data['platform'] = message.text
    
    # if user choose smartphone option
    if message.text == '\U0001F4F1 Смартфон':
        await message.answer('Укажите операционную систему', reply_markup=user_unauthorized_kb.reg_mobile_os_kb)

    # if user choose pc option
    else:
        await message.answer('Укажите операционную систему', reply_markup=user_unauthorized_kb.reg_desktop_os_kb)

    await state.set_state(user_unauthorized_fsm.RegistrationFSM.os)


@user_mw.unauthorized_only()
async def authorization_take_os(message: types.Message, state: FSMContext):
    """Change FSM state, save user's OS and request user's ChatGPT option."""
    async with state.proxy() as data:
        data['os_name'] = message.text

    await message.answer('Используете ли Вы ChatGPT?', reply_markup=user_unauthorized_kb.reg_chatgpt_kb)
    await state.set_state(user_unauthorized_fsm.RegistrationFSM.chatgpt)


@user_mw.unauthorized_only()
async def authorization_show_info_chatgpt(message: types.Message):
    """Show information about ChatGPT."""
    await message.answer('<b>ChatGPT</b> — нейронная сеть в виде чат-бота, способная отвечать на сложные вопросы и вести осмысленный диалог!',
                         parse_mode='HTML')


@user_mw.unauthorized_only()
async def authorization_take_chatgpt(message: types.Message, state: FSMContext):
    """Change FSM state, save user's ChatGPT option and request user's referral promo."""
    async with state.proxy() as data:
        data['chatgpt'] = message.text

    await message.answer('И последний шаг: введите реферальный промокод, если он имеется', reply_markup=user_unauthorized_kb.reg_ref_promo_kb)
    await state.set_state(user_unauthorized_fsm.RegistrationFSM.promo)


@user_mw.unauthorized_only()
async def authorization_promo_yes(message: types.Message, state: FSMContext):
    """Check entered referral promocode, notify old client about new client used his referral promocode, complete authorization."""

    # if referral promocode exists in system
    if await postgesql_db.is_referral_promo(message.text):
        async with state.proxy() as data:
            data['promo'] = message.text

        # send information to old client that new client joined project by his referral promocode
        _, client_creator_id, provided_sub_id, _, bonus_time_parsed = await postgesql_db.get_refferal_promo_info_by_phrase(message.text)
        await service_functions.notify_client_new_referal(client_creator_id, message.from_user.first_name, message.from_user.username)

        # send information about promocode bonus time to new client
        client_creator_name, *_ = await postgesql_db.get_client_info_by_clientID(client_creator_id)
        await message.answer(f'Промокод от пользователя {client_creator_name}, дающий {bonus_time_parsed} дней бесплатной подписки, принят!\n\n', parse_mode='HTML')

        # send information about subscription available by referral promocode
        _, title, description, price = await postgesql_db.get_subscription_info_by_subID(provided_sub_id)
        answer_message = 'Информация о Вашей подписке:\n\n'
        answer_message += f'<b>{title}</b>\n'
        answer_message += f'{description}\n\n'
        answer_message += f'Стоимость: {int(price)}₽ в месяц.'
        await message.answer(answer_message, parse_mode='HTML')

        # complete authorization
        await service_functions.authorization_complete(message, state)

    # if referral promocode wasn't recognized
    else:
        await message.answer('Такого промокода нет! Попробуйте ввести его еще раз')
        async with state.proxy() as data:
            data['promo'] = None


@user_mw.unauthorized_only()
async def authorization_promo_no(message: types.Message, state: FSMContext):
    """Complete authorization without referral promocode."""
    async with state.proxy() as data:
        data['promo'] = None

    await service_functions.authorization_complete(message, state)
    await message.answer('<b>Чтобы получить конфигурацию, Вам нужно продлить подписку!</b>', parse_mode='HTML')


def register_handlers_unauthorized_client(dp: Dispatcher):
    dp.register_message_handler(fsm_cancel, Text(equals='Отмена', ignore_case=True), state=[None,
                                                                                            user_unauthorized_fsm.RegistrationFSM.platform,
                                                                                            user_unauthorized_fsm.RegistrationFSM.os,
                                                                                            user_unauthorized_fsm.RegistrationFSM.chatgpt,
                                                                                            user_unauthorized_fsm.RegistrationFSM.promo])
    dp.register_message_handler(authorization_fsm_start, Text(
        equals='\U0001f525 Подключиться!', ignore_case=True))
    dp.register_message_handler(authorization_take_platform, Text(equals=[
                                '\U0001F4F1 Смартфон', '\U0001F4BB ПК']), state=user_unauthorized_fsm.RegistrationFSM.platform)
    dp.register_message_handler(authorization_take_os, Text(equals=[
                                'Android', 'IOS (IPhone)', 'Windows', 'macOS', 'Linux']), state=user_unauthorized_fsm.RegistrationFSM.os)
    dp.register_message_handler(authorization_show_info_chatgpt, Text(
        equals='Что это?', ignore_case=True), state=user_unauthorized_fsm.RegistrationFSM.chatgpt)
    dp.register_message_handler(authorization_take_chatgpt, Text(equals=[
                                'Использую', 'Не использую']), state=user_unauthorized_fsm.RegistrationFSM.chatgpt)
    dp.register_message_handler(authorization_promo_no, Text(
        equals='Нет промокода'), state=user_unauthorized_fsm.RegistrationFSM.promo)
    dp.register_message_handler(
        authorization_promo_yes, state=user_unauthorized_fsm.RegistrationFSM.promo)
