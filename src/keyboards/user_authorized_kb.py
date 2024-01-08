from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from src.database import postgres_dbms
from src.services import localization as loc


menu = ReplyKeyboardMarkup(resize_keyboard=True).\
    add(KeyboardButton(loc.auth.btns['sub_renewal'])).\
    add(KeyboardButton(loc.auth.btns['sub_status'])).insert(KeyboardButton(loc.auth.btns['personal_account'])).\
    add(KeyboardButton(loc.auth.btns['rules'])).insert(KeyboardButton(loc.other.btns['help'])).insert(KeyboardButton(loc.other.btns['about_service']))

sub_renewal = ReplyKeyboardMarkup(resize_keyboard=True).\
    add(KeyboardButton(loc.auth.btns['payment_1mnth'])).insert(KeyboardButton(loc.auth.btns['payment_3mnth'])).insert(KeyboardButton(loc.auth.btns['payment_12mnth'])).\
    add(KeyboardButton(loc.auth.btns['payment_history'])).\
    add(KeyboardButton(loc.auth.btns['return_main_menu']))

sub_renewal_verification = ReplyKeyboardMarkup(resize_keyboard=True).\
    add(KeyboardButton(loc.auth.btns['payment_check'])).\
    add(KeyboardButton(loc.auth.btns['payment_cancel']))


async def sub_renewal_link_inline(link_for_customer: str) -> InlineKeyboardMarkup:
    """Return dynamic inline keyboard with specified payment link as URL for inline button."""
    return InlineKeyboardMarkup().add(InlineKeyboardButton(loc.auth.btns['pay'], url=link_for_customer))

account = ReplyKeyboardMarkup(resize_keyboard=True).\
    add(KeyboardButton(loc.auth.btns['ref_program'])).\
    add(KeyboardButton(loc.auth.btns['configs'])).insert(KeyboardButton(loc.auth.btns['promo'])).\
    add(KeyboardButton(loc.auth.btns['about_client'])).insert(KeyboardButton(loc.auth.btns['about_sub'])).insert(KeyboardButton(loc.auth.btns['settings'])).\
    add(KeyboardButton(loc.auth.btns['return_main_menu']))

config = ReplyKeyboardMarkup(resize_keyboard=True).\
    add(KeyboardButton(loc.auth.btns['current_configs'])).insert(KeyboardButton(loc.auth.btns['request_config'])).\
    add(KeyboardButton(loc.auth.btns['return_to_account_menu_1']))

config_platform = ReplyKeyboardMarkup(resize_keyboard=True).\
    add(KeyboardButton(loc.unauth.btns['smartphone'])).insert(KeyboardButton(loc.unauth.btns['pc'])).\
    add(KeyboardButton(loc.auth.btns['return_to_configs_menu']))

config_mobile_os = ReplyKeyboardMarkup(resize_keyboard=True).\
    add(KeyboardButton(loc.unauth.btns['android'])).insert(KeyboardButton(loc.unauth.btns['ios'])).\
    add(KeyboardButton(loc.auth.btns['return_to_configs_menu']))

config_desktop_os = ReplyKeyboardMarkup(resize_keyboard=True).\
    add(KeyboardButton(loc.unauth.btns['windows'])).insert(KeyboardButton(loc.unauth.btns['macos'])).insert(KeyboardButton(loc.unauth.btns['linux'])).\
    add(KeyboardButton(loc.auth.btns['return_to_configs_menu']))

config_chatgpt = ReplyKeyboardMarkup(resize_keyboard=True).\
    add(KeyboardButton(loc.unauth.btns['use_chatgpt'])).insert(KeyboardButton(loc.unauth.btns['dont_use_chatgpt'])).insert(KeyboardButton(loc.unauth.btns['what_is_chatgpt'])).\
    add(KeyboardButton(loc.auth.btns['return_to_configs_menu']))

promo = ReplyKeyboardMarkup(resize_keyboard=True).\
    add(KeyboardButton(loc.auth.btns['used_promos'])).add(
        KeyboardButton(loc.auth.btns['return_to_account_menu_2']))

ref_program = ReplyKeyboardMarkup(resize_keyboard=True).\
    add(KeyboardButton(loc.auth.btns['ref_program_participation'])).\
    add(KeyboardButton(loc.auth.btns['generate_invite'])).insert(KeyboardButton(loc.auth.btns['show_ref_code'])).\
    add(KeyboardButton(loc.auth.btns['return_to_account_menu_1']))

settings = ReplyKeyboardMarkup(resize_keyboard=True).\
    add(KeyboardButton(loc.auth.btns['settings_chatgpt_mode'])).insert(KeyboardButton(loc.auth.btns['settings_notifications'])).\
    add(KeyboardButton(loc.auth.btns['return_to_account_menu_1']))


async def settings_notifications(client_id: int) -> ReplyKeyboardMarkup:
    """Return dynamic reply keyboard with current notifications settings for client with specified client_id."""
    sub_expires_in_1_day, sub_expires_in_3_days, sub_expires_in_7_days, _ = await postgres_dbms.get_settings_info(client_id)
    settings_notifications_kb = ReplyKeyboardMarkup(resize_keyboard=True)

    # if client turned on notifications one day before subscription expires
    if sub_expires_in_1_day:
        settings_notifications_kb.add(KeyboardButton(loc.auth.btns['1d_off']))
    # if client turned off notifications one day before subscription expires
    else:
        settings_notifications_kb.add(KeyboardButton(loc.auth.btns['1d_on']))

    # if client turned on notifications 3 days before subscription expires
    if sub_expires_in_3_days:
        settings_notifications_kb.insert(KeyboardButton(loc.auth.btns['3d_off']))
    # if client turned off notifications 3 days before subscription expires
    else:
        settings_notifications_kb.insert(KeyboardButton(loc.auth.btns['3d_on']))

    # if client turned on notifications 7 days before subscription expires
    if sub_expires_in_7_days:
        settings_notifications_kb.insert(KeyboardButton(loc.auth.btns['7d_off']))
    # if client turned off notifications 7 days before subscription expires
    else:
        settings_notifications_kb.insert(KeyboardButton(loc.auth.btns['7d_on']))

    settings_notifications_kb.add(KeyboardButton(loc.auth.btns['return_to_settings']))

    return settings_notifications_kb


async def settings_chatgpt(client_id: int) -> ReplyKeyboardMarkup:
    """Return dynamic reply keyboard with current bot's ChatGPT settings for client with specified client_id."""
    settings_chatgpt_kb = ReplyKeyboardMarkup(resize_keyboard=True)

    # if client turned on ChatGPT mode for bot
    if await postgres_dbms.get_chatgpt_mode_status(client_id):
        settings_chatgpt_kb.add(KeyboardButton(loc.auth.btns['chatgpt_off']))

    # if client turned off ChatGPT mode for bot
    else:
        settings_chatgpt_kb.add(KeyboardButton(loc.auth.btns['chatgpt_on']))

    settings_chatgpt_kb.add(KeyboardButton(loc.auth.btns['return_to_settings']))

    return settings_chatgpt_kb


async def configuration_instruction_inlkb(configuration_protocol_name: str, configuration_os: str) -> InlineKeyboardMarkup:
    """Return dynamic inline keyboard with specified protocol and configuration OS as callback_data."""
    return InlineKeyboardMarkup().add(InlineKeyboardButton(loc.auth.btns['installation_instruction'], callback_data=configuration_protocol_name + '--' + configuration_os))
