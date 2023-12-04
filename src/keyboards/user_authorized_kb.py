from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton


menu_kb = ReplyKeyboardMarkup(resize_keyboard=True).\
    add(KeyboardButton('\u2764\uFE0F\u200D\U0001F525 Продлить подписку!')).\
    add(KeyboardButton('Личный кабинет')).insert(KeyboardButton('Статус подписки')).\
    add(KeyboardButton('Правила')).insert(KeyboardButton('Помощь')).insert(KeyboardButton('О сервисе'))

sub_renewal_kb = ReplyKeyboardMarkup(resize_keyboard=True).\
    add(KeyboardButton('1 месяц')).insert(KeyboardButton('3 месяца (-15%)')).insert(KeyboardButton('12 месяцев (-30%)')).\
    add(KeyboardButton('Указать вручную')).insert(KeyboardButton('История оплаты')).\
    add(KeyboardButton('Возврат в главное меню'))

account_kb = ReplyKeyboardMarkup(resize_keyboard=True).\
    add(KeyboardButton('Реферальная программа')).\
    add(KeyboardButton('Информация о пользователе')).insert(KeyboardButton('Информация о подписке')).\
    add(KeyboardButton('Конфигурации')).insert(KeyboardButton('Ввести промокод')).\
    add(KeyboardButton('Возврат в главное меню'))

config_kb = ReplyKeyboardMarkup(resize_keyboard=True).\
    add(KeyboardButton('Текущие конфигурации')).insert(KeyboardButton('Запросить новую конфигурацию')).\
    add(KeyboardButton('Вернуться'))

config_platform_kb = ReplyKeyboardMarkup(resize_keyboard=True).\
    add(KeyboardButton('\U0001F4F1 Смартфон')).insert(KeyboardButton('\U0001F4BB ПК')).add(KeyboardButton('Отмена выбора'))

config_mobile_os_kb = ReplyKeyboardMarkup(resize_keyboard=True).\
    add(KeyboardButton('Android')).insert(KeyboardButton('IOS (IPhone)')).add(KeyboardButton('Отмена выбора'))

config_desktop_os_kb = ReplyKeyboardMarkup(resize_keyboard=True).\
    add(KeyboardButton('Windows')).insert(KeyboardButton('macOS')).insert(KeyboardButton('Linux')).add(KeyboardButton('Отмена выбора'))

config_chatgpt_kb = ReplyKeyboardMarkup(resize_keyboard=True).\
    add(KeyboardButton('Использую')).insert(KeyboardButton('Не использую')).insert(KeyboardButton('Что это?')).\
    add(KeyboardButton('Отмена выбора'))

promo_kb = ReplyKeyboardMarkup(resize_keyboard=True).\
    add(KeyboardButton('Использованные промокоды')).add(KeyboardButton('Отмена ввода'))

ref_program_kb = ReplyKeyboardMarkup(resize_keyboard=True).\
    add(KeyboardButton('Участие в реферальной программе')).\
    add(KeyboardButton('Сгенерировать приглашение *')).insert(KeyboardButton('Показать реферальный промокод')).\
    add(KeyboardButton('Вернуться'))