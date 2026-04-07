from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from src.services import localization as loc


welcome = ReplyKeyboardMarkup(
    resize_keyboard=True,
    keyboard=[
        [KeyboardButton(text=loc.unauth.btns['join'])],
        [KeyboardButton(text=loc.unauth.btns['project_info'])],
    ],
)

reg_platform = ReplyKeyboardMarkup(
    resize_keyboard=True,
    keyboard=[
        [KeyboardButton(text=loc.unauth.btns['smartphone']), KeyboardButton(text=loc.unauth.btns['pc'])],
        [KeyboardButton(text=loc.unauth.btns['cancel'])],
    ],
)

reg_mobile_os = ReplyKeyboardMarkup(
    resize_keyboard=True,
    keyboard=[
        [KeyboardButton(text=loc.unauth.btns['android']), KeyboardButton(text=loc.unauth.btns['ios'])],
        [KeyboardButton(text=loc.unauth.btns['cancel'])],
    ],
)

reg_desktop_os = ReplyKeyboardMarkup(
    resize_keyboard=True,
    keyboard=[
        [
            KeyboardButton(text=loc.unauth.btns['windows']),
            KeyboardButton(text=loc.unauth.btns['macos']),
            KeyboardButton(text=loc.unauth.btns['linux']),
        ],
        [KeyboardButton(text=loc.unauth.btns['cancel'])],
    ],
)

reg_chatgpt = ReplyKeyboardMarkup(
    resize_keyboard=True,
    keyboard=[
        [
            KeyboardButton(text=loc.unauth.btns['use_chatgpt']),
            KeyboardButton(text=loc.unauth.btns['dont_use_chatgpt']),
            KeyboardButton(text=loc.unauth.btns['what_is_chatgpt']),
        ],
        [KeyboardButton(text=loc.unauth.btns['cancel'])],
    ],
)

reg_ref_promo = ReplyKeyboardMarkup(
    resize_keyboard=True,
    keyboard=[
        [KeyboardButton(text=loc.unauth.btns['no_promo'])],
        [KeyboardButton(text=loc.unauth.btns['cancel'])],
    ],
)
