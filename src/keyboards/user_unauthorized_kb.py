from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from src.services import localization as loc


welcome = ReplyKeyboardMarkup(resize_keyboard=True).\
    add(KeyboardButton(loc.btns.unauth['join'])).\
    add(KeyboardButton(loc.btns.unauth['project_info']))

reg_platform = ReplyKeyboardMarkup(resize_keyboard=True).\
    add(KeyboardButton(loc.btns.unauth['smartphone'])).insert(KeyboardButton(loc.btns.unauth['pc'])).\
    add(KeyboardButton(loc.btns.unauth['cancel']))

reg_mobile_os = ReplyKeyboardMarkup(resize_keyboard=True).\
    add(KeyboardButton(loc.btns.unauth['android'])).insert(KeyboardButton(loc.btns.unauth['ios'])).\
    add(KeyboardButton(loc.btns.unauth['cancel']))

reg_desktop_os = ReplyKeyboardMarkup(resize_keyboard=True).\
    add(KeyboardButton(loc.btns.unauth['windows'])).insert(KeyboardButton(loc.btns.unauth['macos'])).insert(KeyboardButton(loc.btns.unauth['linux'])).\
    add(KeyboardButton(loc.btns.unauth['cancel']))

reg_chatgpt = ReplyKeyboardMarkup(resize_keyboard=True).\
    add(KeyboardButton(loc.btns.unauth['use_chatgpt'])).insert(KeyboardButton(loc.btns.unauth['dont_use_chatgpt'])).insert(KeyboardButton(loc.btns.unauth['what_is_chatgpt'])).\
    add(KeyboardButton(loc.btns.unauth['cancel']))

reg_ref_promo = ReplyKeyboardMarkup(resize_keyboard=True).\
    add(KeyboardButton(loc.btns.unauth['no_promo'])).\
    add(KeyboardButton(loc.btns.unauth['cancel']))
