from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


welcome = ReplyKeyboardMarkup(resize_keyboard=True).\
    add(KeyboardButton('\U0001f525 Подключиться!')).\
    add(KeyboardButton('О проекте'))

reg_platform = ReplyKeyboardMarkup(resize_keyboard=True).\
    add(KeyboardButton('\U0001F4F1 Смартфон')).insert(KeyboardButton('\U0001F4BB ПК')).\
    add(KeyboardButton('Отмена'))

reg_mobile_os = ReplyKeyboardMarkup(resize_keyboard=True).\
    add(KeyboardButton('Android')).insert(KeyboardButton('IOS (IPhone)')).\
    add(KeyboardButton('Отмена'))

reg_desktop_os = ReplyKeyboardMarkup(resize_keyboard=True).\
    add(KeyboardButton('Windows')).insert(KeyboardButton('macOS')).insert(KeyboardButton('Linux')).\
    add(KeyboardButton('Отмена'))

reg_chatgpt = ReplyKeyboardMarkup(resize_keyboard=True).\
    add(KeyboardButton('Использую')).insert(KeyboardButton('Не использую')).insert(KeyboardButton('Что это?')).\
    add(KeyboardButton('Отмена'))

reg_ref_promo = ReplyKeyboardMarkup(resize_keyboard=True).\
    add(KeyboardButton('Нет промокода')).\
    add(KeyboardButton('Отмена'))
