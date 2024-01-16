from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from src.services import localization as loc


menu = ReplyKeyboardMarkup(resize_keyboard=True).\
    add(KeyboardButton(loc.admn.btns['sql_insert_config'])).insert(KeyboardButton(loc.admn.btns['sql_insert_client'])).insert(KeyboardButton(loc.admn.btns['get_file_id'])).\
    add(KeyboardButton(loc.admn.btns['send_message'])).insert(KeyboardButton(loc.admn.btns['clients_info'])).\
    add(KeyboardButton(loc.admn.btns['show_earnings'])).\
    add(KeyboardButton(loc.admn.btns['reset_fsm_1']))

notification = ReplyKeyboardMarkup(resize_keyboard=True).\
    add(KeyboardButton(loc.admn.btns['send_message_everyone'])).insert(KeyboardButton(loc.admn.btns['send_message_selected'])).\
    add(KeyboardButton(loc.admn.btns['reset_fsm_2']))


async def configuration_inline(telegram_id: int) -> InlineKeyboardMarkup:
    """Return dynamic inline keyboard with specified telegram_id as callback_data."""
    return InlineKeyboardMarkup().add(InlineKeyboardButton(loc.admn.btns['config_answer_inline'], callback_data=telegram_id))
