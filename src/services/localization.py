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
class SubjectLocalization:
    msgs: dict[str, str] = field(default_factory=dict)
    btns: dict[str, str] = field(default_factory=dict)
    tfids: dict[str, str] = field(default_factory=dict)

# @dataclass(frozen=True, slots=True, eq=False)
# class UserAuthorizedLocalization:
#     msgs: dict[str, str] = field(default_factory=dict)
#     btns: dict[str, str] = field(default_factory=dict)
#     tfids: dict[str, str] = field(default_factory=dict)

# @dataclass(frozen=True, slots=True, eq=False)
# class AdminLocalization:
#     msgs: dict[str, str] = field(default_factory=dict)
#     btns: dict[str, str] = field(default_factory=dict)
#     tfids: dict[str, str] = field(default_factory=dict)

# @dataclass(frozen=True, slots=True, eq=False)
# class ServiceFunctionLocalization:
#     msgs: dict[str, str] = field(default_factory=dict)
#     btns: dict[str, str] = field(default_factory=dict)
#     tfids: dict[str, str] = field(default_factory=dict)


unauth: SubjectLocalization
auth: SubjectLocalization
admn: SubjectLocalization
srvc: SubjectLocalization


# @dataclass(frozen=True, slots=True, eq=False)
# class MessagesTexts:
#     unauth: dict[str, str] = field(default_factory=dict)
#     auth: dict[str, str] = field(default_factory=dict)
#     admn: dict[str, str] = field(default_factory=dict)
#     srvc: dict[str, str] = field(default_factory=dict)


# @dataclass(frozen=True, slots=True, eq=False)
# class KeyboardButtonsTexts:
#     unauth: dict[str, str] = field(default_factory=dict)
#     auth: dict[str, str] = field(default_factory=dict)
#     admn: dict[str, str] = field(default_factory=dict)


# @dataclass(frozen=True, slots=True, eq=False)
# class TelegramFilesIds:
#     unauth: dict[str, str] = field(default_factory=dict)
#     auth: dict[str, str] = field(default_factory=dict)
#     admn: dict[str, str] = field(default_factory=dict)


# msgs: MessagesTexts
# btns: KeyboardButtonsTexts
# tfids: TelegramFilesIds


@run_once
def set_locale(localization_file_path: str = 'src/localizations/',
               language: str = 'ru') -> None:
    """_summary_

    :param localization_file_path: _description_, defaults to 'src/localizations/'
    :type localization_file_path: str, optional
    :param language: _description_, defaults to 'ru'
    :type language: str, optional
    """
    #global msgs, btns, tfids
    global unauth, auth, admn, srvc

    localization_file_name = language + '.json'
    try:
        with open(os.path.join(localization_file_path, localization_file_name), mode='r', encoding='utf8') as localization_file:
            localization_dict: dict = json.load(localization_file)

            unauth = SubjectLocalization(*localization_dict['user_unauthorized'].values())
            auth = SubjectLocalization(*localization_dict['user_authorized'].values())
            admn = SubjectLocalization(*localization_dict['admin'].values())
            srvc = SubjectLocalization(*localization_dict['service_functions'].values())
            # user_unauthorized_messages: dict = localization_dict['user_unauthorized_messages']
            # user_authorized_messages: dict = localization_dict['user_authorized_messages']
            # admin_messages: dict = localization_dict['admin_messages']
            # service_messages: dict = localization_dict['service_messages']
            # msgs = MessagesTexts(user_unauthorized_messages, user_authorized_messages, admin_messages, service_messages)

            # user_unauthorized_keyboard_buttons: dict = localization_dict['user_unauthorized_keyboard_buttons']
            # user_authorized_keyboard_buttons: dict = localization_dict['user_authorized_keyboard_buttons']
            # admin_keyboard_buttons: dict = localization_dict['admin_keyboard_buttons']
            # btns = KeyboardButtonsTexts(user_unauthorized_keyboard_buttons, user_authorized_keyboard_buttons, admin_keyboard_buttons)

            # user_unauthorized_telegram_file_ids: dict = localization_dict['user_unauthorized_telegram_file_ids']
            # user_authorized_telegram_file_ids: dict = localization_dict['user_authorized_telegram_file_ids']
            # admin_telegram_file_ids: dict = localization_dict['admin_telegram_file_ids']
            # tfids = TelegramFilesIds(user_unauthorized_telegram_file_ids, user_authorized_telegram_file_ids, admin_telegram_file_ids)
    
    except Exception as e:
       print(e)