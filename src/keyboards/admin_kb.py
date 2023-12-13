from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton


menu_kb = ReplyKeyboardMarkup(resize_keyboard=True).\
    add(KeyboardButton('_узнать_id_файла')).\
    add(KeyboardButton('_SQL_вставка_пользователя')).insert(KeyboardButton('_SQL_вставка_конфигурации')).\
    add(KeyboardButton('_отправка_сообщений')).\
    add(KeyboardButton('_сброс_FSM'))

notification_kb = ReplyKeyboardMarkup(resize_keyboard=True).\
    add(KeyboardButton('_отправить_всем')).insert(KeyboardButton('_отправить_избранным')).\
    add(KeyboardButton('_вернуться'))

async def configuration(telegram_id: int):
    return InlineKeyboardMarkup().add(InlineKeyboardButton('Ответить', callback_data=telegram_id))