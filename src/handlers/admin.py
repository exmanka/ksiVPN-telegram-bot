import logging
import aiofiles
import html
from decimal import Decimal
from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import Message, CallbackQuery
from src.middlewares import admin_mw
from src.keyboards import admin_kb, user_authorized_kb, user_unauthorized_kb
from src.states import admin_fsm
from src.database import postgres_dbms
from src.services import internal_functions, localization as loc
from src.services.date_formatting import format_localized_datetime
from src.config import settings
from src.runtime import bot, dp


logger = logging.getLogger(__name__)


router = Router(name="admin")


async def _format_failed_delivery_row(
    idx: int,
    telegram_id: int,
    status: internal_functions.DeliveryStatus,
    err: str | None,
) -> str:
    """Build one report line for a broadcast recipient who couldn't receive the message.

    Fetches client info from DB and appends a human-readable status label.
    Used in both broadcast handlers to keep their loop bodies identical.
    """
    _, name, surname, username, *_ = await postgres_dbms.get_client_info_by_telegramID(telegram_id)
    row = loc.admn.msgs['clients_row_str'].format(
        idx + 1,
        html.escape(name),
        html.escape(str(surname)),
        html.escape(str(username)),
        telegram_id,
    )
    labels = {
        internal_functions.DeliveryStatus.BLOCKED: '(has blocked bot)',
        internal_functions.DeliveryStatus.CHAT_NOT_FOUND: '(chat not found)',
        internal_functions.DeliveryStatus.ERROR: f'(unexpected error: {html.escape(str(err))})',
    }
    return row + ' ' + labels[status] + '\n'


@router.message(
    F.text.in_({loc.admn.btns[key] for key in ('reset_fsm_1', 'reset_fsm_2')}),
    StateFilter('*'),
)
@router.message(Command(commands=['reset']), StateFilter('*'))
@admin_mw.admin_only()
async def fsm_reset(message: Message, state: FSMContext):
    """Cancel admin's FSM state and return to menu keyboard regardless of machine state."""
    await state.clear()
    await message.answer(loc.admn.msgs['reset_fsm_keyboard'], reply_markup=admin_kb.menu)


@router.message(Command(commands=['admin']), StateFilter('*'))
@admin_mw.admin_only()
async def show_admin_keyboard(message: Message):
    """Send message with information about admin's commands and show admin keyboard."""
    await message.reply(loc.admn.msgs['admin_kb_info'], reply_markup=admin_kb.menu)


@router.message(F.text == loc.admn.btns['send_message'])
@admin_mw.admin_only()
async def notifications_menu(message: Message):
    """Show keyboard for sending messages via bot."""
    await message.answer(loc.admn.msgs['go_send_message_menu'], reply_markup=admin_kb.notification)


@router.message(F.text == loc.admn.btns['send_message_everyone'])
@admin_mw.admin_only()
async def notifications_send_message_everyone_fsm_start(message: Message, state: FSMContext):
    """Start FSM for sending message to every client who wrote bot at least one time."""
    await state.set_state(admin_fsm.SendMessage.everyone_decision)
    await message.answer(loc.admn.msgs['fsm_start'])
    await message.answer(loc.admn.msgs['message_everyone_info'])


@router.message(StateFilter(admin_fsm.SendMessage.everyone_decision))
@admin_mw.admin_only()
async def notifications_send_message_everyone(message: Message, state: FSMContext):
    """Catch message, echo message and send it to every client who wrote bot at least one time, if admin wrote /perfect."""
    if message.text and message.text == '/perfect':
        ignored_clients_str = ''
        data = await state.get_data()

        for idx, [telegram_id] in enumerate(await postgres_dbms.get_clients_telegram_ids()):
            status, err = await internal_functions.safe_deliver(
                lambda tid=telegram_id: bot.copy_message(tid, data['message_chat_id'], data['message_id']),
                telegram_id=telegram_id,
            )
            if status is internal_functions.DeliveryStatus.OK:
                continue
            ignored_clients_str += await _format_failed_delivery_row(idx, telegram_id, status, err)

        if ignored_clients_str:
            answer_message = loc.admn.msgs['message_everyone_was_sent'] + '\n\n' + loc.admn.msgs['message_everyone_somebody_didnt_recieve']\
                .format(ignored_clients_str=ignored_clients_str)
            await internal_functions.send_long_message(message, answer_message)
        else:
            await message.answer(loc.admn.msgs['message_everyone_was_sent'] + '\n\n' + loc.admn.msgs['message_everyone_everybody_received'])

        await fsm_reset(message, state)
        return

    await message.answer(loc.admn.msgs['how_message_looks'])

    # echo message showing how will be displayed admin's message for clients
    await bot.copy_message(message.from_user.id, message.chat.id, message.message_id)

    # save last message to send it if admin write /perfect
    await state.update_data(message_chat_id=message.chat.id, message_id=message.message_id)


# ---------------------------------------------------------------------------
# ONE-OFF: announcement broadcast that resets FSM and re-applies the main reply
# keyboard for authorized recipients. Mirrors the regular `send_message_everyone`
# flow but additionally:
#   * picks reply_markup per recipient (authorized -> user_authorized_kb.menu,
#     unauthorized -> user_unauthorized_kb.welcome) and passes it to copy_message;
#   * clears FSM state for authorized recipients via dp.fsm.storage + StorageKey;
#   * skips the admin themselves (they're mid-flow typing /perfect).
# Delete this block, the matching FSM state and the keyboard button after the
# announcement has been sent.
# ---------------------------------------------------------------------------
@router.message(F.text == loc.admn.btns['send_message_everyone_with_reset'])
@admin_mw.admin_only()
async def notifications_send_message_everyone_with_reset_fsm_start(message: Message, state: FSMContext):
    """Start FSM for the one-off announcement (broadcast + reset FSM + main keyboard)."""
    await state.set_state(admin_fsm.SendMessage.everyone_reset_decision)
    await message.answer(loc.admn.msgs['fsm_start'])
    await message.answer(loc.admn.msgs['message_everyone_with_reset_info'])


@router.message(StateFilter(admin_fsm.SendMessage.everyone_reset_decision))
@admin_mw.admin_only()
async def notifications_send_message_everyone_with_reset(message: Message, state: FSMContext):
    """Catch message; on /perfect broadcast it to every client + reset FSM / set kb for authorized."""
    if message.text and message.text == '/perfect':
        ignored_clients_str = ''
        data = await state.get_data()
        admin_id = settings.bot.admin_id

        for idx, [telegram_id] in enumerate(await postgres_dbms.get_clients_telegram_ids()):
            if telegram_id == admin_id:
                # Don't reset the admin's own FSM — they're literally in the middle of running /perfect.
                continue

            is_authorized = await postgres_dbms.is_user_registered(telegram_id)
            keyboard = user_authorized_kb.menu if is_authorized else user_unauthorized_kb.welcome

            # Reset FSM unconditionally: unauthorized users may be sitting in
            # RegistrationMenu.promo (their next text would otherwise be parsed as
            # a referral promo code). RedisStorage clear is a no-op when no state
            # is set, so it's safe for users with empty FSM too.
            key = StorageKey(bot_id=bot.id, chat_id=telegram_id, user_id=telegram_id)
            await FSMContext(storage=dp.fsm.storage, key=key).clear()

            status, err = await internal_functions.safe_deliver(
                lambda tid=telegram_id, kb=keyboard: bot.copy_message(
                    tid, data['message_chat_id'], data['message_id'], reply_markup=kb,
                ),
                telegram_id=telegram_id,
            )
            if status is internal_functions.DeliveryStatus.OK:
                continue
            ignored_clients_str += await _format_failed_delivery_row(idx, telegram_id, status, err)

        if ignored_clients_str:
            answer_message = loc.admn.msgs['message_everyone_was_sent'] + '\n\n' + loc.admn.msgs['message_everyone_somebody_didnt_recieve']\
                .format(ignored_clients_str=ignored_clients_str)
            await internal_functions.send_long_message(message, answer_message)
        else:
            await message.answer(loc.admn.msgs['message_everyone_was_sent'] + '\n\n' + loc.admn.msgs['message_everyone_everybody_received'])

        await fsm_reset(message, state)
        return

    await message.answer(loc.admn.msgs['how_message_looks'])

    # echo message showing how the announcement will be displayed for clients
    await bot.copy_message(message.from_user.id, message.chat.id, message.message_id)

    # save last message to send it if admin write /perfect
    await state.update_data(message_chat_id=message.chat.id, message_id=message.message_id)


@router.message(F.text == loc.admn.btns['send_message_selected'])
@admin_mw.admin_only()
async def notifications_send_message_selected_fsm_start(message: Message, state: FSMContext):
    """Start FSM for sending message to selected clients."""
    await state.set_state(admin_fsm.SendMessage.selected_list)
    await message.answer(loc.admn.msgs['fsm_start'])
    await message.answer(loc.admn.msgs['message_selected_info'])


@router.message(StateFilter(admin_fsm.SendMessage.selected_list))
@admin_mw.admin_only()
async def notifications_send_message_selected_list(message: Message, state: FSMContext):
    """Parse entered by admin list of selected clients for sending them some message."""
    selected_clients = message.text.split(' ')
    selected_clients_telegram_ids = []
    for client in selected_clients:
        if client[0] == '@':
            if telegram_id := await postgres_dbms.get_telegramID_by_username(client):
                selected_clients_telegram_ids.append(telegram_id)
        elif await postgres_dbms.get_clientID_by_telegramID(int(client)):
            selected_clients_telegram_ids.append(int(client))

    await state.update_data(selected_telegram_ids=selected_clients_telegram_ids)
    await state.set_state(admin_fsm.SendMessage.selected_decision)

    selected_clients_str = ''
    for idx, telegram_id in enumerate(selected_clients_telegram_ids):
        _, name, surname, username, *_ = await postgres_dbms.get_client_info_by_telegramID(telegram_id)
        selected_clients_str += loc.admn.msgs['clients_row_str'].format(idx + 1, html.escape(name), html.escape(str(surname)), html.escape(str(username)), telegram_id) + '\n'

    if selected_clients_str:
        await internal_functions.send_long_message(message, loc.admn.msgs['message_selected_somebody_received'].format(selected_clients_str=selected_clients_str))
        await message.answer(loc.admn.msgs['message_selected_enter_message_info'])
    else:
        await message.answer(loc.admn.msgs['message_selected_nobody_received'])


@router.message(StateFilter(admin_fsm.SendMessage.selected_decision))
@admin_mw.admin_only()
async def notifications_send_message_selected(message: Message, state: FSMContext):
    """Catch message, echo message and send it to selected clients, if admin wrote /perfect."""
    if message.text and message.text == '/perfect':
        ignored_clients_str = ''
        data = await state.get_data()

        for idx, telegram_id in enumerate(data['selected_telegram_ids']):
            status, err = await internal_functions.safe_deliver(
                lambda tid=telegram_id: bot.copy_message(tid, data['message_chat_id'], data['message_id']),
                telegram_id=telegram_id,
            )
            if status is internal_functions.DeliveryStatus.OK:
                continue
            ignored_clients_str += await _format_failed_delivery_row(idx, telegram_id, status, err)

        if ignored_clients_str:
            answer_message = loc.admn.msgs['message_everyone_was_sent'] + '\n\n' + loc.admn.msgs['message_everyone_somebody_didnt_recieve']\
                .format(ignored_clients_str=ignored_clients_str)
            await internal_functions.send_long_message(message, answer_message)
        else:
            await message.answer(loc.admn.msgs['message_everyone_was_sent'] + '\n\n' + loc.admn.msgs['message_everyone_everybody_received'])

        await fsm_reset(message, state)
        return

    await message.answer('Вот так будет выглядеть Ваше сообщение:')

    await bot.copy_message(message.from_user.id, message.chat.id, message.message_id)

    await state.update_data(message_chat_id=message.chat.id, message_id=message.message_id)


@router.message(F.text == loc.admn.btns['clients_info'])
@router.message(Command(commands=['clients']))
@admin_mw.admin_only()
async def show_clients_info(message: Message):
    """Send message with information about all clients. Add /clients [-h] flag to get human-readable message."""
    is_human_readable = False
    command_flags: list = message.text.split(' ')
    if len(command_flags) > 1 and command_flags[1] == '-h':
        is_human_readable = True

    await message.answer(loc.admn.msgs['clients_info'])

    answer_message = ''
    for [client_id] in await postgres_dbms.get_clients_ids():
        name, surname, username, telegram_id, register_date, used_ref_promo_id = await postgres_dbms.get_client_info_by_clientID(client_id)
        register_date_parsed = format_localized_datetime(register_date)
        *_, sub_price = await postgres_dbms.get_subscription_info_by_clientID(client_id)
        sub_expiration_date_parsed = format_localized_datetime(await postgres_dbms.get_subscription_expiration_date(telegram_id))
        paid_sum: Decimal = await postgres_dbms.get_payments_successful_sum(client_id)
        ref_promo_info = await postgres_dbms.get_refferal_promo_info_by_clientCreatorID(client_id)
        ref_promo_phrase = ref_promo_info[1] if ref_promo_info else '—'

        answer_message_row = ''
        if await postgres_dbms.is_subscription_active(telegram_id) or await postgres_dbms.is_subscription_free(telegram_id):
            answer_message_row += loc.admn.msgs['clients_info_sub_active']
        else:
            answer_message_row += loc.admn.msgs['clients_info_sub_inactive']

        answer_message_row +=\
            f"| <b>{client_id}</b> "\
            f"|{await internal_functions.format_none_string(html.escape(str(username)) if username else None)} <code>{html.escape(str(name))}{await internal_functions.format_none_string(html.escape(str(surname)) if surname else None)}</code> <code>{telegram_id}</code>, {register_date_parsed[:-8]} "\
            f"| {sub_price}₽/мес, <b>{sub_expiration_date_parsed}</b> "\
            f"| paid: {float(paid_sum):g}₽ "\
            f"| <code>{html.escape(str(ref_promo_phrase))}</code> "

        who_invited_str = ''
        if used_ref_promo_id is not None:
            _, who_invited_client_id, *_ = await postgres_dbms.get_refferal_promo_info_by_promoID(used_ref_promo_id)
            who_invited_name, who_invited_surname, who_invited_username, who_invited_telegram_id, *_ = await postgres_dbms.get_client_info_by_clientID(who_invited_client_id)
            who_invited_str +=\
                f"| {await internal_functions.format_none_string(html.escape(str(who_invited_username)) if who_invited_username else None)} <code>{html.escape(str(who_invited_name))}{await internal_functions.format_none_string(html.escape(str(who_invited_surname)) if who_invited_surname else None)}</code> <code>{who_invited_telegram_id}</code>"

        answer_message_row += who_invited_str
        answer_message += answer_message_row + '\n' + '\n' * int(is_human_readable)

    wrapper = None if is_human_readable else '<pre>{text}</pre>'
    await internal_functions.send_long_message(message, answer_message, wrapper=wrapper)


@router.message(F.text == loc.admn.btns['show_earnings'])
@admin_mw.admin_only()
async def show_earnings(message: Message):
    """Send message with information about earned money per current month."""
    earnings_per_current_month: Decimal = await postgres_dbms.get_earnings_per_month()
    await message.answer(loc.admn.msgs['show_earnings'].format(float(earnings_per_current_month)))


@router.message(F.text == loc.admn.btns['show_logs'])
@router.message(Command(commands=['logs']))
@admin_mw.admin_only()
async def show_logs(message: Message):
    """Send message with last N rows of bot logs.

    Can be use both /logs and /logs <last_rows_number> ways."""
    last_rows_number = 50
    last_rows_number_list = message.text.split(' ')[1:]
    if last_rows_number_list:
        last_rows_number = int(last_rows_number_list[0])

    await message.answer(loc.admn.msgs['show_logs_info'].format(last_rows_number))

    last_rows_counter = 0
    async with aiofiles.open('logs/bot.log', mode='rb') as f:
        try:
            await f.seek(-2, 2)
            while last_rows_counter < last_rows_number:
                await f.seek(-2, 1)
                if await f.read(1) == b'\n':
                    last_rows_counter += 1
        except OSError:
            await f.seek(0)

        last_lines = (await f.read()).decode()

    await internal_functions.send_long_message(message, html.escape(last_lines), wrapper='<pre>{text}</pre>')


@router.message(F.text == loc.admn.btns['get_file_id'])
@router.message(Command(commands=['fileid']))
@admin_mw.admin_only()
async def get_file_id(message: Message):
    """Send message with added file id."""
    if message.photo:
        await message.answer(loc.admn.msgs['file_id_photo'].format(message.photo[0].file_id))
    elif message.document:
        await message.answer(loc.admn.msgs['file_id_document'].format(message.document.file_id))
    else:
        await message.answer(loc.admn.msgs['error_no_file_for_file_id'])


def register_handlers_admin(dp):
    """Attach the `admin` router to the dispatcher."""
    dp.include_router(router)
