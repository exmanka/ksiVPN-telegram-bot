from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from src.services import localization as loc


faq_inline = InlineKeyboardMarkup().\
    add(InlineKeyboardButton(loc.other.btns['faq_inline'], callback_data=loc.other.btns['faq_inline_callback'])).\
    add(InlineKeyboardButton(loc.other.btns['tg_channel_inline'], url=loc.other.btns['tg_channel_inline_url']))