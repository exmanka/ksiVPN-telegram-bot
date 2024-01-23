import logging
import aiofiles
from decimal import Decimal
from aiogram import Dispatcher
from aiogram.types import Message, CallbackQuery
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Text
from aiogram.utils.exceptions import ChatNotFound
from src.middlewares import admin_mw
from src.keyboards import admin_kb
from src.states import admin_fsm
from src.database import postgres_dbms
from src.services import internal_functions, localization as loc
from bot_init import bot, POSTGRES_DB, POSTGRES_PASSWORD


logger = logging.getLogger(__name__)


@admin_mw.admin_only()
async def fsm_reset(message: Message, state: FSMContext):
    """Cancel admin's FSM state and return to menu keyboard regardless of machine state."""
    await state.finish()
    await message.answer(loc.admn.msgs['reset_fsm_keyboard'], parse_mode='HTML', reply_markup=admin_kb.menu)


@admin_mw.admin_only()
async def show_admin_keyboard(message: Message):
    """Send message with information about admin's commands and show admin keyboard."""
    await message.reply(loc.admn.msgs['admin_kb_info'], reply_markup=admin_kb.menu)


@admin_mw.admin_only()
async def notifications_menu(message: Message):
    """Show keyboard for sending messages via bot."""
    await message.answer(loc.admn.msgs['go_send_message_menu'], parse_mode='HTML', reply_markup=admin_kb.notification)


@admin_mw.admin_only()
async def notifications_send_message_everyone_fsm_start(message: Message, state: FSMContext):
    """Start FSM for sending message to every client who wrote bot at least one time."""
    await state.set_state(admin_fsm.SendMessage.everyone_decision)
    await message.answer(loc.admn.msgs['fsm_start'], parse_mode='HTML')
    await message.answer(loc.admn.msgs['message_everyone_info'])


@admin_mw.admin_only()
async def notifications_send_message_everyone(message: Message, state: FSMContext):
    """Catch message, echo message and send it to every client who wrote bot at least one time, if admin wrote /perfect."""
    # if message looks good for admin
    if message.text and message.text == '/perfect':
        ignored_clients_str = ''
        async with state.proxy() as data:

            # for every client
            for idx, [telegram_id] in enumerate(await postgres_dbms.get_clients_telegram_ids()):

                # if client didn't write to bot
                try:
                    await internal_functions.send_message_by_telegram_id(telegram_id, data['message'])

                # add him to message list of clients who didn't receive message
                except ChatNotFound as _t:
                    _, name, surname, username, *_ = await postgres_dbms.get_client_info_by_telegramID(telegram_id)
                    ignored_clients_str += loc.admn.msgs['clients_row_str'].format(idx + 1, name, surname, username, telegram_id)

        # if some clients didn't receive message because they didn't write to bot at all
        if ignored_clients_str:
            answer_message = loc.admn.msgs['message_everyone_was_sent'] + '\n\n' + loc.admn.msgs['message_everyone_somebody_didnt_recieve']\
                .format(ignored_clients_str=ignored_clients_str)
            await message.answer(answer_message, parse_mode='HTML')

        # if all clients receive message
        else:
            await message.answer(loc.admn.msgs['message_everyone_was_sent'] + '\n\n' + loc.admn.msgs['message_everyone_everybody_received'], parse_mode='HTML')

        await fsm_reset(message, state)
        return

    await message.answer(loc.admn.msgs['how_message_looks'])

    # echo message showing how will be displayed admin's message for clients
    await internal_functions.send_message_by_telegram_id(message.from_user.id, message)

    # save last message to send it if admin write /perfect
    async with state.proxy() as data:
        data['message'] = message


@admin_mw.admin_only()
async def notifications_send_message_selected_fsm_start(message: Message, state: FSMContext):
    """Start FSM for sending message to selected clients."""
    await state.set_state(admin_fsm.SendMessage.selected_list)
    await message.answer(loc.admn.msgs['fsm_start'], parse_mode='HTML')
    await message.answer(loc.admn.msgs['message_selected_info'], parse_mode='HTML')


@admin_mw.admin_only()
async def notifications_send_message_selected_list(message: Message, state: FSMContext):
    """Parse entered by admin list of selected clients for sending them some message."""
    # parse clients mentioned in message
    selected_clients = message.text.split(' ')
    selected_clients_telegram_ids = []
    for client in selected_clients:

        # if client mentioned by username
        if client[0] == '@':

            # if client exists in db
            if telegram_id := await postgres_dbms.get_telegramID_by_username(client):
                selected_clients_telegram_ids.append(telegram_id)

        # if client mentioned by telegram_id and exists in db
        elif await postgres_dbms.get_clientID_by_telegramID(int(client)):
            selected_clients_telegram_ids.append(int(client))

    # save selected clients ids
    async with state.proxy() as data:
        data['selected_telegram_ids'] = selected_clients_telegram_ids
    await state.set_state(admin_fsm.SendMessage.selected_decision)

    # show selected clients info
    selected_clients_str = ''
    for idx, telegram_id in enumerate(selected_clients_telegram_ids):
        _, name, surname, username, *_ = await postgres_dbms.get_client_info_by_telegramID(telegram_id)
        selected_clients_str += loc.admn.msgs['clients_row_str'].format(idx + 1, name, surname, username, telegram_id)

    # if at least 1 selected client exists in db
    if selected_clients_str:
        await message.answer(loc.admn.msgs['message_selected_somebody_received'].format(selected_clients_str=selected_clients_str), parse_mode='HTML')
        await message.answer(loc.admn.msgs['message_selected_enter_message_info'])

    # if mentioned clients don't exist in db
    else:
        await message.answer(loc.admn.msgs['message_selected_nobody_received'], parse_mode='HTML')


@admin_mw.admin_only()
async def notifications_send_message_selected(message: Message, state: FSMContext):
    """Catch message, echo message and send it to selected clients, if admin wrote /perfect."""
    # if message looks good for admin
    if message.text and message.text == '/perfect':
        ignored_clients_str = ''
        async with state.proxy() as data:

            # for every existing in db selected client
            for idx, telegram_id in enumerate(data['selected_telegram_ids']):

                # if client didn't write to bot
                try:
                    await internal_functions.send_message_by_telegram_id(telegram_id, data['message'])

                # add him to message list of clients who didn't receive message
                except ChatNotFound as _t:
                    _, name, surname, username, *_ = await postgres_dbms.get_client_info_by_telegramID(telegram_id)
                    ignored_clients_str += loc.admn.msgs['clients_row_str'].format(idx + 1, name, surname, username, telegram_id)

        # if some clients didn't receive message because they didn't write to bot at all
        if ignored_clients_str:
            answer_message = loc.admn.msgs['message_everyone_was_sent'] + '\n\n' + loc.admn.msgs['message_everyone_somebody_didnt_recieve']\
                .format(ignored_clients_str=ignored_clients_str)
            await message.answer(answer_message, parse_mode='HTML')

        # if all clients receive message
        else:
            await message.answer(loc.admn.msgs['message_everyone_was_sent'] + '\n\n' + loc.admn.msgs['message_everyone_everybody_received'], parse_mode='HTML')
    
        await fsm_reset(message, state)
        return

    await message.answer('Вот так будет выглядеть Ваше сообщение:')

    # echo message showing how will be displayed admin's message for clients
    await internal_functions.send_message_by_telegram_id(message.from_user.id, message)

    # save last message to send it if admin write /perfect
    async with state.proxy() as data:
        data['message'] = message


@admin_mw.admin_only()
async def show_user_info_sql_fsm_start(message: Message):
    """Start FSM for showing SQL query for INSERT of forward message's owner."""
    await admin_fsm.UserInfo.ready.set()
    await message.answer(loc.admn.msgs['fsm_start'], parse_mode='HTML')
    await message.answer(loc.admn.msgs['sql_insert_client_info'])


@admin_mw.admin_only()
async def show_user_info_sql(message: Message):
    """Send message with SQL auery for INSERT of forward message's owner."""
    # if user blocked ability to get information about his profile
    if message.forward_from is None:
        await message.reply(loc.admn.msgs['cant_read_user'])
    else:
        first_name = message.forward_from.first_name
        last_name = message.forward_from.last_name
        username = message.forward_from.username
        telegram_id = message.forward_from.id

        # create beautiful answer
        if last_name is None and username is None:
            await message.reply(f"<code>INSERT INTO clients (name, telegram_id, register_date) VALUES('{first_name}', "
                                f"{telegram_id}, TIMESTAMP '2023-01-01 00:00');</code>", parse_mode='HTML')
        elif username is None:
            await message.reply(f"<code>INSERT INTO clients (name, surname, telegram_id, register_date) VALUES('{first_name}', "
                                f"'{last_name}', {telegram_id}, TIMESTAMP '2023-01-01 00:00');</code>", parse_mode='HTML')
        elif last_name is None:
            await message.reply(f"<code>INSERT INTO clients (name, username, telegram_id, register_date) VALUES('{first_name}', "
                                f"'@{username}', {telegram_id}, TIMESTAMP '2023-01-01 00:00');</code>", parse_mode='HTML')
        else:
            await message.reply(f"<code>INSERT INTO clients (name, surname, username, telegram_id, register_date) VALUES('{first_name}', "
                                f"'{last_name}', '@{username}', {telegram_id}, TIMESTAMP '2023-01-01 00:00');</code>",
                                parse_mode='HTML')


@admin_mw.admin_only()
async def show_user_config_sql_cm_start(message: Message):
    """Start FSM for showing SQL query for INSERT of configuration provided by admin."""
    await admin_fsm.ConfigInfo.ready.set()
    await message.answer(loc.admn.msgs['fsm_start'], parse_mode='HTML')
    await message.answer(loc.admn.msgs['sql_insert_config_info'], parse_mode='HTML')
    await message.answer(loc.admn.msgs['sql_insert_config_check_config_info'], parse_mode='HTML')


@admin_mw.admin_only()
async def show_user_config_sql(message: Message):
    """Send message with SQL auery for INSERT of configuration provided by admin."""
    # parse arguments
    if message.photo or message.document:
        arguments = message.caption.split(' ')
    else:
        arguments = message.text.split(' ')

    # if number of arguments are less then expected
    if len(arguments) < 6:
        await message.answer(loc.admn.msgs['error_not_enough_flags'])
        return

    # if admin didn't add link as 7th argument (link)
    elif len(arguments) == 6:
        flag_username_or_telegram_id, flag_protocol, flag_location, os, date_of_receipt_date, date_of_receipt_time = arguments

        # if photo was sended
        if message.photo:
            file_type = 'photo'
            link = message.photo[0].file_id

        # if document was sended
        elif message.document:
            file_type = 'document'
            link = message.document.file_id

        # any other case
        else:
            await message.answer(loc.admn.msgs['error_bad_attachment'])

    # if admin added link as 7th argument (link)
    elif len(arguments) == 7:
        flag_username_or_telegram_id, flag_protocol, flag_location, os, date_of_receipt_date, date_of_receipt_time, link = arguments

        # creating link for XTLS-Reality
        file_type = 'link'

    # if number of arguments are more then expected
    else:
        await message.answer(loc.admn.msgs['error_too_many_flags'])
        return

    # if 1st argument is username
    if flag_username_or_telegram_id[0] == '@':
        client_id = await postgres_dbms.get_clientID_by_username(flag_username_or_telegram_id)

    # if 1st argument is telegram_id
    else:
        client_id = await postgres_dbms.get_clientID_by_telegramID(int(flag_username_or_telegram_id))

    # check 2nd argument as protocol_id
    match flag_protocol:
        case 'w':
            protocol_id = 1
        case 'x':
            protocol_id = 2
        case 's':
            protocol_id = 3
        case _:
            await message.answer(loc.admn.msgs['error_bad_protocol'])
            return

    # check 3rd argument as location_id
    match flag_location:
        case 'n':
            location_id = 1
        case 'l':
            location_id = 2
        case 'g':
            location_id = 3
        case 'u':
            location_id = 4
        case _:
            await message.answer(loc.admn.msgs['error_bad_location'])
            return

    answer_text = '<code>INSERT INTO configurations(client_id, protocol_id, location_id, os, file_type, telegram_file_id, date_of_receipt) '
    answer_text += f"VALUES({client_id}, {protocol_id}, {location_id}, '{os}', '{file_type}', '{link}', TIMESTAMP '{date_of_receipt_date} {date_of_receipt_time}');</code>"
    await message.answer(answer_text, parse_mode='HTML')


@admin_mw.admin_only()
async def sql_query_fsm_start(message: Message):
    """Start FSM for executing SQL query."""
    await admin_fsm.SQLQuery.password.set()
    await message.answer(loc.admn.msgs['fsm_start'], parse_mode='HTML')
    await message.answer(loc.admn.msgs['sql_query_enter_password'], parse_mode='HTML', reply_markup=admin_kb.sql_query)


@admin_mw.admin_only()
async def sql_query_password_verification(message: Message, state: FSMContext):
    """Verify database password entered correctly."""
    if message.text == POSTGRES_PASSWORD:
        await state.set_state(admin_fsm.SQLQuery.query)

        # delete message with password
        await bot.delete_message(message.from_user.id, message.message_id)
        
        await message.answer(loc.admn.msgs['sql_query_correct_password'], 'HTML')

        # send message with all database tables names to admin
        tables_names_str = ''
        for idx, [table_name] in enumerate(await postgres_dbms.get_tables_names()):
            tables_names_str += loc.admn.msgs['sql_query_tables_row'].format(idx + 1, table_name)
        await message.answer(loc.admn.msgs['sql_query_tables_list'].format(POSTGRES_DB, tables_names_str=tables_names_str), parse_mode='HTML')

    else:
        await message.answer(loc.admn.msgs['sql_query_wrong_password'], 'HTML')


@admin_mw.admin_only()
async def sql_query_execution(message: Message, state: FSMContext):
    """Execute written SQL query and receive feedback."""
    logger.info(f'SQL query "{message.text}" was executed by admin with telegram_id {message.from_user.id}')
    try:
        # get data from DBMS
        records_list = await postgres_dbms.execute_query(message.text)

        # send data by chunks in case data size is too long for one telegram message
        max_chunk_size = 2048
        answer_message = ''
        for record in records_list:
            table_row_list_str: list[str] = [f'{column}=<code>{value}</code>' for column, value in zip(list(record.keys()), list(record.values()))]
            answer_message += f"{', '.join(table_row_list_str)}\n"
            if len(answer_message) >= max_chunk_size:
                await message.answer(answer_message, parse_mode='HTML')
                answer_message = ''
        await message.answer(answer_message, parse_mode='HTML')
            
        # left_border = 0
        # chunk_size = 4000
        # while (len(data) - left_border) // chunk_size != 0:
        #     await message.answer(data[left_border:left_border + chunk_size])
        #     left_border += chunk_size
        # await message.answer(data[left_border:])
    
    except Exception as e:
        await message.answer(loc.admn.msgs['sql_query_error'].format(e))


@admin_mw.admin_only()
async def show_clients_info(message: Message):
    """Send message with information about all clients."""
    await message.answer(loc.admn.msgs['clients_info'])

    answer_message = ''
    for [client_id] in await postgres_dbms.get_clients_ids():
        name, surname, username, telegram_id, _, register_date_parsed, used_ref_promo_id = await postgres_dbms.get_client_info_by_clientID(client_id)
        *_, sub_price = await postgres_dbms.get_subscription_info_by_clientID(client_id)
        sub_expiration_date_parsed = await postgres_dbms.get_subscription_expiration_date(telegram_id)
        config_num = await postgres_dbms.get_configurations_number(client_id)
        paid_sum: Decimal = await postgres_dbms.get_payments_successful_sum(client_id)
        _, ref_promo_phrase, *_ = await postgres_dbms.get_refferal_promo_info_by_clientCreatorID(client_id)

        answer_message_row = ''
        if await postgres_dbms.is_subscription_active(telegram_id) or await postgres_dbms.is_subscription_free(telegram_id):
            answer_message_row += loc.admn.msgs['clients_info_sub_active']
        else:
            answer_message_row += loc.admn.msgs['clients_info_sub_inactive']

        # hope that telegram add ability to send markdown's spreadsheets in message to api, but for now
        answer_message_row +=\
            f"| <b>{client_id}</b> "\
            f"| {await internal_functions.format_none_string(username)} <code>{name}{await internal_functions.format_none_string(surname)}</code> <code>{telegram_id}</code>, {register_date_parsed[:-8]} "\
            f"| {sub_price}₽/мес, <b>{sub_expiration_date_parsed}</b> "\
            f"| configs: {config_num} "\
            f"| paid: {float(paid_sum):g}₽ "\
            f"| <code>{ref_promo_phrase}</code> "
            
        # if client was invited by another client
        who_invited_str = ''
        if used_ref_promo_id is not None:
            _, who_invited_client_id, *_ = await postgres_dbms.get_refferal_promo_info_by_promoID(used_ref_promo_id)
            who_invited_name, who_invited_surname, who_invited_username, who_invited_telegram_id, *_ = await postgres_dbms.get_client_info_by_clientID(who_invited_client_id)
            who_invited_str +=\
                f"| {await internal_functions.format_none_string(who_invited_username)} <code>{who_invited_name}{await internal_functions.format_none_string(who_invited_surname)}</code> <code>{who_invited_telegram_id}</code>"

        answer_message_row += who_invited_str
        answer_message += answer_message_row + '\n\n'

        # send message for every 10 client_id to avoid telegram message length restrictions
        if client_id % 10 == 0:
            await message.answer(answer_message, parse_mode='HTML')
            answer_message = ''
    
    # send remaining info
    if answer_message:
        await message.answer(answer_message, 'HTML')


@admin_mw.admin_only()
async def show_earnings(message: Message):
    """Send message with information about earned money per current month."""
    earnings_per_current_month: Decimal = await postgres_dbms.get_earnings_per_month()
    await message.answer(loc.admn.msgs['show_earnings'].format(float(earnings_per_current_month)), parse_mode='HTML')


@admin_mw.admin_only()
async def show_logs(message: Message):
    """Send message with last N rows of bot logs.
    
    Can be use both /logs and /logs <last_rows_number> ways."""
    # get last rows number by argument or set default if argument is not specified
    last_rows_number_list = message.text.split(' ')[1:]
    if last_rows_number_list:
        last_rows_number = int(last_rows_number_list[0])
    else:
        last_rows_number = 10

    # read only last rows of file
    last_rows_counter = 0
    async with aiofiles.open('bot.log', mode='rb') as f:

        # move pointer to the end of byte-encoded file and iterate up
        try:
            await f.seek(-2, 2)
            while last_rows_counter < last_rows_number:
                await f.seek(-2, 1)
                if await f.read(1) == b'\n':
                    last_rows_counter += 1

        # if file contains less then last_rows_number rows
        except OSError:
            await f.seek(0)
        
        last_lines = (await f.read()).decode()
    await message.answer(f'<pre>{last_lines}</pre>', parse_mode='HTML')


@admin_mw.admin_only()
async def check_user_configs(message: Message):
    """Send messages with configurations of another client.

    Used for test.
    """
    # taking user info (telegramID or username) from text after command
    user_info = message.text.split(' ')[1]

    # if user_info is username
    if user_info[0] == '@':
        client_id = await postgres_dbms.get_clientID_by_username(user_info)

    # if user_info is user telegramID
    else:
        client_id = await postgres_dbms.get_clientID_by_telegramID(user_info)

    # get information about specified client's configurations
    configurations_info = await postgres_dbms.get_configurations_info(client_id)
    await message.answer(loc.auth.msgs['configs_info'].format(len(configurations_info)), parse_mode='HTML')

    # send message for every configuration
    for file_type, date_of_receipt, os, is_chatgpt_available, name, country, city, bandwidth, ping, telegram_file_id in configurations_info:
        await internal_functions.send_configuration(message.from_user.id, file_type, date_of_receipt, os, is_chatgpt_available, name, country, city, bandwidth, ping, telegram_file_id)

    await message.answer(loc.auth.msgs['configs_rules'], parse_mode='HTML')


@admin_mw.admin_only()
async def get_file_id(message: Message):
    """Send message with added file id."""
    # if message contains photo
    if message.photo:
        await message.answer(loc.admn.msgs['file_id_photo'].format(message.photo[0].file_id), parse_mode='HTML')

    # if message contains document
    elif message.document:
        await message.answer(loc.admn.msgs['file_id_document'].format(message.document.file_id), parse_mode='HTML')

    # any other case
    else:
        await message.answer(loc.admn.msgs['error_no_file_for_file_id'])


@admin_mw.admin_only()
async def send_configuration_fsm_start(call: CallbackQuery, state: FSMContext):
    """Start FSM for sending configurations for a client after pressing inline button and send instruction."""
    await admin_fsm.SendConfig.ready.set()
    async with state.proxy() as data:
        data['telegram_id'] = call.data

    await call.message.answer(loc.admn.msgs['fsm_start'], parse_mode='HTML')
    await call.message.answer(loc.admn.msgs['send_configuration_info'], parse_mode='HTML')
    await call.answer()


@admin_mw.admin_only()
async def send_configuration(message: Message, state: FSMContext):
    """Check configuration sended by admin and send it to client."""
    async with state.proxy() as data:
        telegram_id = int(data['telegram_id'])
    client_id = await postgres_dbms.get_clientID_by_telegramID(telegram_id)

    try:
        # if message is text
        if text := message.text:
            # create configuration
            file_type = 'link'
            flag_protocol, flag_location, flag_os, flag_link = text.split(' ')
            await internal_functions.create_configuration(client_id, file_type, flag_protocol, flag_location, flag_os, flag_link)
            _, date_of_receipt, os, is_chatgpt_available, name, country, city, bandwidth, ping, telegram_file_id = (await postgres_dbms.get_configurations_info(client_id))[-1]

        # if message is document
        elif document := message.document:
            # create configuration
            file_type = 'document'
            flag_protocol, flag_location, flag_os = message.caption.split(' ')
            telegram_file_id = document.file_id
            await internal_functions.create_configuration(client_id, file_type, flag_protocol, flag_location, flag_os, telegram_file_id=telegram_file_id)
            file_type, date_of_receipt, os, is_chatgpt_available, name, country, city, bandwidth, ping, telegram_file_id = (await postgres_dbms.get_configurations_info(client_id))[-1]

        # if message is photo
        elif photo := message.photo:
            # create configuration
            file_type = 'photo'
            flag_protocol, flag_location, flag_os = message.caption.split(' ')
            telegram_file_id = photo[0].file_id
            await internal_functions.create_configuration(client_id, file_type, flag_protocol, flag_location, flag_os, telegram_file_id=telegram_file_id)
            file_type, date_of_receipt, os, is_chatgpt_available, name, country, city, bandwidth, ping, telegram_file_id = (await postgres_dbms.get_configurations_info(client_id))[-1]

        # other cases
        else:
            await message.reply(loc.admn.msgs['error_bad_attachment'])
            return
        
        # send message to client, admin and finish FSM for sending configurations
        await bot.send_message(telegram_id, loc.auth.msgs['config_was_received'], parse_mode='HTML')
        await internal_functions.send_configuration(telegram_id, file_type, date_of_receipt, os, is_chatgpt_available, name, country, city, bandwidth, ping, telegram_file_id)
        await bot.send_message(telegram_id, loc.auth.msgs['configs_rules'], parse_mode='HTML')
        await message.reply(loc.admn.msgs['config_was_sent'].format(file_type), parse_mode='HTML')
        await state.finish()

    # catch create_configuration() exceptions
    except ValueError as ve:
        await message.reply(loc.admn.msgs['error_bad_flags_number'].format(ve))
    except Exception as e:
        await message.reply(loc.admn.msgs['error_unrecognized'].format(e))


def register_handlers_admin(dp: Dispatcher):
    dp.register_message_handler(fsm_reset, Text([loc.admn.btns[key] for key in ('reset_fsm_1', 'reset_fsm_2')]), state='*')
    dp.register_message_handler(fsm_reset, commands=['reset'], state='*')
    dp.register_message_handler(show_admin_keyboard, commands=['admin'], state='*')
    dp.register_message_handler(notifications_menu, Text(loc.admn.btns['send_message']))
    dp.register_message_handler(notifications_send_message_everyone_fsm_start, Text(loc.admn.btns['send_message_everyone']))
    dp.register_message_handler(notifications_send_message_everyone, state=admin_fsm.SendMessage.everyone_decision, content_types='any')
    dp.register_message_handler(notifications_send_message_selected_fsm_start, Text(loc.admn.btns['send_message_selected']))
    dp.register_message_handler(notifications_send_message_selected_list, state=admin_fsm.SendMessage.selected_list)
    dp.register_message_handler(notifications_send_message_selected, state=admin_fsm.SendMessage.selected_decision, content_types='any')
    dp.register_message_handler(show_user_info_sql_fsm_start, Text(loc.admn.btns['sql_insert_client']))
    dp.register_message_handler(show_user_info_sql_fsm_start, commands=['sql_user'])
    dp.register_message_handler(show_user_info_sql, state=admin_fsm.UserInfo.ready)
    dp.register_message_handler(show_user_config_sql_cm_start, Text(loc.admn.btns['sql_insert_config']))
    dp.register_message_handler(show_user_config_sql_cm_start, commands=['sql_config'])
    dp.register_message_handler(check_user_configs, state=admin_fsm.ConfigInfo.ready, commands=['check_configs'])
    dp.register_message_handler(show_user_config_sql, state=admin_fsm.ConfigInfo.ready, content_types=['text', 'photo', 'document'])
    dp.register_message_handler(sql_query_fsm_start, Text(loc.admn.btns['sql_query']))
    dp.register_message_handler(sql_query_password_verification, state=admin_fsm.SQLQuery.password)
    dp.register_message_handler(sql_query_execution, state=admin_fsm.SQLQuery.query)
    dp.register_message_handler(show_clients_info, Text(loc.admn.btns['clients_info']))
    dp.register_message_handler(show_earnings, Text(loc.admn.btns['show_earnings']))
    dp.register_message_handler(show_logs, Text(loc.admn.btns['show_logs']))
    dp.register_message_handler(show_logs, commands=['logs'])
    dp.register_message_handler(get_file_id, Text(loc.admn.btns['get_file_id']), content_types=['text', 'photo', 'document'])
    dp.register_message_handler(get_file_id, commands=['fileid', 'fid'], commands_ignore_caption=False, content_types=['text', 'photo', 'document'])
    dp.register_callback_query_handler(send_configuration_fsm_start, lambda call: call.data.isdigit(), state='*')
    dp.register_message_handler(send_configuration, content_types=['text', 'photo', 'document'], state=admin_fsm.SendConfig.ready)
