from bot_init import bot
from aiogram import types, Dispatcher
from aiogram.types import ReplyKeyboardRemove
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Text
from src.keyboards import user_unauthorized_kb
from src.database import postgesql_db
from src.states import user_unauthorized_fsm
from src.middlewares import user_mw
from src.handlers.admin import send_user_info
from src.services.messages import messages_dict
from src.handlers.user_authorized import already_registered_system


@user_mw.unauthorized_only()
async def cm_cancel(message: types.Message, state: FSMContext):
    current_state = await state.get_state() # Получаем текущее состояние бота
    if current_state is None:   # Если не находится в каком-либо состоянии
        await message.reply('Извините, в данном состоянии я вас не понимаю \U0001F914')
        return
    
    await state.finish()
    await message.answer('Возврат в главное меню', reply_markup=user_unauthorized_kb.welcome_kb)

async def authorization_cm_start(message: types.Message):
    if postgesql_db.is_user_registered(message.from_user.id):
        await already_registered_system(message)
    else:
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

@user_mw.unauthorized_only()
async def authorization_promo_yes(message: types.Message, state: FSMContext):
    if message.text in ['Masha', 'Maria', 'masha', 'maria']:
        await message.answer('Промокод принят!')
        async with state.proxy() as data:
            data['promo'] = message.text

        async with state.proxy() as data:
            await send_user_info({'fullname': message.from_user.full_name, 'username': message.from_user.username,\
                                'id': message.from_user.id}, data._data)
        
        await message.answer(f'Отлично! Теперь ждем ответа от разработчика: в скором времени он проверит Вашу регистрацию и вышлет конфигурацию!',
                                reply_markup=ReplyKeyboardRemove())
        await message.answer(f'Пожалуйста, не забывайте, что он тоже человек, и периодически спит (хотя на самом деле крайне редко)')

        await state.finish()
    else:
        await message.answer('Такого промокода нет! Попробуйте ввести его еще раз')

@user_mw.unauthorized_only()
async def authorization_promo_no(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['promo'] = 'без_промокода'

    async with state.proxy() as data:
        await send_user_info({'fullname': message.from_user.full_name, 'username': message.from_user.username,\
                                'id': message.from_user.id}, data._data)

    await message.answer(f'Отлично! Теперь ждем ответа от разработчика: в скором времени он проверит Вашу регистрацию и вышлет конфигурацию!',
                            reply_markup=ReplyKeyboardRemove())
    await message.answer(f'Пожалуйста, не забывайте, что он тоже человек, и периодически спит (хотя на самом деле крайне редко)')

    await state.finish()

async def command_start(message : types.Message):
    await bot.send_photo(message.from_user.id, messages_dict['hello_message']['img_id'], messages_dict['hello_message']['text'], reply_markup=user_unauthorized_kb.welcome_kb)

    
# async def close_keyboard(message : types.Message):
#     await bot.send_message(message.from_user.id, 'Закрываю клавиатуру!', reply_markup=ReplyKeyboardRemove())  # Удаление клавиатуры


def register_handlers_unauthorized_client(dp : Dispatcher):
    # dp.register_message_handler(close_keyboard, commands=['close_kb'])
    dp.register_message_handler(cm_cancel, Text(equals='Cancel', ignore_case=True), state="*")
    dp.register_message_handler(cm_cancel, Text(equals='Отмена', ignore_case=True), state="*")
    dp.register_message_handler(authorization_cm_start, Text(equals='\U0001f525 Подключиться!', ignore_case=True))
    dp.register_message_handler(authorization_take_platform, Text(equals=['\U0001F4F1 Смартфон', '\U0001F4BB ПК']), state=user_unauthorized_fsm.RegistrationFSM.platform)
    dp.register_message_handler(authorization_take_os, Text(equals=['Android', 'IOS (IPhone)', 'Windows', 'macOS', 'Linux']), state=user_unauthorized_fsm.RegistrationFSM.os)
    dp.register_message_handler(authorization_show_info_chatgpt, Text(equals='Что это?', ignore_case=True), state=user_unauthorized_fsm.RegistrationFSM.chatgpt)
    dp.register_message_handler(authorization_take_chatgpt, Text(equals=['Использую', 'Не использую']), state=user_unauthorized_fsm.RegistrationFSM.chatgpt)
    dp.register_message_handler(authorization_promo_no, Text(equals='Нет промокода'), state=user_unauthorized_fsm.RegistrationFSM.promo)
    dp.register_message_handler(authorization_promo_yes, state=user_unauthorized_fsm.RegistrationFSM.promo)
    dp.register_message_handler(command_start, commands=['start'])