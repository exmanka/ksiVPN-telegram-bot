import os
import json
from dataclasses import dataclass, field


def run_once(func):
    def wrapper(*args, **kwargs):
        if not getattr(wrapper, 'has_run', False):
            setattr(wrapper, 'has_run', True)
            return func(*args, **kwargs)
    
    return wrapper


@dataclass(frozen=True, slots=True, eq=False)
class MessagesTexts:
    unauth: dict[str, str] = field(default_factory=dict)
    auth: dict[str, str] = field(default_factory=dict)
    admn: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True, eq=False)
class KeyboardButtonsTexts:
    unauth: dict[str, str] = field(default_factory=dict)
    auth: dict[str, str] = field(default_factory=dict)
    admn: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True, eq=False)
class TelegramFilesIds:
    unauth: dict[str, str] = field(default_factory=dict)
    auth: dict[str, str] = field(default_factory=dict)
    admn: dict[str, str] = field(default_factory=dict)


msgs: MessagesTexts
btns: KeyboardButtonsTexts
tfids: TelegramFilesIds


@run_once
def set_locale(localization_file_path: str = 'src/localizations/',
                     language: str = 'ru') -> None:
    """_summary_

    :param localization_file_path: _description_, defaults to 'src/localizations/'
    :type localization_file_path: str, optional
    :param language: _description_, defaults to 'ru'
    :type language: str, optional
    """
    print('Вызвалась функция set_locale')
    global msgs, btns, tfids

    localization_file_name = language + '.json'
    try:
        with open(os.path.join(localization_file_path, localization_file_name), mode='r', encoding='utf8') as localization_file:
            localization_dict = json.load(localization_file)

            user_unauthorized_messeges: dict = localization_dict['user_unauthorized_messages']
            user_authorized_messeges: dict = localization_dict['user_authorized_messages']
            admin_messeges: dict = localization_dict['admin_messages']
            msgs = MessagesTexts(user_unauthorized_messeges, user_authorized_messeges, admin_messeges)

            user_unauthorized_keyboard_buttons: dict = localization_dict['user_unauthorized_keyboard_buttons']
            user_authorized_keyboard_buttons: dict = localization_dict['user_authorized_keyboard_buttons']
            admin_keyboard_buttons: dict = localization_dict['admin_keyboard_buttons']
            btns = KeyboardButtonsTexts(user_unauthorized_keyboard_buttons, user_authorized_keyboard_buttons, admin_keyboard_buttons)

            user_unauthorized_telegram_file_ids: dict = localization_dict['user_unauthorized_telegram_file_ids']
            user_authorized_telegram_file_ids: dict = localization_dict['user_authorized_telegram_file_ids']
            admin_telegram_file_ids: dict = localization_dict['admin_telegram_file_ids']
            tfids = TelegramFilesIds(user_unauthorized_telegram_file_ids, user_authorized_telegram_file_ids, admin_telegram_file_ids)
    
    except Exception as e:
       print(e)