from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton


# Замещение клавиатуры на кнопки, resize_keyboard - изменение размера кнопок под размер текста, one_time_keyboard - скрытие клавиатуры после выбора
welcome_kb = ReplyKeyboardMarkup(resize_keyboard=True).\
    add(KeyboardButton('\U0001f525 Подключиться!')).\
    add(KeyboardButton('О проекте'))

reg_platform_kb = ReplyKeyboardMarkup(resize_keyboard=True).\
    add(KeyboardButton('\U0001F4F1 Смартфон')).insert(KeyboardButton('\U0001F4BB ПК')).\
    add(KeyboardButton('Отмена'))

reg_mobile_os_kb = ReplyKeyboardMarkup(resize_keyboard=True).\
    add(KeyboardButton('Android')).insert(KeyboardButton('IOS (IPhone)')).\
    add(KeyboardButton('Отмена'))

reg_desktop_os_kb = ReplyKeyboardMarkup(resize_keyboard=True).\
    add(KeyboardButton('Windows')).insert(KeyboardButton('macOS')).insert(KeyboardButton('Linux')).\
    add(KeyboardButton('Отмена'))

reg_chatgpt_kb = ReplyKeyboardMarkup(resize_keyboard=True).\
    add(KeyboardButton('Использую')).insert(KeyboardButton('Не использую')).insert(KeyboardButton('Что это?')).\
    add(KeyboardButton('Отмена'))

reg_ref_promo_kb = ReplyKeyboardMarkup(resize_keyboard=True).\
    add(KeyboardButton('Нет промокода')).\
    add(KeyboardButton('Отмена'))

account_kb = ReplyKeyboardMarkup(resize_keyboard=True).\
    add(KeyboardButton('\u2764\uFE0F\u200D\U0001F525 Продлить подписку!')).\
    add(KeyboardButton('Личный кабинет')).insert(KeyboardButton('Статус подписки')).\
    add(KeyboardButton('Правила')).insert(KeyboardButton('Помощь')).insert(KeyboardButton('О сервисе'))

# reg_ref_promo_kb = InlineKeyboardMarkup()
# reg_ref_promo_kb.add(InlineKeyboardButton('Нет промокода', callback_data='no_ref_promo'))

# add - добавление кнопки на новой строке, insert - добавление кнопки на той же строке.
# kb_client.row(b1, b2, b3) - добавление кнопок в строку
# b2 = KeyboardButton('/info')
# b3 = KeyboardButton('/close_kb')
