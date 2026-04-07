from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from src.services import localization as loc


faq_inline = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(
            text=loc.other.btns['faq_inline'],
            callback_data=loc.other.btns['faq_inline_callback'],
        )],
        [InlineKeyboardButton(
            text=loc.other.btns['tg_channel_inline'],
            url=loc.other.btns['tg_channel_inline_url'],
        )],
    ]
)
