import asyncio
import logging
import html
import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from enum import Enum
from typing import Awaitable, Callable
from zoneinfo import ZoneInfo
from aiogram.types import Message, ReplyKeyboardMarkup, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.utils.media_group import MediaGroupBuilder
from aiogram.types import User
from src.keyboards import user_authorized_kb, admin_kb
from src.states import user_authorized_fsm
from src.database import clients_db, payments_db, promocodes_db, remnawave_db, subscriptions_db
from src.services import localization as loc
from src.services.date_formatting import format_localized_bonus_days, format_localized_datetime
from src.services.remnawave_service import (
    UNSET,
    RemnawaveError,
    create_panel_user,
    get_panel_user_squads,
    get_user_hwid_devices,
    update_panel_user,
)
from src.config import settings
from src.config.schema import GraceSettings
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


async def _send_new_client_joined_to_admin(client_id: int,
                                            fullname: str,
                                            username: str | None,
                                            telegram_id: int,
                                            subscription_url: str | None,
                                            promo: str | None) -> None:
    """Send admin notification when a new client completes registration."""
    username_str = await format_none_string(username, prefix=' @')

    if promo is None:
        ref_promo_str = loc.internal.msgs['new_client_no_ref_promo_str']
    else:
        _, client_creator_id, provided_sub_id, bonus_time = await promocodes_db.get_refferal_promo_info_by_phrase(promo)
        client_creator_name, client_creator_surname, client_creator_username, client_creator_telegram_id, *_ = await clients_db.get_client_info_by_clientID(client_creator_id)
        *_, price = await subscriptions_db.get_subscription_info_by_subID(provided_sub_id)
        client_creator_surname_str = await format_none_string(client_creator_surname)
        client_creator_username_str = await format_none_string(client_creator_username)
        ref_promo_str = loc.internal.msgs['new_client_ref_promo_str'].\
            format(promo, client_creator_name, client_creator_surname_str, client_creator_username_str, client_creator_telegram_id, format_localized_bonus_days(bonus_time), price)

    sub_url_str = f'<code>{subscription_url}</code>' if subscription_url else loc.internal.msgs['new_client_joined_no_sub_url']
    await bot.send_message(settings.bot.admin_id,
                           loc.internal.msgs['new_client_joined'].format(client_id, username_str, fullname, telegram_id, sub_url_str, ref_promo_str=ref_promo_str))


async def notify_admin_promo_entered(client_id: int, promo_phrase: str, promo_type: str):
    """Send message to administrator with information about entered by client promocode.

    :param client_id:
    :param promo_phrase: phrase of entered promocode
    :param promo_type: type of promocode as string ('global', 'local', 'ref')
    :raises Exception: wrong type of promo code was entered
    """
    name, surname, username, telegram_id, *_ = await clients_db.get_client_info_by_clientID(client_id)

    # convert surname and username for beautiful formatting
    surname_str = await format_none_string(surname)
    username_str = await format_none_string(username)

    new_sub_str = ''
    if promo_type == 'global':
        id, expiration_date, _, bonus_time = await promocodes_db.get_global_promo_info(promo_phrase)
        provided_sub_id = None

    elif promo_type == 'local':
        id, expiration_date, bonus_time, provided_sub_id = await promocodes_db.get_local_promo_info(promo_phrase)

        # if local promo changes client's subscription
        if provided_sub_id:
            *_, price = await subscriptions_db.get_subscription_info_by_subID(provided_sub_id)
            new_sub_str = loc.internal.msgs['admin_promo_was_entered_local_promo_new_sub_str'].format(price)

    elif promo_type == 'ref':
        _, client_creator_id, provided_sub_id, bonus_time = await promocodes_db.get_refferal_promo_info_by_phrase(promo_phrase)
        creator_name, *_ = await clients_db.get_client_info_by_clientID(client_creator_id)
        *_, sub_price = await subscriptions_db.get_subscription_info_by_subID(provided_sub_id)
        await bot.send_message(
            settings.bot.admin_id,
            loc.internal.msgs['admin_ref_promo_was_entered'].format(
                client_id, username_str, name, surname_str, telegram_id,
                promo_phrase, creator_name, format_localized_bonus_days(bonus_time), sub_price,
            ))
        return

    else:
        raise Exception('wrong promo type was entered')

    await bot.send_message(settings.bot.admin_id,
                           loc.internal.msgs['admin_promo_was_entered'].\
                            format(client_id, username_str, name, surname_str, telegram_id, promo_type, id,
                                   format_localized_bonus_days(bonus_time),
                                   format_localized_datetime(expiration_date),
                                   new_sub_str=new_sub_str))


async def notify_admin_payment_success(
    client_id: int,
    days_number: int,
    provider_name,  # PaymentProviderName; not annotated to avoid module-level cycle
):
    """Send message for admin with information about new successful client's payment.

    Adds a prefix to the admin notification when the paying client's
    telegram_id is in settings.payments.test_user_ids — so test transactions are
    visually distinct from real ones in the admin feed.

    :param client_id:
    :param days_number: number of days client paid for
    :param provider_name: which gateway processed the payment (yoomoney/yookassa) —
        rendered into the admin message so the operator can correlate by provider.
    """
    name, surname, username, telegram_id, *_ = await clients_db.get_client_info_by_clientID(client_id)

    # convert surname and username for beautiful formatting
    surname_str = await format_none_string(surname)
    username_str = await format_none_string(username)

    is_test_payment = telegram_id in settings.payments.test_user_ids
    test_prefix = loc.internal.msgs['admin_payment_test_prefix'] if is_test_payment else ''

    await bot.send_message(
        settings.bot.admin_id,
        loc.internal.msgs['admin_successful_payment'].format(
            days_number, client_id, username_str, name, surname_str, telegram_id,
            provider_name=str(provider_name),
            test_prefix=test_prefix,
        )
    )


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
    *_, bonus_time = await promocodes_db.get_refferal_promo_info_by_clientCreatorID(client_creator_id)

    client_creator_telegram_id = await clients_db.get_telegramID_by_clientID(client_creator_id)
    await safe_deliver(
        lambda: bot.send_message(
            client_creator_telegram_id,
            loc.internal.msgs['ref_promo_was_entered'].format(referral_client_name, referral_client_username_str, format_localized_bonus_days(bonus_time)),
        ),
        telegram_id=client_creator_telegram_id,
    )


async def notify_client_if_subscription_must_be_renewed_to_receive_configuration(telegram_id: int):
    """Send message by specified telegram_id IF client needs to renew subscription for receiving his first configuration."""

    if await subscriptions_db.is_subscription_blank(telegram_id):
        await safe_deliver(
            lambda: bot.send_message(telegram_id, loc.unauth.msgs['need_renew_sub']),
            telegram_id=telegram_id,
        )


async def check_referral_reward(ref_client_id: int):
    """Check whether the client should receive a referral fee.

    :param ref_client_id: client_id of person who registered with referral promocode
    """
    successful_payments_number = await payments_db.get_payments_successful_number(ref_client_id)
    ref_client_name, _, ref_client_username, *_, used_ref_promo_id = await clients_db.get_client_info_by_clientID(ref_client_id)

    # if client paid for subscription for the first time and used referral promo
    if successful_payments_number == 1 and used_ref_promo_id:

        # add subscription bonus time (30 days) for old client
        _, client_creator_id, *_ = await promocodes_db.get_refferal_promo_info_by_promoID(used_ref_promo_id)
        await subscriptions_db.add_subscription_period(client_creator_id, days=30)
        await sync_panel_user_safely(client_creator_id)

        # notify old client about new bonus
        # if client's username exists (add whitespace for good string formatting)
        ref_client_username_str = await format_none_string(ref_client_username)
        client_creator_telegram_id = await clients_db.get_telegramID_by_clientID(client_creator_id)
        await safe_deliver(
            lambda: bot.send_message(
                client_creator_telegram_id,
                loc.internal.msgs['ref_client_paid_for_sub'].format(ref_client_name, ref_client_username_str),
            ),
            telegram_id=client_creator_telegram_id,
        )


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
        used_ref_promo_id, _, provided_sub_id, bonus_time = await promocodes_db.get_refferal_promo_info_by_phrase(phrase)

    client_id = await clients_db.insert_client(from_user.first_name, from_user.id, from_user.last_name, from_user.username, used_ref_promo_id, provided_sub_id, bonus_time)
    if bonus_time:
        await subscriptions_db.activate_client_bonus_time(client_id)
    expire_at = await subscriptions_db.get_subscription_expiration_date_by_clientID(client_id)

    subscription_url: str | None = None
    try:
        remnawave_uuid, subscription_url = await create_panel_user(from_user.id, from_user.username, expire_at)
        await remnawave_db.insert_client_remnawave(client_id, remnawave_uuid, subscription_url)
    except RemnawaveError as exc:
        logger.error("Failed to create Remnawave user for client_id=%s tg_id=%s: %s", client_id, from_user.id, exc)
        await safe_deliver(
            lambda: bot.send_message(settings.bot.admin_id, loc.internal.msgs['new_client_remnawave_error'].format(client_id, html.escape(str(exc)))),
            telegram_id=settings.bot.admin_id,
        )

    await _send_new_client_joined_to_admin(client_id, from_user.full_name, from_user.username, from_user.id, subscription_url, data.get('promo'))

    if subscription_url:
        welcome_text = loc.internal.msgs['registration_complete']
    else:
        welcome_text = loc.internal.msgs['registration_complete_no_url']

    await send_photo_safely(from_user.id,
                            telegram_file_id=loc.auth.tfids['welcome'],
                            caption=welcome_text,
                            reply_markup=user_authorized_kb.menu)

    if data.get('promo') and subscription_url:
        await send_subscription_card(from_user.id)

    await state.clear()


class PanelSyncResult(Enum):
    """What :func:`sync_panel_user` left the panel user in."""
    NO_RECORD = 'no_record'  # client isn't provisioned in Remnawave (no clients_remnawave row)
    REGULAR = 'regular'      # expireAt = real expiration date, regular squads
    GRACE = 'grace'          # «Telegram-only» grace period


def is_in_grace_window(expiration: datetime, price, now: datetime, grace: GraceSettings) -> bool:
    """Whether the client must be in the «Telegram-only» grace period right now.

    Only paid subscriptions get grace; the window is ``[expiration, expiration + grace.days)``.
    """
    return (grace.enabled
            and price > 0
            and expiration <= now < expiration + timedelta(days=grace.days))


# One lock per client: payment webhooks, the reconciler, promo handlers and the
# subscription events worker all run in this single event loop and may sync the
# same panel user concurrently.
_panel_sync_locks: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)


async def _pre_grace_internal_squads_fallback(grace: GraceSettings) -> list[uuid.UUID]:
    """Squads to restore when nothing usable was captured: a random assignable squad + the reserve grace squad."""
    squads: list[uuid.UUID] = []
    if base := await remnawave_db.get_random_active_remnawave_squad_uuid():
        squads.append(base)
    if grace.internal_squad_uuid and grace.internal_squad_uuid not in squads:
        squads.append(grace.internal_squad_uuid)
    return squads


async def sync_panel_user(client_id: int) -> PanelSyncResult:
    """Bring the client's Remnawave user in line with the bot DB (the source of truth).

    The single place that writes expireAt/squads to the panel for an existing user:

    * outside grace — ``expireAt`` = real ``expiration_date`` (the VPN app shows the same date as the bot);
    * entering grace — capture the user's current internal/external squads from the panel into
      ``clients_remnawave``, then ``expireAt`` = expiration + grace.days, internal squads = [grace squad],
      external squad = grace external squad (only if configured);
    * still in grace — re-apply the grace state (idempotent, e.g. after a failed attempt);
    * leaving grace (payment, promo code, grace disabled) — restore the captured squads, then forget them.

    Raises RemnawaveError on panel failures; the DB grace state is written so that a retry converges.
    """
    async with _panel_sync_locks[client_id]:
        state = await remnawave_db.get_client_panel_state(client_id)
        if state is None:
            return PanelSyncResult.NO_RECORD

        grace = settings.remnawave.grace
        remnawave_uuid = state['remnawave_uuid']
        expiration = state['expiration_date']

        if is_in_grace_window(expiration, state['price'], state['now'], grace):
            if state['grace_started_at'] is None:
                internal, external = await get_panel_user_squads(remnawave_uuid)
                # A user that somehow already has only the grace squad has nothing worth restoring.
                pre_internal = internal if any(s != grace.internal_squad_uuid for s in internal) else None
                pre_external = external if external != grace.external_squad_uuid else None
                await remnawave_db.start_client_grace(client_id, pre_internal, pre_external)
                logger.info("Client %s enters grace: pre-grace internal=%s external=%s",
                            client_id, pre_internal, pre_external)

            await update_panel_user(
                remnawave_uuid,
                expire_at=expiration + timedelta(days=grace.days),
                internal_squads=[grace.internal_squad_uuid] if grace.internal_squad_uuid else UNSET,
                external_squad=grace.external_squad_uuid if grace.external_squad_uuid else UNSET,
            )
            return PanelSyncResult.GRACE

        if state['grace_started_at'] is not None:
            internal = state['pre_grace_internal_squads']
            if not internal:
                logger.warning("Client %s leaves grace without captured squads — assigning fallback squads", client_id)
                internal = await _pre_grace_internal_squads_fallback(grace)
            pre_external = state['pre_grace_external_squad_uuid']
            # Touch the external squad only if grace could have changed it.
            external = pre_external if (grace.external_squad_uuid or pre_external) else UNSET

            await update_panel_user(remnawave_uuid, expire_at=expiration,
                                    internal_squads=internal, external_squad=external)
            await remnawave_db.clear_client_grace(client_id)
            logger.info("Client %s leaves grace: restored internal=%s external=%s", client_id, internal, pre_external)
            return PanelSyncResult.REGULAR

        await update_panel_user(remnawave_uuid, expire_at=expiration)
        return PanelSyncResult.REGULAR


async def sync_panel_user_safely(client_id: int) -> None:
    """:func:`sync_panel_user` for payment / promo code paths: never raises, alerts the admin instead.

    A client without a Remnawave record is skipped with a warning (and an admin alert).
    """
    try:
        result = await sync_panel_user(client_id)
    except RemnawaveError as exc:
        logger.error("Failed to sync Remnawave user of client_id=%s: %s", client_id, exc)
        await safe_deliver(
            lambda: bot.send_message(settings.bot.admin_id, loc.internal.msgs['remnawave_expiry_sync_error'].format(client_id, html.escape(str(exc)))),
            telegram_id=settings.bot.admin_id,
        )
        return

    if result is PanelSyncResult.NO_RECORD:
        logger.warning("Client %s has no Remnawave record — skipping panel sync", client_id)
        await safe_deliver(
            lambda: bot.send_message(settings.bot.admin_id, loc.internal.msgs['remnawave_expiry_sync_no_record'].format(client_id)),
            telegram_id=settings.bot.admin_id,
        )


async def _get_grace_until(telegram_id: int) -> datetime | None:
    """Return when the client's current «Telegram-only» grace period ends, or None if not in grace."""
    if await remnawave_db.get_client_grace_started_at_by_telegramID(telegram_id) is None:
        return None
    expiration_date = await subscriptions_db.get_subscription_expiration_date(telegram_id)
    if expiration_date is None:
        return None
    grace_until = expiration_date + timedelta(days=settings.remnawave.grace.days)
    now = datetime.now(ZoneInfo(settings.tz)).replace(tzinfo=None)  # DB timestamps are naive, in settings.tz
    return grace_until if now < grace_until else None


async def build_subscription_card(telegram_id: int) -> str:
    """Return the «Subscription information» card text for the client with specified telegram_id.

    Active devices are counted from Remnawave HWID devices; the count is shown as «—»
    when the subscription is blank, the client isn't provisioned in the panel, or the panel is unreachable.
    """
    client_id = await clients_db.get_clientID_by_telegramID(telegram_id)

    subscription_url = await remnawave_db.get_client_remnawave_subscription_url_by_telegramID(telegram_id)
    url = subscription_url or loc.auth.msgs['subscription_info_url_pending']

    # Determine status and expiry line.
    # Priority: blank (EPOCH) → free → active → inactive/expired.
    # blank and free subscriptions carry no expiry line.
    is_blank = await subscriptions_db.is_subscription_blank(telegram_id)
    if is_blank:
        status = loc.auth.msgs['subscription_info_status_blank']
        expiry = ''
        url = loc.auth.msgs['subscription_info_url_blank']
    elif await subscriptions_db.is_subscription_free(telegram_id):
        status = loc.auth.msgs['subscription_info_status_free']
        expiry = ''
    elif await subscriptions_db.is_subscription_active(telegram_id):
        status = loc.auth.msgs['subscription_info_status_active']
        expiration_date = await subscriptions_db.get_subscription_expiration_date(telegram_id)
        expiry = loc.auth.msgs['subscription_info_expiry_line_active'].format(
            format_localized_datetime(expiration_date)) if expiration_date else ''
    elif grace_until := await _get_grace_until(telegram_id):
        status = loc.auth.msgs['subscription_info_status_grace']
        expiration_date = await subscriptions_db.get_subscription_expiration_date(telegram_id)
        expiry = loc.auth.msgs['subscription_info_expiry_line_grace'].format(
            format_localized_datetime(expiration_date), format_localized_datetime(grace_until))
    else:
        status = loc.auth.msgs['subscription_info_status_inactive']
        expiration_date = await subscriptions_db.get_subscription_expiration_date(telegram_id)
        expiry = loc.auth.msgs['subscription_info_expiry_line_inactive'].format(
            format_localized_datetime(expiration_date)) if expiration_date else ''

    *_, price = await subscriptions_db.get_subscription_info_by_clientID(client_id)
    max_devices = await subscriptions_db.get_max_configurations_by_telegramID(telegram_id)

    devices_count = '–'
    remnawave_uuid = await remnawave_db.get_client_remnawave_uuid_by_telegramID(telegram_id)
    if not is_blank and remnawave_uuid is not None:
        try:
            devices_count = len(await get_user_hwid_devices(remnawave_uuid))
        except RemnawaveError as exc:
            logger.warning("Failed to fetch HWID devices for tg_id=%s: %s", telegram_id, exc)

    return loc.auth.msgs['subscription_info'].format(
        status=status, expiry=expiry, url=url,
        price=price, active_devices=f'{devices_count} из {max_devices}',
    )


async def send_subscription_card(telegram_id: int) -> None:
    """Send the «Subscription information» card to a DB-sourced recipient, e.g. after a first payment or referral promo."""
    text = await build_subscription_card(telegram_id)
    await safe_deliver(
        lambda: bot.send_message(telegram_id, text, reply_markup=user_authorized_kb.my_subscription_inline),
        telegram_id=telegram_id,
    )


async def safe_delete_message(chat_id: int, message_id: int | None) -> None:
    """Delete a message ignoring 'message to delete not found' errors.

    No-op when ``message_id`` is ``None``. Callers commonly source the id from
    DB helpers like ``get_payment_last_message_id`` that legitimately return
    ``None`` when there's nothing to delete (e.g. user cancelled in
    ``PaymentMenu.provider_selection`` before any payment was created, or no
    payments exist for the client at all). Without this guard aiogram's
    Pydantic validation crashes the handler.
    """
    if message_id is None:
        return
    try:
        await bot.delete_message(chat_id, message_id)
    except TelegramBadRequest:
        pass


async def finalize_successful_payment(
    payment_id: int,
    client_id: int,
    days_number: int,
    provider_name,  # PaymentProviderName; not annotated to avoid module-level cycle
) -> None:
    """Post-finalize business chain after a payment is marked SUCCEEDED in DB.

    The atomic ``payments``/``clients_subscriptions`` update has already been
    performed by ``PaymentService`` via ``repository.claim_finalize`` before
    this is invoked. This function owns everything that happens AFTER the DB
    is consistent:

    1. Sync new expiry to Remnawave Panel.
    2. Pay out the referral bonus if this is the user's first successful payment.
    3. Notify the admin.
    4. Fiscalize income in «Мой налог» if enabled for ``provider_name`` (records
       the receipt URL in DB; URL is included in the user notification below).
    5. Notify the user: delete the payment-link message, reset FSM if they're
       still in the verification flow, send the "payment successful" message
       (with the receipt URL if step 4 succeeded; with the renewal keyboard
       when the user was actively waiting).
    6. On the client's first successful payment, send the subscription card so
       a new user sees how to connect right away.

    Each step is independently wrapped so a failure in one (e.g. Remnawave
    panel temporarily unreachable, «Мой налог» down) does not skip the others.
    Errors are logged but never propagated — the payment is already valid in
    DB and that's the source of truth. Fiscalization failures additionally
    trigger an admin alert so the receipt can be issued manually in «Мой налог».

    Wired as the ``on_payment_succeeded`` callback in
    :mod:`src.payments.runtime`. Webhook deliveries, the APScheduler reconciler,
    and manual user re-checks all end up here through the same path.
    """
    try:
        await sync_panel_user_safely(client_id)
    except Exception:
        logger.exception(
            "sync_panel_user_safely failed for client_id=%s after payment_id=%s",
            client_id, payment_id,
        )

    try:
        await check_referral_reward(client_id)
    except Exception:
        logger.exception(
            "check_referral_reward failed for client_id=%s after payment_id=%s",
            client_id, payment_id,
        )

    try:
        await notify_admin_payment_success(client_id, days_number, provider_name)
    except Exception:
        logger.exception(
            "notify_admin_payment_success failed for client_id=%s after payment_id=%s",
            client_id, payment_id,
        )

    receipt_url = await _try_fiscalize_income(payment_id, days_number, provider_name)

    # ``send_receipt`` is the UI policy: do we put the URL in the buyer's
    # message? Independent of whether registration happened — the URL stays
    # in ``payments.fiscal_receipt_url`` either way for audit / re-send.
    display_receipt_url = (
        receipt_url if settings.payments.fiscalization.send_receipt else None
    )

    try:
        await _notify_user_payment_succeeded(payment_id, client_id, receipt_url=display_receipt_url)
    except Exception:
        logger.exception(
            "_notify_user_payment_succeeded failed for client_id=%s after payment_id=%s",
            client_id, payment_id,
        )

    try:
        await _send_subscription_card_after_first_payment(client_id)
    except Exception:
        logger.exception(
            "_send_subscription_card_after_first_payment failed for client_id=%s after payment_id=%s",
            client_id, payment_id,
        )


async def _send_subscription_card_after_first_payment(client_id: int) -> None:
    """Send the subscription card if this is the client's first successful payment."""
    if await payments_db.get_payments_successful_number(client_id) != 1:
        return

    telegram_id = await clients_db.get_telegramID_by_clientID(client_id)
    if telegram_id is None:
        return

    await send_subscription_card(telegram_id)


async def _try_fiscalize_income(payment_id: int, days_number: int, provider_name) -> str | None:
    """Run ``provider.fiscalize_income`` and persist the receipt URL.

    Returns the public print-URL on success, ``None`` if fiscalization is
    disabled for this provider OR if it failed. Failures trigger an admin
    alert so a manual receipt can be issued in «Мой налог».

    Imports happen inside the function — at module-load time ``src.payments.runtime``
    is still being constructed (it imports this module via the
    ``on_payment_succeeded`` wiring), so a module-level import would cycle.
    """
    from src.payments.runtime import payment_service

    provider = payment_service.providers.get(provider_name)
    if provider is None:
        logger.warning(
            "fiscalize: provider %s not in registry for payment_id=%s — skipping",
            provider_name, payment_id,
        )
        return None

    amount = await payments_db.get_payment_amount(payment_id)
    if amount is None:
        logger.error("fiscalize: payment_id=%s not found in DB", payment_id)
        return None

    description = loc.internal.msgs['fiscal_receipt_description'].format(days_number)

    try:
        receipt = await provider.fiscalize_income(
            payment_id=payment_id, amount=amount, description=description,
        )
    except Exception:
        logger.exception(
            "fiscalize_income raised for payment_id=%s provider=%s — admin will be alerted",
            payment_id, provider_name,
        )
        await _alert_admin_fiscalization_failed(payment_id)
        return None

    if receipt is None:
        # Provider's fiscalization is disabled — silent no-op, not an error.
        return None

    try:
        await payments_db.update_payment_fiscal_receipt_url(payment_id, receipt.print_url)
    except Exception:
        logger.exception(
            "Failed to persist fiscal_receipt_url for payment_id=%s "
            "(receipt was registered with ФНС but DB is now inconsistent)",
            payment_id,
        )
        # We still return the URL — the user gets their receipt even if our
        # audit column failed to update.

    logger.info(
        "Income registered in Мой налог for payment_id=%s receipt_url=%s",
        payment_id, receipt.print_url,
    )
    return receipt.print_url


async def _alert_admin_fiscalization_failed(payment_id: int) -> None:
    """Best-effort admin notification on fiscalization failure."""
    try:
        await safe_deliver(
            lambda: bot.send_message(
                settings.bot.admin_id,
                loc.internal.msgs['admin_fiscalization_failed'].format(payment_id),
            ),
            telegram_id=settings.bot.admin_id,
        )
    except Exception:
        logger.exception("admin alert for fiscalization failure also failed")


async def _notify_user_payment_succeeded(
    payment_id: int,
    client_id: int,
    *,
    receipt_url: str | None = None,
) -> None:
    """Delete payment-link message, reset FSM if in verification, send success message.

    Keyboard policy: if the user is currently in the verification state, we
    were the active conversation — reset FSM to ``menu`` and attach the
    renewal keyboard so the flow continues coherently. Otherwise (paid hours
    ago, currently doing something else), send the success message without a
    keyboard — interrupting their current screen would be jarring.

    Receipt: when ``receipt_url`` is provided (fiscalization on and succeeded),
    we use the ``payment_successful_with_receipt`` template that includes a
    link to the «Мой налог» print page. When ``None`` (fiscalization off, or
    on but failed), use the plain template — user can't distinguish "no
    receipt configured" from "receipt failed", which is intentional (admin
    handles failed cases separately via the alert).

    Best-effort: all errors are caught at the caller (``finalize_successful_payment``).
    """
    from src.runtime import dp  # imported here to avoid moving the import to module top
    from aiogram.fsm.storage.base import StorageKey

    telegram_id = await clients_db.get_telegramID_by_clientID(client_id)
    if telegram_id is None:
        logger.warning("Cannot notify user payment_id=%s — telegram_id not found for client_id=%s", payment_id, client_id)
        return

    telegram_message_id = await payments_db.get_payment_telegram_message_id(payment_id)
    if telegram_message_id is not None:
        await safe_delete_message(telegram_id, telegram_message_id)

    # FSM reset is only meaningful when the user is still in the verification
    # flow. Otherwise we leave their state alone — they may be doing something
    # unrelated, and unexpectedly clearing their state would be confusing.
    storage = dp.storage
    key = StorageKey(bot_id=bot.id, chat_id=telegram_id, user_id=telegram_id)
    was_in_payment_flow = False
    try:
        current_state = await storage.get_state(key)
        if current_state == user_authorized_fsm.PaymentMenu.verification.state:
            was_in_payment_flow = True
            await storage.set_state(key, user_authorized_fsm.PaymentMenu.menu.state)
    except Exception:
        logger.warning("Failed to read/reset FSM state for tg_id=%s", telegram_id, exc_info=True)

    reply_markup = user_authorized_kb.sub_renewal if was_in_payment_flow else None

    if receipt_url is not None:
        text = loc.internal.msgs['payment_successful_with_receipt'].format(payment_id, receipt_url)
    else:
        text = loc.internal.msgs['payment_successful'].format(payment_id)

    await safe_deliver(
        lambda: bot.send_message(telegram_id, text, reply_markup=reply_markup),
        telegram_id=telegram_id,
    )

