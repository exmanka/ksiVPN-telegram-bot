from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


menu_kb = ReplyKeyboardMarkup(resize_keyboard=True).\
    add(KeyboardButton('Узнать ID файла')).\
    add(KeyboardButton('SQL вставка пользователя')).insert(KeyboardButton('SQL вставка конфигурации')).\
    add(KeyboardButton('Сброс FSM'))