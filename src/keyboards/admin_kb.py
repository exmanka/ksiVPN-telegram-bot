from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from src.services import localization as loc


menu = ReplyKeyboardMarkup(
    resize_keyboard=True,
    keyboard=[
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
        # One-off announcement variant — sends to all users, resets FSM for authorized
        # ones and reapplies user_authorized_kb.menu / user_unauthorized_kb.welcome.
        # Remove together with the matching admin.py handlers after the announcement.
        [KeyboardButton(text=loc.admn.btns['send_message_everyone_with_reset'])],
        [KeyboardButton(text=loc.admn.btns['reset_fsm_2'])],
    ],
)
