from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from src.services import localization as loc


welcome = ReplyKeyboardMarkup(
    resize_keyboard=True,
    keyboard=[
        [KeyboardButton(text=loc.unauth.btns['join'])],
        [KeyboardButton(text=loc.unauth.btns['project_info'])],
    ],
)

reg_promo_inline = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text=loc.unauth.btns['skip_promo'], callback_data='skip_promo')],
])
