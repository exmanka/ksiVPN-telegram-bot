import os
import json
from dataclasses import dataclass, field


def run_once(func):
    """Decorator allows to call the specified function only once."""
    def wrapper(*args, **kwargs):
        if not getattr(wrapper, 'has_run', False):
            setattr(wrapper, 'has_run', True)
            return func(*args, **kwargs)
    
    return wrapper


@dataclass(frozen=True, slots=True, eq=False)
class SubjectLocalization:
    """Dataclass for localization of subjects."""
    msgs: dict[str, str] = field(default_factory=dict)
    btns: dict[str, str] = field(default_factory=dict)
    tfids: dict[str, str] = field(default_factory=dict)


unauth: SubjectLocalization     # user_unauthorized
auth: SubjectLocalization       # user_authorized
admn: SubjectLocalization       # admin
other: SubjectLocalization      # other
internal: SubjectLocalization   # internal_functions
mw: SubjectLocalization         # middlewares


@run_once
def set_locale(localization_file_path: str = 'src/localizations/',
               language: str = 'ru') -> None:
    """Set bot localization by .json file. Function is executed only once.

    :param localization_file_path: path to .json file, defaults to 'src/localizations/'
    :param language: name of .json file, defaults to 'ru'
    """
    global unauth, auth, admn, other, internal, mw

    localization_file_name = language + '.json'
    try:
        with open(os.path.join(localization_file_path, localization_file_name), mode='r', encoding='utf8') as localization_file:
            localization_dict: dict = json.load(localization_file)
            unauth = SubjectLocalization(*localization_dict['user_unauthorized'].values())
            auth = SubjectLocalization(*localization_dict['user_authorized'].values())
            admn = SubjectLocalization(*localization_dict['admin'].values())
            other = SubjectLocalization(*localization_dict['other'].values())
            internal = SubjectLocalization(*localization_dict['internal_functions'].values())
            mw = SubjectLocalization(*localization_dict['middlewares'].values())
    
    except Exception as e:
       print(e)