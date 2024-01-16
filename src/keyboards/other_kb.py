from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from src.services import localization as loc


faq_inline = InlineKeyboardMarkup().add(InlineKeyboardButton(loc.other.btns['faq_inline'], callback_data=loc.other.btns['faq_inline_callback']))