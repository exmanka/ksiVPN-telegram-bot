import asyncio
import logging
from datetime import datetime
from enum import Enum
from typing import Awaitable, Callable
from aiogram.types import Message, ReplyKeyboardMarkup, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.utils.media_group import MediaGroupBuilder
from aiogram.types import User
from src.keyboards import user_authorized_kb, admin_kb
from src.states import user_authorized_fsm
from src.database import postgres_dbms
from src.services import aiomoney, localization as loc
from src.services.date_formatting import format_localized_bonus_days, format_localized_datetime
from src.services.remnawave_service import RemnawaveError, create_panel_user
from src.config import settings
from src.runtime import bot


logger = logging.getLogger(__name__)


class DeliveryStatus(Enum):
    """Outcome of a Telegram message delivery attempt via :func:`safe_deliver`."""
    OK = 'ok'
    BLOCKED = 'blocked'          # TelegramForbiddenError — user blocked bot or deactivated account
    CHAT_NOT_FOUND = 'gone'      # TelegramBadRequest — chat not found / user gone
    ERROR = 'error'              # any other unexpected error


async def safe_deliver(coro_factory: Callable[[], Awaitable], *, telegram_id: int) -> tuple[DeliveryStatus, str | None]:
    """Execute a Telegram send/copy coroutine, swallowing expected delivery failures.

    Use for any ``bot.send_*`` / ``bot.copy_*`` call where the ``telegram_id`` comes from
    the database and the recipient may have blocked the bot or deleted their account.
    Expected failures (``TelegramForbiddenError``, ``TelegramBadRequest``) are logged at
    INFO, anything else at WARNING. The caller gets a :class:`DeliveryStatus` back and
    decides whether to record the failure, retry, etc.

    :param coro_factory: zero-arg callable returning the coroutine to await,
                         e.g. ``lambda: bot.send_message(tid, text)``
    :param telegram_id: recipient id, used for logging only
    :return: ``(status, error_str)`` — ``error_str`` is ``None`` on success,
             otherwise a human-readable description of the exception.
    """
    try:
        await coro_factory()
        return DeliveryStatus.OK, None
    except TelegramForbiddenError as e:
        err = str(e)
        logger.info(f"Can't deliver to {telegram_id}: bot blocked or account deactivated ({err})")
        return DeliveryStatus.BLOCKED, err
    except TelegramBadRequest as e:
        err = str(e)
        logger.info(f"Can't deliver to {telegram_id}: chat not found ({err})")
        return DeliveryStatus.CHAT_NOT_FOUND, err
    except Exception as e:
        err = str(e)
        logger.warning(f"Can't deliver to {telegram_id} due to unexpected error: {err}")
        return DeliveryStatus.ERROR, err


async def format_none_string(string: str | None, prefix: str = ' ', postfix: str = '') -> str:
    """Return empty string '' if specified object is None, else return specified specified string with prefix and postfix.
    
    Use for fast object conversion before str.format method usage.

    :param string: object that needs to be formatted
    :param prefix: prefix added to specified string if it's not None, defaults to ' '
    :param postfix: prefix added to specified string if it's not None, defaults to ''
    :return: empty string or prefix + string + postfix
    """    
    return '' if string is None else prefix + string + postfix


async def send_long_message(message: Message, text: str, parse_mode: str | None = 'HTML', wrapper: str | None = None, max_length: int = 4096):
    """Split long text into multiple messages to fit Telegram's 4096 char limit.

    :param message: aiogram Message to reply to
    :param text: full text to send
    :param parse_mode: parse mode for messages, defaults to 'HTML'
    :param wrapper: optional wrapper format string with {text} placeholder, e.g. '<pre>{text}</pre>'
    """
    lines = text.split('\n')
    chunk = ''

    for line in lines:
        candidate = chunk + line + '\n' if chunk else line + '\n'
        # check length with wrapper applied
        formatted = wrapper.format(text=candidate) if wrapper else candidate
        if len(formatted) > max_length and chunk:
            # send accumulated chunk
            formatted_chunk = wrapper.format(text=chunk) if wrapper else chunk
            await message.answer(formatted_chunk, parse_mode=parse_mode)
            chunk = line + '\n'
        else:
            chunk = candidate

    if chunk.strip():
        formatted_chunk = wrapper.format(text=chunk) if wrapper else chunk
        await message.answer(formatted_chunk, parse_mode=parse_mode)


async def send_photo_safely(telegram_user_id: int,
                            telegram_file_id: str,
                            caption: str | None,
                            parse_mode: str | None = None,
                            reply_markup: ReplyKeyboardMarkup | InlineKeyboardMarkup | None = None):
    """Send photo by specified telegram_file_id if telegram_file_id is valid and available for bot. Else send template image by URL.

    If parse_mode is None (default), bot-level default (HTML) is used via DefaultBotProperties.
    Pass an explicit string to override (e.g. 'Markdown'), or pass '' to disable parsing entirely.
    """
    # Only pass parse_mode explicitly when the caller overrides it; otherwise let DefaultBotProperties apply.
    pm_kwargs: dict = {'parse_mode': parse_mode} if parse_mode is not None else {}
    try:
        await bot.send_photo(telegram_user_id, telegram_file_id, caption=caption, reply_markup=reply_markup, **pm_kwargs)

    except TelegramBadRequest as wrong_file_id:
        logger.warning(f"Can't send photo by specified telegram_file_id: {wrong_file_id}. Perhaps you try to send image by file_id from ksiVPN bot. File_id is unique for each individual bot!")
        await bot.send_photo(telegram_user_id, loc.internal.tfids['template_image_url'], caption=caption, reply_markup=reply_markup, **pm_kwargs)


async def reply_media_group_safely(message: Message,
                                   telegram_files_ids_list: list[str],
                                   caption: str | None,
                                   parse_mode: str | None = None):
    """Reply message with media group with specified telegram_files_ids if they are valid and available for bot. Else send template media group with image by URL.

    If parse_mode is None (default), bot-level default (HTML) is used via DefaultBotProperties.
    """
    # parse_mode on the first photo item (which carries the caption); None → omit → bot default applies.
    pm_kwargs: dict = {'parse_mode': parse_mode} if parse_mode is not None else {}

    def _build(files: list[str]) -> list:
        builder = MediaGroupBuilder()
        for i, tfid in enumerate(files):
            if i == 0:
                builder.add_photo(media=tfid, caption=caption, **pm_kwargs)
            else:
                builder.add_photo(media=tfid)
        return builder.build()

    try:
        await message.reply_media_group(_build(telegram_files_ids_list))

    except TelegramBadRequest as wrong_file_id:
        logger.warning(f"Can't send media group by specified telegram_files_ids: {wrong_file_id}. Perhaps you try to send image by file_id from ksiVPN bot. File_id is unique for each individual bot!")
        await message.reply_media_group(_build([loc.internal.tfids['template_image_url']]))


async def send_message_by_telegram_id(telegram_id: int, message: Message):
    """Send specified message by provided telegram_id.

    :param telegram_id:
    :param message:
    :raises Exception: unrecognized message type
    """
    # if message is text
    if text := message.text:
        # preserve original formatting via entities; bot default parse_mode is NOT applied
        # when entities are present (they take precedence)
        await bot.send_message(telegram_id, text, entities=message.entities)

    # if message is animation (GIF or H.264/MPEG-4 AVC video without sound)
    elif animation := message.animation:
        await bot.send_animation(telegram_id, animation.file_id,
                                 caption=message.caption, caption_entities=message.caption_entities)

    # if message is audio (audio file to be treated as music)
    elif audio := message.audio:
        await bot.send_audio(telegram_id, audio.file_id,
                             caption=message.caption, caption_entities=message.caption_entities)

    # if message is document
    elif document := message.document:
        await bot.send_document(telegram_id, document.file_id,
                                caption=message.caption, caption_entities=message.caption_entities)

    # if message is photo
    elif photo := message.photo:
        await bot.send_photo(telegram_id, photo[0].file_id,
                             caption=message.caption, caption_entities=message.caption_entities)

    # if message is sticker
    elif sticker := message.sticker:
        await bot.send_sticker(telegram_id, sticker.file_id)

    # if message is video
    elif video := message.video:
        await bot.send_video(telegram_id, video.file_id,
                             caption=message.caption, caption_entities=message.caption_entities)

    # if message is video note
    elif video_note := message.video_note:
        await bot.send_video_note(telegram_id, video_note.file_id)

    # if message is voice
    elif voice := message.voice:
        await bot.send_voice(telegram_id, voice.file_id,
                             caption=message.caption, caption_entities=message.caption_entities)

    # other cases
    else:
        raise Exception('unrecognized message type')


async def send_configuration(telegram_id: int,
                             configuration_file_type: str,
                             configuration_date_of_receipt: datetime,
                             configuration_os: str,
                             configuration_protocol_name: str,
                             server_country: str,
                             server_city: str,
                             server_bandwidth: int,
                             server_ping: int,
                             available_services: list[str],
                             configuration_link: str,
                             configuration_id: int,
                             server_name: str):
    """Send message with specified configuration by telegram_id.

    :param telegram_id:
    :param configuration_file_type: file type ('document' or 'link')
    :param configuration_date_of_receipt: date the configuration was created
    :param configuration_os: name of OS provided by configuration
    :param configuration_protocol_name: name of protocol provided by configuration
    :param server_country: name of country where server provided by configuration is situated
    :param server_city: name of city where server provided by configuration is situated
    :param server_bandwidth: bandwidth of server provided by configuration
    :param server_ping: average ping of server provided by configuration
    :param available_services: list of available services on this server
    :param configuration_link: telegram file id (for 'document') or VPN URI string (for 'link')
    :param configuration_id: configuration ID in database
    :param server_name: human-readable server name
    :raises Exception: wrong file type
    """
    answer_text = await create_configuration_description(configuration_date_of_receipt, configuration_os, configuration_protocol_name, server_country, server_city, server_bandwidth, server_ping, available_services, configuration_id, server_name)

    # if config was generated as document
    if configuration_file_type == 'document':
        await bot.send_document(telegram_id, configuration_link, caption=answer_text,
                                reply_markup=await user_authorized_kb.configuration_instruction_inline(configuration_protocol_name, configuration_os))

    # if config was generated as link
    elif configuration_file_type == 'link':
        answer_text = f'<code>{configuration_link}</code>\n\n' + answer_text
        await bot.send_message(telegram_id, answer_text,
                               reply_markup=await user_authorized_kb.configuration_instruction_inline(configuration_protocol_name, configuration_os))

    else:
        raise Exception('wrong file type')


async def _send_new_client_joined_to_admin(client_id: int,
                                            fullname: str,
                                            username: str | None,
                                            telegram_id: int,
                                            subscription_url: str | None,
                                            promo: str | None) -> None:
    """Send admin notification when a new client completes registration."""
    username_str = await format_none_string(username, prefix=' @')

    if promo is None:
        ref_promo_str = loc.internal.msgs['config_request_new_client_no_ref_promo_str']
    else:
        _, client_creator_id, provided_sub_id, bonus_time = await postgres_dbms.get_refferal_promo_info_by_phrase(promo)
        client_creator_name, client_creator_surname, client_creator_username, client_creator_telegram_id, *_ = await postgres_dbms.get_client_info_by_clientID(client_creator_id)
        *_, price = await postgres_dbms.get_subscription_info_by_subID(provided_sub_id)
        client_creator_surname_str = await format_none_string(client_creator_surname)
        client_creator_username_str = await format_none_string(client_creator_username)
        ref_promo_str = loc.internal.msgs['config_request_new_client_ref_promo_str'].\
            format(promo, client_creator_name, client_creator_surname_str, client_creator_username_str, client_creator_telegram_id, format_localized_bonus_days(bonus_time), price)

    sub_url_str = f'<code>{subscription_url}</code>' if subscription_url else '⚠️ ошибка создания пользователя в Remnawave'
    await bot.send_message(settings.bot.admin_id,
                           loc.internal.msgs['new_client_joined'].format(client_id, username_str, fullname, telegram_id, sub_url_str, ref_promo_str=ref_promo_str))


async def send_configuration_request_to_admin(client: dict, choice: dict, is_new_client: bool):
    """Send message for administrator with information about new configuration request from client.

    :param client: dict with information about client ('fullname', 'username', 'id')
    :param choice: dict with information about client's choice ('platform', 'os_name', 'chatgpt', 'promo')
    :param is_new_client: if client is new TRUE else FALSE
    """
    # convert username for beautiful formatting
    username_str = await format_none_string(client['username'], prefix=' @')

    # get client_id from db
    client_id, *_ = await postgres_dbms.get_client_info_by_telegramID(client['id'])

    # map displayed OS label back to short alias (android/ios/windows/macos/linux)
    os_alias_map = {loc.unauth.btns[k]: k for k in ('android', 'ios', 'windows', 'macos', 'linux')}
    os_alias = os_alias_map.get(choice['os_name'], 'android')

    # if request was sended by new client with zero configurations
    if is_new_client:

        # if client didn't enter referral promocode during registration
        if choice['promo'] is None:
            ref_promo_str = loc.internal.msgs['config_request_new_client_no_ref_promo_str']

        # if client entered referral promocode during registration
        else:

            # get information about entered referral promocode
            _, client_creator_id, provided_sub_id, bonus_time = await postgres_dbms.get_refferal_promo_info_by_phrase(choice['promo'])
            client_creator_name, client_creator_surname, client_creator_username, client_creator_telegram_id, *_ = await postgres_dbms.get_client_info_by_clientID(client_creator_id)
            *_, price = await postgres_dbms.get_subscription_info_by_subID(provided_sub_id)

            # convert surname and username for beautiful formatting
            client_creator_surname_str = await format_none_string(client_creator_surname)
            client_creator_username_str = await format_none_string(client_creator_username)
            ref_promo_str = loc.internal.msgs['config_request_new_client_ref_promo_str'].\
                format(choice['promo'], client_creator_name, client_creator_surname_str, client_creator_username_str, client_creator_telegram_id, format_localized_bonus_days(bonus_time), price)

        await bot.send_message(settings.bot.admin_id,
                               loc.internal.msgs['config_request_new_client'].\
                                format(client['fullname'], username_str, client['id'], choice['platform'][2:], choice['os_name'], choice['chatgpt'], client_id, ref_promo_str=ref_promo_str),
                               reply_markup=await admin_kb.configuration_inline(client['id'], os_alias))

    # if request was sended by old client with at least one configuration
    else:
        await bot.send_message(settings.bot.admin_id,
                               loc.internal.msgs['config_request_old_client'].\
                                format(client['fullname'], username_str, client['id'], choice['platform'][2:], choice['os_name'], choice['chatgpt'], client_id),
                               reply_markup=await admin_kb.configuration_inline(client['id'], os_alias))


async def notify_admin_promo_entered(client_id: int, promo_phrase: str, promo_type: str):
    """Send message to administrator with information about entered by client promocode.

    :param client_id:
    :param promo_phrase: phrase of entered promocode
    :param promo_type: type of promocode as string ('global', 'local')
    :raises Exception: wrong type of promo code was entered
    """
    name, surname, username, telegram_id, *_ = await postgres_dbms.get_client_info_by_clientID(client_id)

    # convert surname and username for beautiful formatting
    surname_str = await format_none_string(surname)
    username_str = await format_none_string(username)

    new_sub_str = ''
    if promo_type == 'global':
        id, expiration_date, _, bonus_time = await postgres_dbms.get_global_promo_info(promo_phrase)
        provided_sub_id = None

    elif promo_type == 'local':
        id, expiration_date, bonus_time, provided_sub_id = await postgres_dbms.get_local_promo_info(promo_phrase)

        # if local promo changes client's subscription
        if provided_sub_id:
            *_, price = await postgres_dbms.get_subscription_info_by_subID(provided_sub_id)
            new_sub_str = loc.internal.msgs['admin_promo_was_etnered_local_promo_new_sub_str'].format(price)

    else:
        raise Exception('wrong promo type was entered')

    await bot.send_message(settings.bot.admin_id,
                           loc.internal.msgs['admin_promo_was_entered'].\
                            format(client_id, username_str, name, surname_str, telegram_id, promo_type, id,
                                   format_localized_bonus_days(bonus_time),
                                   format_localized_datetime(expiration_date),
                                   new_sub_str=new_sub_str))


async def notify_admin_payment_success(client_id: int, months_number: int):
    """Send message for admin with information about new successful client's payment.

    :param client_id:
    :param months_number: number of month client paid for
    """
    name, surname, username, telegram_id, *_ = await postgres_dbms.get_client_info_by_clientID(client_id)

    # convert surname and username for beautiful formatting
    surname_str = await format_none_string(surname)
    username_str = await format_none_string(username)
    await bot.send_message(settings.bot.admin_id, loc.internal.msgs['admin_successful_payment'].format(months_number, client_id, username_str, name, surname_str, telegram_id))


async def notify_client_new_referal(client_creator_id: int, referral_client_name: str, referral_client_username: str | None = None):
    """Send message for client with information about new client registered by his referral promocode.

    :param client_creator_id: system id of client who own promocode
    :param referal_client_name: name of new referral client
    :param referal_client_username: username of new referral client, defaults to None
    :type referal_client_username: str | None, optional
    """
    # convert username for beautiful formatting
    referral_client_username_str = await format_none_string(referral_client_username, prefix=' @')

    # get information about referral bonus
    *_, bonus_time = await postgres_dbms.get_refferal_promo_info_by_clientCreatorID(client_creator_id)

    client_creator_telegram_id = await postgres_dbms.get_telegramID_by_clientID(client_creator_id)
    await safe_deliver(
        lambda: bot.send_message(
            client_creator_telegram_id,
            loc.internal.msgs['ref_promo_was_entered'].format(referral_client_name, referral_client_username_str, format_localized_bonus_days(bonus_time)),
        ),
        telegram_id=client_creator_telegram_id,
    )


async def notify_client_if_subscription_must_be_renewed_to_receive_configuration(telegram_id: int):
    """Send message by specified telegram_id IF client needs to renew subscription for receiving his first configuration."""

    if await postgres_dbms.is_subscription_blank(telegram_id):
        await safe_deliver(
            lambda: bot.send_message(telegram_id, loc.unauth.msgs['need_renew_sub']),
            telegram_id=telegram_id,
        )


async def create_configuration_description(configuration_date_of_receipt: datetime,
                                           configuration_os: str,
                                           configuration_protocol_name: str,
                                           server_country: str,
                                           server_city: str,
                                           server_bandwidth: int,
                                           server_ping: int,
                                           available_services: list[str],
                                           configuration_id: int,
                                           server_name: str,
                                           link: str | None = None) -> str:
    """Return description for specified configurations.

    :param configuration_date_of_receipt: date the configuration was created
    :param configuration_os: name of OS provided by configuration
    :param configuration_protocol_name: name of protocol provided by configuration
    :param server_country: name of country where server provided by configuration is situated
    :param server_city: name of city where server provided by configuration is situated
    :param server_bandwidth: bandwidth of server provided by configuration
    :param server_ping: average ping of server provided by configuration
    :param available_services: list of available services on this server
    :param configuration_id: configuration ID in database
    :param server_name: human-readable server name
    :param link: vless link for XTLS-Reality configuration, defaults to None
    :return: description of configurations with HTML-tags
    :rtype: str
    """
    services_str = ', '.join(available_services) if available_services else '—'

    return loc.internal.msgs['config_info'].format(server_name, server_country, server_city,
                                               server_bandwidth, server_ping, services_str, configuration_protocol_name,
                                               configuration_os, format_localized_datetime(configuration_date_of_receipt),
                                               configuration_id)


async def create_configuration(client_id: int,
                               file_type: str,
                               flag_protocol: str,
                               flag_location: str,
                               flag_os: str,
                               flag_link: str | None = None,
                               telegram_file_id: str | None = None):
    """Create new configuration in db.

    :param client_id:
    :param file_type: file type in ('link', 'document')
    :param flag_protocol: protocol name in ('wireguar', 'w', 'wg', 'xtls-reality', 'x', 'xtls', 'reality', 'shadowsocks', 's', 'ss')
    :param flag_location: location name in ('netherlands', 'n', 'latvia', 'l', 'germany', 'g', 'usa', 'u')
    :param flag_os: os name in ('android', 'ios', 'windows', 'linux', 'macos', 'mac')
    :param flag_link: link for XTLS-Reality starting from 'vless://'
    :param telegram_file_id: telegram file_id for 'document' configurations
    :raises Exception: invalid telegram_file_id
    :raises Exception: invalid file_type
    """
    if file_type == 'link':
        protocol_id, server_id, os_enum, link = await get_configuration_sql_data(flag_protocol, flag_location, flag_os, flag_link)
        await postgres_dbms.insert_configuration(client_id, protocol_id, server_id, os_enum, file_type, link)

    elif file_type == 'document':
        if telegram_file_id is None:
            raise Exception(loc.internal.msgs['error_no_telegram_file_id'])

        protocol_id, server_id, os_enum, _ = await get_configuration_sql_data(flag_protocol, flag_location, flag_os, flag_link)
        await postgres_dbms.insert_configuration(client_id, protocol_id, server_id, os_enum, file_type, telegram_file_id)

    else:
        raise Exception(loc.internal.msgs['error_bad_file_type'])


async def get_configuration_sql_data(protocol: str, location: str, os: str, link: str | None = None) -> tuple[int, str, str]:
    """Return data suitable for SQL-query for configuration creation.

    :param protocol: protocol alias (e.g. 'x', 'wg', 'ss')
    :param location: server alias (e.g. 'nl1', 'lv1', 'de1', 'us1')
    :param os: os name in ('android', 'ios', 'windows', 'linux', 'macos', 'mac')
    :param link: link for XTLS-Reality starting from 'vless://'
    :raises Exception: invalid protocol alias
    :raises Exception: invalid server alias
    :raises Exception: invalid OS type
    :raises Exception: invalid link
    :return: tuple (protocol_id, server_id, os_enum, link)
    """
    protocol_id = await postgres_dbms.get_protocol_id_by_alias(protocol.lower())
    if protocol_id is None:
        raise Exception(loc.internal.msgs['error_bad_protocol'])

    server_id = await postgres_dbms.get_server_id_by_alias(location.lower())
    if server_id is None:
        raise Exception(loc.internal.msgs['error_bad_country'])

    os_enum = None
    match os.lower():
        case 'android':
            os_enum = 'Android'

        case 'ios':
            os_enum = 'IOS'

        case 'windows':
            os_enum = 'Windows'

        case 'linux':
            os_enum = 'Linux'

        case 'mac':
            os_enum = 'macOS'
        case 'macos':
            os_enum = 'macOS'

        case _:
            raise Exception(loc.internal.msgs['error_bad_os'])

    if link and not link.startswith('vless://'):
        raise Exception(loc.internal.msgs['error_bad_link'])

    return protocol_id, server_id, os_enum, link


async def check_referral_reward(ref_client_id: int):
    """Check whether the client should receive a referral fee.

    :param ref_client_id: client_id of person who registered with referral promocode
    """
    successful_payments_number = await postgres_dbms.get_payments_successful_number(ref_client_id)
    ref_client_name, _, ref_client_username, *_, used_ref_promo_id = await postgres_dbms.get_client_info_by_clientID(ref_client_id)

    # if client paid for subscription for the first time and used referral promo
    if successful_payments_number == 1 and used_ref_promo_id:

        # add subscription bonus time (30 days) for old client
        _, client_creator_id, *_ = await postgres_dbms.get_refferal_promo_info_by_promoID(used_ref_promo_id)
        await postgres_dbms.add_subscription_period(client_creator_id, days=30)

        # notify old client about new bonus
        # if client's username exists (add whitespace for good string formatting)
        ref_client_username_str = await format_none_string(ref_client_username)
        client_creator_telegram_id = await postgres_dbms.get_telegramID_by_clientID(client_creator_id)
        await safe_deliver(
            lambda: bot.send_message(
                client_creator_telegram_id,
                loc.internal.msgs['ref_client_paid_for_sub'].format(ref_client_name, ref_client_username_str),
            ),
            telegram_id=client_creator_telegram_id,
        )


async def autocheck_payment_status(payment_id: int) -> str:
    """Automatically check payment is successful according to YooMoney for 300 seconds.

    :param payment_id:
    :return: autochecker status, 'success' - payment was successfully finished, 'failure' - payment wasn't successfully finished in 300 seconds,
    'already_checked' - payment was already checked and added to db as successful by other functions
    """
    wallet = aiomoney.YooMoneyWallet(settings.payments.yoomoney.token.get_secret_value())

    # wait for user to redirect to Yoomoney site first 5 seconds
    await asyncio.sleep(5)

    # After that check Yoomoney payment status using quadratic equation
    a = 0.01
    b = 10
    max_waiting_time = 60   # seconds
    for x in range(100):

        # if user has already checked successful payment and it was added to account subscription
        if await postgres_dbms.get_payment_status(payment_id):
            return 'already_checked'

        # if payment was successful according to YooMoney info
        if await wallet.check_payment_on_successful(payment_id):
            return 'success'

        await asyncio.sleep(min(a * x * x + b, max_waiting_time))

    return 'failure'


async def authorization_complete(from_user: User, state: FSMContext) -> None:
    """Complete authorization of new client: insert into DB, provision in Remnawave, notify admin.

    :param from_user: Telegram User object (message.from_user or callback.from_user)
    :param state:
    """
    used_ref_promo_id = None
    provided_sub_id = None
    bonus_time = None
    data = await state.get_data()

    if phrase := data.get('promo'):
        used_ref_promo_id, _, provided_sub_id, bonus_time = await postgres_dbms.get_refferal_promo_info_by_phrase(phrase)

    client_id = await postgres_dbms.insert_client(from_user.first_name, from_user.id, from_user.last_name, from_user.username, used_ref_promo_id, provided_sub_id, bonus_time)
    expire_at = await postgres_dbms.get_subscription_expiration_date_by_clientID(client_id)

    subscription_url: str | None = None
    try:
        remnawave_uuid, subscription_url = await create_panel_user(from_user.id, from_user.username, expire_at)
        await postgres_dbms.insert_client_remnawave(client_id, remnawave_uuid, subscription_url)
    except RemnawaveError as exc:
        logger.error("Failed to create Remnawave user for client_id=%s tg_id=%s: %s", client_id, from_user.id, exc)
        await safe_deliver(
            lambda: bot.send_message(settings.bot.admin_id, loc.internal.msgs['new_client_remnawave_error'].format(client_id, from_user.id)),
            telegram_id=settings.bot.admin_id,
        )

    await _send_new_client_joined_to_admin(client_id, from_user.full_name, from_user.username, from_user.id, subscription_url, data.get('promo'))

    if subscription_url:
        welcome_text = loc.internal.msgs['registration_complete'].format(subscription_url)
    else:
        welcome_text = loc.internal.msgs['registration_complete_no_url']

    await bot.send_message(from_user.id, welcome_text, reply_markup=user_authorized_kb.menu)
    await state.clear()


async def sub_renewal(message: Message, state: FSMContext, months_number: int, discount: float):
    """Create message with subscription renewal payment link, run autochecker for payment and notify about successful payment.

    :param message:
    :param state:
    :param months_number: number of months subscription must be renewed
    :param discount: price discount in range [0, 1)
    """
    # get client_id by telegramID
    client_id = await postgres_dbms.get_clientID_by_telegramID(message.from_user.id)

    # get client's sub info
    sub_id, sub_title, _, sub_price = await postgres_dbms.get_subscription_info_by_clientID(client_id)

    # count payment sum
    payment_price = max(sub_price * months_number * (1 - discount), 2)
    # create entity in db table payments and getting payment_id
    payment_id = await postgres_dbms.insert_payment(client_id, sub_id, payment_price, months_number)

    # use aiomoney for payment link creation
    wallet = aiomoney.YooMoneyWallet(settings.payments.yoomoney.token.get_secret_value())
    payment_form = await wallet.create_payment_form(
        amount_rub=payment_price,
        unique_label=payment_id,
        payment_source=aiomoney.PaymentSource.YOOMONEY_WALLET,
        success_redirect_url="https://t.me/ksiVPN_bot"
    )

    # answer with ReplyKeyboardMarkup
    await message.answer(loc.internal.msgs['wait_payment'], reply_markup=user_authorized_kb.sub_renewal_verification)
    await state.set_state(user_authorized_fsm.PaymentMenu.verification)

    # answer with InlineKeyboardMarkup with link to payment
    discount_str = ''
    if discount:
        discount_str = loc.internal.msgs['discount_str'].format(sub_price * months_number * discount)

    message_info = await message.answer(loc.internal.msgs['payment_form'].format(sub_title, months_number, payment_price, payment_id, discount_str=discount_str),
                                        reply_markup=await user_authorized_kb.sub_renewal_link_inline(payment_form.link_for_customer))

    # add telegram_id for created payment
    await postgres_dbms.update_payment_telegram_message_id(payment_id, message_info.message_id)

    # run payment autochecker for 310 seconds
    client_last_payment_status = await autocheck_payment_status(payment_id)

    # if autochecker returns successful payment info
    if client_last_payment_status == 'success':
        await postgres_dbms.update_payment_successful(payment_id, client_id, months_number)
        await state.set_state(user_authorized_fsm.PaymentMenu.menu)
        await notify_admin_payment_success(client_id, months_number)
        await check_referral_reward(client_id)

        # try to delete payment message
        try:
            await bot.delete_message(message.chat.id, message_info.message_id)

        # if already deleted
        except TelegramBadRequest:
            pass

        finally:
            await message.answer(loc.internal.msgs['payment_successful'].format(payment_id), reply_markup=user_authorized_kb.sub_renewal)
