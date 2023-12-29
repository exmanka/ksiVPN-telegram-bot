from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from src.services import localization as loc


welcome = ReplyKeyboardMarkup(resize_keyboard=True).\
    add(KeyboardButton(loc.unauth.btns['join'])).\
    add(KeyboardButton(loc.unauth.btns['project_info']))

reg_platform = ReplyKeyboardMarkup(resize_keyboard=True).\
    add(KeyboardButton(loc.unauth.btns['smartphone'])).insert(KeyboardButton(loc.unauth.btns['pc'])).\
    add(KeyboardButton(loc.unauth.btns['cancel']))

reg_mobile_os = ReplyKeyboardMarkup(resize_keyboard=True).\
    add(KeyboardButton(loc.unauth.btns['android'])).insert(KeyboardButton(loc.unauth.btns['ios'])).\
    add(KeyboardButton(loc.unauth.btns['cancel']))

reg_desktop_os = ReplyKeyboardMarkup(resize_keyboard=True).\
    add(KeyboardButton(loc.unauth.btns['windows'])).insert(KeyboardButton(loc.unauth.btns['macos'])).insert(KeyboardButton(loc.unauth.btns['linux'])).\
    add(KeyboardButton(loc.unauth.btns['cancel']))

reg_chatgpt = ReplyKeyboardMarkup(resize_keyboard=True).\
    add(KeyboardButton(loc.unauth.btns['use_chatgpt'])).insert(KeyboardButton(loc.unauth.btns['dont_use_chatgpt'])).insert(KeyboardButton(loc.unauth.btns['what_is_chatgpt'])).\
    add(KeyboardButton(loc.unauth.btns['cancel']))

reg_ref_promo = ReplyKeyboardMarkup(resize_keyboard=True).\
    add(KeyboardButton(loc.unauth.btns['no_promo'])).\
    add(KeyboardButton(loc.unauth.btns['cancel']))
