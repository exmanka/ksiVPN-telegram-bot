from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from src.database import postgesql_db


menu_kb = ReplyKeyboardMarkup(resize_keyboard=True).\
    add(KeyboardButton('\u2764\uFE0F\u200D\U0001F525 Продлить подписку!')).\
    add(KeyboardButton('Статус подписки')).insert(KeyboardButton('Личный кабинет')).\
    add(KeyboardButton('Правила')).insert(KeyboardButton('Помощь')).insert(KeyboardButton('О сервисе'))

sub_renewal_kb = ReplyKeyboardMarkup(resize_keyboard=True).\
    add(KeyboardButton('1 месяц')).insert(KeyboardButton('3 месяца (-10%)')).insert(KeyboardButton('12 месяцев (-15%)')).\
    add(KeyboardButton('История оплаты')).\
    add(KeyboardButton('Возврат в главное меню'))

sub_renewal_verification_kb = ReplyKeyboardMarkup(resize_keyboard=True).\
    add(KeyboardButton('Проверить оплату')).\
    add(KeyboardButton('Отмена оплаты'))

account_kb = ReplyKeyboardMarkup(resize_keyboard=True).\
    add(KeyboardButton('Реферальная программа')).\
    add(KeyboardButton('О пользователе')).insert(KeyboardButton('О подписке')).\
    add(KeyboardButton('Конфигурации')).insert(KeyboardButton('Ввести промокод')).insert(KeyboardButton('Настройки')).\
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

settings_kb = ReplyKeyboardMarkup(resize_keyboard=True).\
    add(KeyboardButton('Режим ChatGPT')).insert(KeyboardButton('Уведомления')).\
    add(KeyboardButton('Вернуться'))

async def settings_notifications(client_id: int) -> ReplyKeyboardMarkup:
    sub_expires_in_1_day, sub_expires_in_3_days, sub_expires_in_7_days = await postgesql_db.get_notifications_info(client_id)
    settings_notifications_kb = ReplyKeyboardMarkup(resize_keyboard=True)

    # if client turned on notifications one day before subscription expires
    if sub_expires_in_1_day:
        settings_notifications_kb.add(KeyboardButton('Выключить за 1 день'))
    # if client turned off notifications one day before subscription expires
    else:
        settings_notifications_kb.add(KeyboardButton('Включить за 1 день'))

    # if client turned on notifications 3 days before subscription expires
    if sub_expires_in_3_days:
        settings_notifications_kb.insert(KeyboardButton('Выключить за 3 дня'))
    # if client turned off notifications 3 days before subscription expires
    else:
        settings_notifications_kb.insert(KeyboardButton('Включить за 3 дня'))

    # if client turned on notifications 7 days before subscription expires
    if sub_expires_in_7_days:
        settings_notifications_kb.insert(KeyboardButton('Выключить за 7 дней'))
    # if client turned off notifications 7 days before subscription expires
    else:
        settings_notifications_kb.insert(KeyboardButton('Включить за 7 дней'))

    settings_notifications_kb.add(KeyboardButton('Обратно'))

    return settings_notifications_kb

async def settings_chatgpt(telegram_id: int) -> ReplyKeyboardMarkup:
    settings_chatgpt_kb = ReplyKeyboardMarkup(resize_keyboard=True)

    # if client turned on ChatGPT mode for bot
    if await postgesql_db.get_chatgpt_mode_status(telegram_id):
        settings_chatgpt_kb.add(KeyboardButton('Выключить'))

    # if client turned off ChatGPT mode for bot
    else:
        settings_chatgpt_kb.add(KeyboardButton('Включить'))

    settings_chatgpt_kb.add(KeyboardButton('Обратно'))

    return settings_chatgpt_kb
