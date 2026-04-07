import logging
import aiofiles
import html
from decimal import Decimal
from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from src.middlewares import admin_mw
from src.keyboards import admin_kb
from src.states import admin_fsm
from src.database import postgres_dbms
from src.services import internal_functions, localization as loc
from bot_init import bot, POSTGRES_DB, POSTGRES_PASSWORD


logger = logging.getLogger(__name__)


router = Router(name="admin")


@admin_mw.admin_only()
async def fsm_reset(message: Message, state: FSMContext):
    """Cancel admin's FSM state and return to menu keyboard regardless of machine state."""
    await state.clear()
    await message.answer(loc.admn.msgs['reset_fsm_keyboard'], reply_markup=admin_kb.menu)


@admin_mw.admin_only()
async def show_admin_keyboard(message: Message):
    """Send message with information about admin's commands and show admin keyboard."""
    await message.reply(loc.admn.msgs['admin_kb_info'], reply_markup=admin_kb.menu)


@admin_mw.admin_only()
async def notifications_menu(message: Message):
    """Show keyboard for sending messages via bot."""
    await message.answer(loc.admn.msgs['go_send_message_menu'], reply_markup=admin_kb.notification)


@admin_mw.admin_only()
async def notifications_send_message_everyone_fsm_start(message: Message, state: FSMContext):
    """Start FSM for sending message to every client who wrote bot at least one time."""
    await state.set_state(admin_fsm.SendMessage.everyone_decision)
    await message.answer(loc.admn.msgs['fsm_start'])
    await message.answer(loc.admn.msgs['message_everyone_info'])


@admin_mw.admin_only()
async def notifications_send_message_everyone(message: Message, state: FSMContext):
    """Catch message, echo message and send it to every client who wrote bot at least one time, if admin wrote /perfect."""
    if message.text and message.text == '/perfect':
        ignored_clients_str = ''
        data = await state.get_data()

        # TODO: перенести обработки ошибок в internal_functions.send_message_by_telegram_id
        for idx, [telegram_id] in enumerate(await postgres_dbms.get_clients_telegram_ids()):
            try:
                await bot.copy_message(telegram_id, data['message_chat_id'], data['message_id'])

            except TelegramForbiddenError as bb:
                # client blocked the bot or deactivated their account
                _, name, surname, username, *_ = await postgres_dbms.get_client_info_by_telegramID(telegram_id)
                logger.info(f"Can't send message to client {name} {telegram_id}: {bb}")
                ignored_clients_str += loc.admn.msgs['clients_row_str'].format(idx + 1, html.escape(name), html.escape(str(surname)), html.escape(str(username)), telegram_id) + '(has blocked bot)\n'

            except TelegramBadRequest:
                # chat not found / user gone
                _, name, surname, username, *_ = await postgres_dbms.get_client_info_by_telegramID(telegram_id)
                ignored_clients_str += loc.admn.msgs['clients_row_str'].format(idx + 1, html.escape(name), html.escape(str(surname)), html.escape(str(username)), telegram_id)

            except Exception as e:
                logger.warning(f"Can't send message to client telegram_id={telegram_id} due to unexpected error: {e}")

        if ignored_clients_str:
            answer_message = loc.admn.msgs['message_everyone_was_sent'] + '\n\n' + loc.admn.msgs['message_everyone_somebody_didnt_recieve']\
                .format(ignored_clients_str=ignored_clients_str)
            await message.answer(answer_message)
        else:
            await message.answer(loc.admn.msgs['message_everyone_was_sent'] + '\n\n' + loc.admn.msgs['message_everyone_everybody_received'])

        await fsm_reset(message, state)
        return

    await message.answer(loc.admn.msgs['how_message_looks'])

    # echo message showing how will be displayed admin's message for clients
    await bot.copy_message(message.from_user.id, message.chat.id, message.message_id)

    # save last message to send it if admin write /perfect
    await state.update_data(message_chat_id=message.chat.id, message_id=message.message_id)


@admin_mw.admin_only()
async def notifications_send_message_selected_fsm_start(message: Message, state: FSMContext):
    """Start FSM for sending message to selected clients."""
    await state.set_state(admin_fsm.SendMessage.selected_list)
    await message.answer(loc.admn.msgs['fsm_start'])
    await message.answer(loc.admn.msgs['message_selected_info'])


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
        selected_clients_str += loc.admn.msgs['clients_row_str'].format(idx + 1, html.escape(name), html.escape(str(surname)), html.escape(str(username)), telegram_id)

    if selected_clients_str:
        await message.answer(loc.admn.msgs['message_selected_somebody_received'].format(selected_clients_str=selected_clients_str))
        await message.answer(loc.admn.msgs['message_selected_enter_message_info'])
    else:
        await message.answer(loc.admn.msgs['message_selected_nobody_received'])


@admin_mw.admin_only()
async def notifications_send_message_selected(message: Message, state: FSMContext):
    """Catch message, echo message and send it to selected clients, if admin wrote /perfect."""
    if message.text and message.text == '/perfect':
        ignored_clients_str = ''
        data = await state.get_data()

        for idx, telegram_id in enumerate(data['selected_telegram_ids']):
            try:
                await bot.copy_message(telegram_id, data['message_chat_id'], data['message_id'])

            except TelegramForbiddenError as bb:
                _, name, surname, username, *_ = await postgres_dbms.get_client_info_by_telegramID(telegram_id)
                logger.info(f"Can't send message to client {name} {telegram_id}: {bb}")
                ignored_clients_str += loc.admn.msgs['clients_row_str'].format(idx + 1, html.escape(name), html.escape(str(surname)), html.escape(str(username)), telegram_id) + '(has blocked bot)\n'

            except TelegramBadRequest:
                _, name, surname, username, *_ = await postgres_dbms.get_client_info_by_telegramID(telegram_id)
                ignored_clients_str += loc.admn.msgs['clients_row_str'].format(idx + 1, html.escape(name), html.escape(str(surname)), html.escape(str(username)), telegram_id)

        if ignored_clients_str:
            answer_message = loc.admn.msgs['message_everyone_was_sent'] + '\n\n' + loc.admn.msgs['message_everyone_somebody_didnt_recieve']\
                .format(ignored_clients_str=ignored_clients_str)
            await message.answer(answer_message)
        else:
            await message.answer(loc.admn.msgs['message_everyone_was_sent'] + '\n\n' + loc.admn.msgs['message_everyone_everybody_received'])

        await fsm_reset(message, state)
        return

    await message.answer('Вот так будет выглядеть Ваше сообщение:')

    await bot.copy_message(message.from_user.id, message.chat.id, message.message_id)

    await state.update_data(message_chat_id=message.chat.id, message_id=message.message_id)


@admin_mw.admin_only()
async def show_user_info_sql_fsm_start(message: Message, state: FSMContext):
    """Start FSM for showing SQL query for INSERT of forward message's owner."""
    await state.set_state(admin_fsm.UserInfo.ready)
    await message.answer(loc.admn.msgs['fsm_start'])
    await message.answer(loc.admn.msgs['sql_insert_client_info'])


@admin_mw.admin_only()
async def show_user_info_sql(message: Message):
    """Send message with SQL auery for INSERT of forward message's owner."""
    if message.forward_from is None:
        await message.reply(loc.admn.msgs['cant_read_user'])
    else:
        first_name = message.forward_from.first_name
        last_name = message.forward_from.last_name
        username = message.forward_from.username
        telegram_id = message.forward_from.id

        if last_name is None and username is None:
            await message.reply(f"<code>INSERT INTO clients (name, telegram_id, register_date) VALUES('{first_name}', "
                                f"{telegram_id}, TIMESTAMP '2023-01-01 00:00');</code>")
        elif username is None:
            await message.reply(f"<code>INSERT INTO clients (name, surname, telegram_id, register_date) VALUES('{first_name}', "
                                f"'{last_name}', {telegram_id}, TIMESTAMP '2023-01-01 00:00');</code>")
        elif last_name is None:
            await message.reply(f"<code>INSERT INTO clients (name, username, telegram_id, register_date) VALUES('{first_name}', "
                                f"'@{username}', {telegram_id}, TIMESTAMP '2023-01-01 00:00');</code>")
        else:
            await message.reply(f"<code>INSERT INTO clients (name, surname, username, telegram_id, register_date) VALUES('{first_name}', "
                                f"'{last_name}', '@{username}', {telegram_id}, TIMESTAMP '2023-01-01 00:00');</code>")


@admin_mw.admin_only()
async def show_user_config_sql_cm_start(message: Message, state: FSMContext):
    """Start FSM for showing SQL query for INSERT of configuration provided by admin."""
    await state.set_state(admin_fsm.ConfigInfo.ready)
    await message.answer(loc.admn.msgs['fsm_start'])
    await message.answer(loc.admn.msgs['sql_insert_config_info'])
    await message.answer(loc.admn.msgs['sql_insert_config_check_config_info'])


@admin_mw.admin_only()
async def show_user_config_sql(message: Message):
    """Send message with SQL qauery for INSERT of configuration provided by admin."""
    if message.document:
        arguments = message.caption.split(' ')
    else:
        arguments = message.text.split(' ')

    if len(arguments) < 6:
        await message.answer(loc.admn.msgs['error_not_enough_flags'])
        return

    elif len(arguments) == 6:
        flag_username_or_telegram_id, flag_protocol, flag_location, os, date_of_receipt_date, date_of_receipt_time = arguments

        if message.document:
            file_type = 'document'
            link = message.document.file_id
        else:
            await message.answer(loc.admn.msgs['error_bad_attachment'])
            return

    elif len(arguments) == 7:
        flag_username_or_telegram_id, flag_protocol, flag_location, os, date_of_receipt_date, date_of_receipt_time, link = arguments
        file_type = 'link'

    else:
        await message.answer(loc.admn.msgs['error_too_many_flags'])
        return

    if flag_username_or_telegram_id[0] == '@':
        client_id = await postgres_dbms.get_clientID_by_username(flag_username_or_telegram_id)
    else:
        client_id = await postgres_dbms.get_clientID_by_telegramID(int(flag_username_or_telegram_id))

    protocol_id = await postgres_dbms.get_protocol_id_by_alias(flag_protocol)
    if protocol_id is None:
        await message.answer(loc.admn.msgs['error_bad_protocol'])
        return

    server_id = await postgres_dbms.get_server_id_by_alias(flag_location)
    if server_id is None:
        await message.answer(loc.admn.msgs['error_bad_location'])
        return

    answer_text = '<code>INSERT INTO configurations(client_id, protocol_id, server_id, os, file_type, link, date_of_receipt) '
    answer_text += f"VALUES({client_id}, {protocol_id}, '{server_id}', '{os}', '{file_type}', '{link}', TIMESTAMP '{date_of_receipt_date} {date_of_receipt_time}');</code>"
    await message.answer(answer_text)


@admin_mw.admin_only()
async def sql_query_fsm_start(message: Message, state: FSMContext):
    """Start FSM for executing SQL query."""
    await state.set_state(admin_fsm.SQLQuery.password)
    await message.answer(loc.admn.msgs['fsm_start'])
    await message.answer(loc.admn.msgs['sql_query_enter_password'], reply_markup=admin_kb.sql_query)


@admin_mw.admin_only()
async def sql_query_password_verification(message: Message, state: FSMContext):
    """Verify database password entered correctly."""
    if message.text == POSTGRES_PASSWORD:
        await state.set_state(admin_fsm.SQLQuery.query)

        # delete message with password
        try:
            await bot.delete_message(message.from_user.id, message.message_id)
        except TelegramBadRequest:
            pass

        await message.answer(loc.admn.msgs['sql_query_correct_password'])

        tables_names_str = ''
        for idx, [table_name] in enumerate(await postgres_dbms.get_tables_names()):
            tables_names_str += loc.admn.msgs['sql_query_tables_row'].format(idx + 1, table_name)
        await message.answer(loc.admn.msgs['sql_query_tables_list'].format(POSTGRES_DB, tables_names_str=tables_names_str))

    else:
        await message.answer(loc.admn.msgs['sql_query_wrong_password'])


@admin_mw.admin_only()
async def sql_query_execution(message: Message, state: FSMContext):
    """Execute written SQL query and receive feedback."""
    logger.info(f'SQL query "{message.text}" was executed by admin with telegram_id {message.from_user.id}')
    try:
        records_list = await postgres_dbms.execute_query(message.text)

        max_chunk_size = 2048
        answer_message = ''
        for record in records_list:
            table_row_list_str: list[str] = [f'{column}=<code>{value}</code>' for column, value in zip(list(record.keys()), list(record.values()))]
            answer_message += f"{', '.join(table_row_list_str)}\n"
            if len(answer_message) >= max_chunk_size:
                await message.answer(answer_message)
                answer_message = ''
        await message.answer(answer_message)

    except Exception as e:
        await message.answer(loc.admn.msgs['sql_query_error'].format(e))


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
        name, surname, username, telegram_id, _, register_date_parsed, used_ref_promo_id = await postgres_dbms.get_client_info_by_clientID(client_id)
        *_, sub_price = await postgres_dbms.get_subscription_info_by_clientID(client_id)
        sub_expiration_date_parsed = await postgres_dbms.get_subscription_expiration_date(telegram_id)
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


@admin_mw.admin_only()
async def show_earnings(message: Message):
    """Send message with information about earned money per current month."""
    earnings_per_current_month: Decimal = await postgres_dbms.get_earnings_per_month()
    await message.answer(loc.admn.msgs['show_earnings'].format(float(earnings_per_current_month)))


@admin_mw.admin_only()
async def show_logs(message: Message):
    """Send message with last N rows of bot logs.

    Can be use both /logs and /logs <last_rows_number> ways."""
    last_rows_number_list = message.text.split(' ')[1:]
    if last_rows_number_list:
        last_rows_number = int(last_rows_number_list[0])
    else:
        last_rows_number = 50

    last_rows_counter = 0
    async with aiofiles.open('bot.log', mode='rb') as f:
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


@admin_mw.admin_only()
async def get_file_id(message: Message):
    """Send message with added file id."""
    if message.photo:
        await message.answer(loc.admn.msgs['file_id_photo'].format(message.photo[0].file_id))
    elif message.document:
        await message.answer(loc.admn.msgs['file_id_document'].format(message.document.file_id))
    else:
        await message.answer(loc.admn.msgs['error_no_file_for_file_id'])


@admin_mw.admin_only()
async def send_configuration_fsm_start(call: CallbackQuery, state: FSMContext):
    """Start FSM for sending configurations for a client after pressing inline button and send instruction."""
    await state.set_state(admin_fsm.SendConfig.ready)
    telegram_id_str, _, os_alias = call.data.partition(':')
    await state.update_data(telegram_id=telegram_id_str, os_alias=os_alias)

    await call.message.answer(loc.admn.msgs['fsm_start'])
    await call.message.answer(loc.admn.msgs['send_configuration_info'])
    await call.answer()


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

        await bot.send_message(telegram_id, loc.auth.msgs['config_was_received'])
        await internal_functions.send_configuration(telegram_id, file_type, date_of_receipt, os, name, country, city, bandwidth, ping, available_services, link, config_id, server_name)
        await bot.send_message(telegram_id, loc.auth.msgs['configs_rules'])
        await message.reply(loc.admn.msgs['config_was_sent'].format(file_type))
        await state.clear()

    except ValueError as ve:
        await message.reply(loc.admn.msgs['error_bad_flags_number'].format(ve))
    except Exception as e:
        await message.reply(loc.admn.msgs['error_unrecognized'].format(e))


def register_handlers_admin(dp):
    """Attach the `admin` router to the dispatcher."""
    dp.include_router(router)


# --- handler registrations ---
_R = router

_R.message.register(
    fsm_reset,
    F.text.in_({loc.admn.btns[key] for key in ('reset_fsm_1', 'reset_fsm_2')}),
    StateFilter('*'),
)
_R.message.register(fsm_reset, Command(commands=['reset']), StateFilter('*'))
_R.message.register(show_admin_keyboard, Command(commands=['admin']), StateFilter('*'))
_R.message.register(notifications_menu, F.text == loc.admn.btns['send_message'])
_R.message.register(notifications_send_message_everyone_fsm_start, F.text == loc.admn.btns['send_message_everyone'])
_R.message.register(notifications_send_message_everyone, StateFilter(admin_fsm.SendMessage.everyone_decision))
_R.message.register(notifications_send_message_selected_fsm_start, F.text == loc.admn.btns['send_message_selected'])
_R.message.register(notifications_send_message_selected_list, StateFilter(admin_fsm.SendMessage.selected_list))
_R.message.register(notifications_send_message_selected, StateFilter(admin_fsm.SendMessage.selected_decision))
_R.message.register(show_user_info_sql_fsm_start, F.text == loc.admn.btns['sql_insert_client'])
_R.message.register(show_user_info_sql_fsm_start, Command(commands=['sql_user']))
_R.message.register(show_user_info_sql, StateFilter(admin_fsm.UserInfo.ready))
_R.message.register(show_user_config_sql_cm_start, F.text == loc.admn.btns['sql_insert_config'])
_R.message.register(show_user_config_sql_cm_start, Command(commands=['sql_config']))
_R.message.register(check_user_configs, Command(commands=['configs']))
_R.message.register(
    show_user_config_sql,
    StateFilter(admin_fsm.ConfigInfo.ready),
    F.content_type.in_({'text', 'document'}),
)
_R.message.register(sql_query_fsm_start, F.text == loc.admn.btns['sql_query'])
_R.message.register(sql_query_password_verification, StateFilter(admin_fsm.SQLQuery.password))
_R.message.register(sql_query_execution, StateFilter(admin_fsm.SQLQuery.query))
_R.message.register(show_clients_info, F.text == loc.admn.btns['clients_info'])
_R.message.register(show_clients_info, Command(commands=['clients']))
_R.message.register(show_earnings, F.text == loc.admn.btns['show_earnings'])
_R.message.register(show_logs, F.text == loc.admn.btns['show_logs'])
_R.message.register(show_logs, Command(commands=['logs']))
_R.message.register(
    get_file_id,
    F.text == loc.admn.btns['get_file_id'],
)
_R.message.register(
    get_file_id,
    Command(commands=['fileid', 'fid']),
)
_R.callback_query.register(
    send_configuration_fsm_start,
    F.data.func(lambda d: d is not None and ':' in d and d.split(':', 1)[0].isdigit()),
)
_R.message.register(
    send_configuration,
    StateFilter(admin_fsm.SendConfig.ready),
    F.content_type.in_({'text', 'document'}),
)
