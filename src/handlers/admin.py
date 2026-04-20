import logging
import aiofiles
import html
from decimal import Decimal
from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from src.middlewares import admin_mw
from src.keyboards import admin_kb
from src.states import admin_fsm
from src.database import postgres_dbms
from src.services import internal_functions, localization as loc
from src.services.date_formatting import format_localized_datetime
from src.runtime import bot


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
        await message.answer(loc.admn.msgs['message_selected_somebody_received'].format(selected_clients_str=selected_clients_str))
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


@router.message(Command(commands=['configs']))
@admin_mw.admin_only()
async def check_user_configs(message: Message):
    """Send messages with configurations of another client."""
    try:
        user_info = message.text.split(' ')[1]

        if user_info[0] == '@':
            client_id = await postgres_dbms.get_clientID_by_username(user_info)
        else:
            client_id = await postgres_dbms.get_clientID_by_telegramID(int(user_info))
    except Exception as e:
        await message.answer(loc.admn.msgs['error_unrecognized'].format(e))
        return

    configurations_info = await postgres_dbms.get_configurations_info(client_id)
    await message.answer(loc.auth.msgs['configs_info'].format(len(configurations_info)))

    for file_type, date_of_receipt, os, name, country, city, bandwidth, ping, available_services, link, config_id, server_name in configurations_info:
        await internal_functions.send_configuration(message.from_user.id, file_type, date_of_receipt, os, name, country, city, bandwidth, ping, available_services, link, config_id, server_name)


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
        config_num = await postgres_dbms.get_configurations_number(client_id)
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
            f"| configs: {config_num} "\
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


@router.callback_query(F.data.func(lambda d: d is not None and ':' in d and d.split(':', 1)[0].isdigit()))
@admin_mw.admin_only()
async def send_configuration_fsm_start(call: CallbackQuery, state: FSMContext):
    """Start FSM for sending configurations for a client after pressing inline button and send instruction."""
    await state.set_state(admin_fsm.SendConfig.ready)
    telegram_id_str, _, os_alias = call.data.partition(':')
    await state.update_data(telegram_id=telegram_id_str, os_alias=os_alias)

    await call.message.answer(loc.admn.msgs['fsm_start'])
    await call.message.answer(loc.admn.msgs['send_configuration_info'])
    await call.answer()


@router.message(
    StateFilter(admin_fsm.SendConfig.ready),
    F.content_type.in_({'text', 'document'}),
)
@admin_mw.admin_only()
async def send_configuration(message: Message, state: FSMContext):
    """Check configuration sended by admin and send it to client."""
    data = await state.get_data()
    telegram_id = int(data['telegram_id'])
    flag_os = data['os_alias']
    client_id = await postgres_dbms.get_clientID_by_telegramID(telegram_id)

    try:
        if text := message.text:
            file_type = 'link'
            flag_protocol, flag_location, flag_link = text.split(' ')
            await internal_functions.create_configuration(client_id, file_type, flag_protocol, flag_location, flag_os, flag_link)
            _, date_of_receipt, os, name, country, city, bandwidth, ping, available_services, link, config_id, server_name = (await postgres_dbms.get_configurations_info(client_id))[-1]

        elif document := message.document:
            file_type = 'document'
            flag_protocol, flag_location = message.caption.split(' ')
            telegram_file_id = document.file_id
            await internal_functions.create_configuration(client_id, file_type, flag_protocol, flag_location, flag_os, telegram_file_id=telegram_file_id)
            file_type, date_of_receipt, os, name, country, city, bandwidth, ping, available_services, link, config_id, server_name = (await postgres_dbms.get_configurations_info(client_id))[-1]

        else:
            await message.reply(loc.admn.msgs['error_bad_attachment'])
            return

        # Client may have blocked the bot between requesting the config and admin issuing it;
        # wrap each delivery so the admin handler doesn't crash on that path.
        await internal_functions.safe_deliver(
            lambda: bot.send_message(telegram_id, loc.auth.msgs['config_was_received']),
            telegram_id=telegram_id,
        )
        config_status, config_err = await internal_functions.safe_deliver(
            lambda: internal_functions.send_configuration(telegram_id, file_type, date_of_receipt, os, name, country, city, bandwidth, ping, available_services, link, config_id, server_name),
            telegram_id=telegram_id,
        )
        await internal_functions.safe_deliver(
            lambda: bot.send_message(telegram_id, loc.auth.msgs['configs_rules']),
            telegram_id=telegram_id,
        )
        if config_status is internal_functions.DeliveryStatus.OK:
            await message.reply(loc.admn.msgs['config_was_sent'].format(file_type))
        else:
            await message.reply(loc.admn.msgs['config_was_sent'].format(file_type) + f'\n\n⚠️ client delivery status: {config_status.value}: {config_err}')
        await state.clear()

    except ValueError as ve:
        await message.reply(loc.admn.msgs['error_bad_flags_number'].format(ve))
    except Exception as e:
        await message.reply(loc.admn.msgs['error_unrecognized'].format(e))


def register_handlers_admin(dp):
    """Attach the `admin` router to the dispatcher."""
    dp.include_router(router)
