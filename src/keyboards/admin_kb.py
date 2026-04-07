from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from src.services import localization as loc


menu = ReplyKeyboardMarkup(
    resize_keyboard=True,
    keyboard=[
        [
            KeyboardButton(text=loc.admn.btns['sql_insert_config']),
            KeyboardButton(text=loc.admn.btns['sql_insert_client']),
            KeyboardButton(text=loc.admn.btns['sql_query']),
        ],
        [
            KeyboardButton(text=loc.admn.btns['get_file_id']),
            KeyboardButton(text=loc.admn.btns['clients_info']),
            KeyboardButton(text=loc.admn.btns['show_earnings']),
        ],
        [
            KeyboardButton(text=loc.admn.btns['send_message']),
            KeyboardButton(text=loc.admn.btns['show_logs']),
        ],
        [KeyboardButton(text=loc.admn.btns['reset_fsm_1'])],
    ],
)

notification = ReplyKeyboardMarkup(
    resize_keyboard=True,
    keyboard=[
        [
            KeyboardButton(text=loc.admn.btns['send_message_everyone']),
            KeyboardButton(text=loc.admn.btns['send_message_selected']),
        ],
        [KeyboardButton(text=loc.admn.btns['reset_fsm_2'])],
    ],
)

sql_query = ReplyKeyboardMarkup(
    resize_keyboard=True,
    keyboard=[[KeyboardButton(text=loc.admn.btns['reset_fsm_2'])]],
)


async def configuration_inline(telegram_id: int, os_alias: str) -> InlineKeyboardMarkup:
    """Return dynamic inline keyboard with telegram_id and os alias encoded in callback_data."""
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(
            text=loc.admn.btns['config_answer_inline'],
            callback_data=f'{telegram_id}:{os_alias}',
        )]]
    )
