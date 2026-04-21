from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from src.database import postgres_dbms
from src.services import localization as loc


menu = ReplyKeyboardMarkup(
    resize_keyboard=True,
    keyboard=[
        [KeyboardButton(text=loc.auth.btns['sub_renewal'])],
        [
            KeyboardButton(text=loc.auth.btns['my_subscription']),
            KeyboardButton(text=loc.auth.btns['personal_account']),
        ],
        [
            KeyboardButton(text=loc.auth.btns['rules']),
            KeyboardButton(text=loc.other.btns['help']),
            KeyboardButton(text=loc.other.btns['about_service']),
        ],
    ],
)

sub_renewal = ReplyKeyboardMarkup(
    resize_keyboard=True,
    keyboard=[
        [
            KeyboardButton(text=loc.auth.btns['payment_1mnth']),
            KeyboardButton(text=loc.auth.btns['payment_3mnth']),
            KeyboardButton(text=loc.auth.btns['payment_12mnth']),
        ],
        [KeyboardButton(text=loc.auth.btns['payment_history'])],
        [KeyboardButton(text=loc.auth.btns['return_main_menu'])],
    ],
)

sub_renewal_verification = ReplyKeyboardMarkup(
    resize_keyboard=True,
    keyboard=[
        [KeyboardButton(text=loc.auth.btns['payment_check'])],
        [KeyboardButton(text=loc.auth.btns['payment_cancel'])],
    ],
)


async def sub_renewal_link_inline(link_for_customer: str) -> InlineKeyboardMarkup:
    """Return dynamic inline keyboard with specified payment link as URL for inline button."""
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=loc.auth.btns['pay'], url=link_for_customer)]]
    )

account = ReplyKeyboardMarkup(
    resize_keyboard=True,
    keyboard=[
        [
            KeyboardButton(text=loc.auth.btns['ref_program']),
            KeyboardButton(text=loc.auth.btns['promo'])
        ],
        [
            KeyboardButton(text=loc.auth.btns['about_client']),
            KeyboardButton(text=loc.auth.btns['settings']),
        ],
        [KeyboardButton(text=loc.auth.btns['return_main_menu'])],
    ],
)

my_subscription_inline = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text=loc.auth.btns['how_to_connect'], callback_data='subscription_how_to_connect')],
    [InlineKeyboardButton(text=loc.auth.btns['how_to_renew'], callback_data='subscription_how_to_renew')],
])

promo = ReplyKeyboardMarkup(
    resize_keyboard=True,
    keyboard=[
        [KeyboardButton(text=loc.auth.btns['used_promos'])],
        [KeyboardButton(text=loc.auth.btns['return_to_account_menu_2'])],
    ],
)

ref_program = ReplyKeyboardMarkup(
    resize_keyboard=True,
    keyboard=[
        [KeyboardButton(text=loc.auth.btns['ref_program_participation'])],
        [
            KeyboardButton(text=loc.auth.btns['generate_invite']),
            KeyboardButton(text=loc.auth.btns['show_ref_code']),
        ],
        [KeyboardButton(text=loc.auth.btns['return_to_account_menu_1'])],
    ],
)

settings = ReplyKeyboardMarkup(
    resize_keyboard=True,
    keyboard=[
        [
            KeyboardButton(text=loc.auth.btns['settings_chatgpt_mode']),
            KeyboardButton(text=loc.auth.btns['settings_notifications']),
        ],
        [KeyboardButton(text=loc.auth.btns['return_to_account_menu_1'])],
    ],
)


async def settings_notifications(client_id: int) -> ReplyKeyboardMarkup:
    """Return dynamic reply keyboard with current notifications settings for client with specified client_id."""
    sub_expires_in_1_day, sub_expires_in_3_days, sub_expires_in_7_days, _ = await postgres_dbms.get_settings_info(client_id)
    builder = ReplyKeyboardBuilder()

    builder.button(text=loc.auth.btns['1d_off'] if sub_expires_in_1_day else loc.auth.btns['1d_on'])
    builder.button(text=loc.auth.btns['3d_off'] if sub_expires_in_3_days else loc.auth.btns['3d_on'])
    builder.button(text=loc.auth.btns['7d_off'] if sub_expires_in_7_days else loc.auth.btns['7d_on'])
    builder.button(text=loc.auth.btns['return_to_settings'])
    builder.adjust(3, 1)

    return builder.as_markup(resize_keyboard=True)


async def settings_chatgpt(client_id: int) -> ReplyKeyboardMarkup:
    """Return dynamic reply keyboard with current bot's ChatGPT settings for client with specified client_id."""
    builder = ReplyKeyboardBuilder()

    if await postgres_dbms.get_chatgpt_mode_status(client_id):
        builder.button(text=loc.auth.btns['chatgpt_off'])
    else:
        builder.button(text=loc.auth.btns['chatgpt_on'])

    builder.button(text=loc.auth.btns['return_to_settings'])
    builder.adjust(1)

    return builder.as_markup(resize_keyboard=True)


async def configuration_instruction_inline(configuration_protocol_name: str, configuration_os: str) -> InlineKeyboardMarkup:
    """Return dynamic inline keyboard with basic and advanced instruction buttons."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text=loc.auth.btns['basic_installation_instruction'],
                callback_data='basic--' + configuration_protocol_name + '--' + configuration_os,
            )],
            [InlineKeyboardButton(
                text=loc.auth.btns['advanced_installation_instruction'],
                callback_data='advanced--' + configuration_protocol_name + '--' + configuration_os,
            )],
        ]
    )
