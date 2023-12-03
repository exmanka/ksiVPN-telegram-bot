from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton


menu_kb = ReplyKeyboardMarkup(resize_keyboard=True)
menu_kb.add(KeyboardButton('\u2764\uFE0F\u200D\U0001F525 Продлить подписку!')).\
    add(KeyboardButton('Личный кабинет')).insert(KeyboardButton('Статус подписки')).\
    add(KeyboardButton('Правила')).insert(KeyboardButton('Помощь')).insert(KeyboardButton('О сервисе'))

account_kb = ReplyKeyboardMarkup(resize_keyboard=True)
account_kb.add(KeyboardButton('Реферальная программа')).\
    add(KeyboardButton('Информация о пользователе')).insert(KeyboardButton('Информация о подписке')).\
    add(KeyboardButton('Конфигурации')).insert(KeyboardButton('Ввести промокод')).\
    add(KeyboardButton('Возврат в главное меню'))

promo_kb = ReplyKeyboardMarkup(resize_keyboard=True).add(KeyboardButton('Использованные промокоды')).add(KeyboardButton('Отмена ввода'))

ref_program_kb = ReplyKeyboardMarkup(resize_keyboard=True).add(KeyboardButton('Участие в реферальной программе')).\
    add(KeyboardButton('Сгенерировать приглашение *')).insert(KeyboardButton('Показать реферальный промокод')).\
    add(KeyboardButton('Вернуться'))