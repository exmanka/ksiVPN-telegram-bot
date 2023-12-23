from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton


menu = ReplyKeyboardMarkup(resize_keyboard=True).\
    add(KeyboardButton('_SQL_вставка_конфигурации')).insert(KeyboardButton('_SQL_вставка_пользователя')).insert(KeyboardButton('_узнать_id_файла')).\
    add(KeyboardButton('_отправка_сообщений')).\
    add(KeyboardButton('* Заработок за месяц')).\
    add(KeyboardButton('_сброс_FSM'))

notification = ReplyKeyboardMarkup(resize_keyboard=True).\
    add(KeyboardButton('_отправить_всем')).insert(KeyboardButton('_отправить_избранным')).\
    add(KeyboardButton('_вернуться'))


async def configuration(telegram_id: int) -> InlineKeyboardMarkup:
    """Return dynamic inline keyboard with specified telegram_id as callback_data."""
    return InlineKeyboardMarkup().add(InlineKeyboardButton('Ответить', callback_data=telegram_id))
