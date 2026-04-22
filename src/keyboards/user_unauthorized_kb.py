from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
from src.services import localization as loc


welcome = ReplyKeyboardMarkup(
    resize_keyboard=True,
    keyboard=[
        [KeyboardButton(text=loc.unauth.btns['join'])],
        [KeyboardButton(text=loc.unauth.btns['project_info'])],
    ],
)

reg_promo = ReplyKeyboardMarkup(
    resize_keyboard=True,
    keyboard=[
        [KeyboardButton(text=loc.unauth.btns['skip_promo'])],
        [KeyboardButton(text=loc.unauth.btns['project_info'])],
    ],
)
