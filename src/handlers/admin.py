from aiogram import Dispatcher
from aiogram.types import Message, CallbackQuery
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Text
from aiogram.utils.exceptions import ChatNotFound
from src.middlewares import admin_mw
from src.keyboards import admin_kb
from src.states import admin_fsm
from src.database import postgesql_db
from src.services import service_functions
from bot_init import bot


@admin_mw.admin_only()
async def fsm_reset(message: Message, state: FSMContext):
    """Cancel admin's FSM state and return to menu keyboard regardless of machine state."""
    await state.finish()
    await message.answer('Сброс машинного состояния и клавиатуры!', reply_markup=admin_kb.menu)


@admin_mw.admin_only()
async def show_admin_keyboard(message: Message):
    """Send message with information about admin's commands and show admin keyboard."""
    await message.reply('Для вызова данного меню используйте /admin.\b\bДоступные команды:\n\n/fileid (/fid)\n/sql_user\n/sql_config', reply_markup=admin_kb.menu)


@admin_mw.admin_only()
async def notifications_menu(message: Message):
    """Show keyboard for sending messages via bot."""
    await message.answer('Открываю клавиатуру отправки сообщений пользователям!', reply_markup=admin_kb.notification)


@admin_mw.admin_only()
async def notifications_send_message_everyone_fsm_start(message: Message, state: FSMContext):
    """Start FSM for sending message to every client who wrote bot at least one time."""
    await state.set_state(admin_fsm.SendMessage.everyone_decision)
    answer_message = 'Активировано машинное состояние! Введите необходимую информацию следующим сообщением, а также приложите файлы при необходимости!\n\n'
    answer_message += 'Введите /perfect, чтобы подтвердить выбор последнего отправленного сообщения!'
    await message.answer(answer_message, parse_mode='HTML')


@admin_mw.admin_only()
async def notifications_send_message_everyone(message: Message, state: FSMContext):
    """Catch message, echo message and send it to every client who wrote bot at least one time, if admin wrote /perfect."""
    # if message looks good for admin
    if message.text and message.text == '/perfect':
        answer_message = ''
        async with state.proxy() as data:

            # for every client
            for idx, [telegram_id] in enumerate(await postgesql_db.get_clients_telegram_ids()):

                # if client didn't write to bot
                try:
                    await service_functions.send_message_by_telegram_id(telegram_id, data['message'])

                # add him to message list of clients who didn't receive message
                except ChatNotFound as _t:
                    _, name, surname, username, *_ = await postgesql_db.get_client_info_by_telegramID(telegram_id)
                    answer_message += f'{idx + 1}. {name} {surname} {username} (tg_id: <code>{telegram_id}</code>)\n'

        # if some clients didn't receive message because they didn't write to bot at all
        if answer_message:
            answer_message = 'Ладненько, сообщение отправлено!\n\nПользователи, до которых сообщение не дошло:\n' + answer_message

        # if all clients receive message
        else:
            answer_message = 'Ладненько, сообщение отправлено!\n\nУра, сообщение получат все пользователи сервиса!'

        await message.answer(answer_message)
        return

    await message.answer('Вот так будет выглядеть Ваше сообщение:')

    # echo message showing how will be displayed admin's message for clients
    await service_functions.send_message_by_telegram_id(message.from_user.id, message)

    # save last message to send it if admin write /perfect
    async with state.proxy() as data:
        data['message'] = message


@admin_mw.admin_only()
async def notifications_send_message_selected_fsm_start(message: Message, state: FSMContext):
    """Start FSM for sending message to selected clients."""
    await state.set_state(admin_fsm.SendMessage.selected_list)
    answer_message = 'Активировано машинное состояние! Введите через запятую <b>username</b> или <b>telegram_id</b> пользователей, для которых предназначена рассылка.'
    await message.answer(answer_message, parse_mode='HTML')


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
            if telegram_id := await postgesql_db.get_telegramID_by_username(client):
                selected_clients_telegram_ids.append(telegram_id)

        # if client mentioned by telegram_id and exists in db
        elif await postgesql_db.get_clientID_by_telegramID(client):
            selected_clients_telegram_ids.append(client)

    # save selected clients ids
    async with state.proxy() as data:
        data['selected_telegram_ids'] = selected_clients_telegram_ids
    await state.set_state(admin_fsm.SendMessage.selected_decision)

    # show selected clients info
    answer_message = ''
    for idx, telegram_id in enumerate(selected_clients_telegram_ids):
        _, name, surname, username, *_ = await postgesql_db.get_client_info_by_telegramID(telegram_id)
        answer_message += f'{idx + 1}. {name} {surname} {username} (tg_id: <code>{telegram_id}</code>)\n'

    # if at least 1 selected client exists in db
    if answer_message:
        answer_message = 'Сообщение будет отправленно пользователям:\n\n' + answer_message

    # if mentioned clients don't exist in db
    else:
        answer_message = 'Вы ошиблись при вводе пользователей! Сообщение ни до кого не дойдет!'
    await message.answer(answer_message, parse_mode='HTML')

    answer_message = 'Теперь введите необходимую информацию следующим сообщением, а также приложите файлы при необходимости!\n\n'
    answer_message += 'Введите /perfect, чтобы подтвердить выбор последнего отправленного сообщения!'
    await message.answer(answer_message)


@admin_mw.admin_only()
async def notifications_send_message_selected(message: Message, state: FSMContext):
    """Catch message, echo message and send it to selected clients, if admin wrote /perfect."""
    # if message looks good for admin
    if message.text and message.text == '/perfect':

        answer_message = ''
        async with state.proxy() as data:

            # for every existing in db selected client
            for idx, telegram_id in enumerate(data['selected_telegram_ids']):

                # if client didn't write to bot
                try:
                    await service_functions.send_message_by_telegram_id(telegram_id, data['message'])

                # add him to message list of clients who didn't receive message
                except ChatNotFound as _t:
                    _, name, surname, username, *_ = await postgesql_db.get_client_info_by_telegramID(telegram_id)
                    answer_message += f'{idx + 1}. {username} ({name}, {surname}), telegram_id <b>{telegram_id}</b>\n'

        # if some clients didn't receive message because they didn't write to bot at all
        if answer_message:
            answer_message = 'Ладненько, сообщение отправлено!\n\nПользователи, до которых сообщение не дошло:\n' + answer_message

        # if all clients receive message
        else:
            answer_message = 'Ладненько, сообщение отправлено!\n\nУра, сообщение получат все указанные пользователи!'

        await message.answer(answer_message)
        await fsm_reset(message, state)
        return

    await message.answer('Вот так будет выглядеть Ваше сообщение:')

    # echo message showing how will be displayed admin's message for clients
    await service_functions.send_message_by_telegram_id(message.from_user.id, message)

    # save last message to send it if admin write /perfect
    async with state.proxy() as data:
        data['message'] = message


@admin_mw.admin_only()
async def show_user_info_sql_fsm_start(message: Message):
    """Start FSM for showing SQL query for INSERT of forward message's owner."""
    await admin_fsm.UserInfo.ready.set()
    message_answer = 'Активировано состояние для получения SQL-запроса на вставку пользователя! Перешлите мне сообщение, и я выведу всю возможную информацию!\n\n'
    message_answer += 'Кстати, проверить, какие конфигурации доступны пользователю можно командой /check_configs <telegram_id> | <username>'
    await message.reply(message_answer)


@admin_mw.admin_only()
async def show_user_info_sql(message: Message):
    """Send message with SQL auery for INSERT of forward message's owner."""
    # if user blocked ability to get information about his profile
    if message.forward_from is None:
        await message.reply('К сожалению, не могу прочитать информацию о пользователе :(')
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
    guide_text = 'Активировано состояние для получения SQL-запроса на вставку конфигурации! Пришлите мне сообщение в формате (вместо переноса строк используются пробелы):\n\n'
    guide_text += '<b>client_id</b> - client_username | client_telegram_id\n'
    guide_text += '<b>protocol_id</b> - <code>w</code> (WireGuard) | <code>x</code> (XTLS-Reality) | <code>s</code> (ShadowSocks)\n'
    guide_text += '<b>location_id</b> - <code>n</code> (Netherlands) | <code>l</code> (Latvia) | <code>g</code> (Germany) | <code>u</code> (USA)\n'
    guide_text += '<b>os</b> - <code>Android</code> | <code>IOS</code> | <code>Windows</code> | <code>Linux</code>\n'
    guide_text += '<b>date_of_receipt</b> - дата получения конфигурации в формате <code>YYYY-MM-DD HH-MI</code>\n'
    guide_text += '<b>link</b> - если вместо фото или файла *.conf нужна ссылка для XTLS/SS для ПК\n\n'
    guide_text += '<b>Не забываем прикрепить файл, если требуется!</b>'
    await message.answer(guide_text, parse_mode='HTML')


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
        await message.answer('Флаги введены неверно, их слишком мало!')
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
            await message.answer('Вы не приложили файл, либо добавили не верный тип вложения!')

    # if admin added link as 7th argument (link)
    elif len(arguments) == 7:
        flag_username_or_telegram_id, flag_protocol, flag_location, os, date_of_receipt_date, date_of_receipt_time, link = arguments

        # creating link for XTLS-Reality
        file_type = 'link'

    # if number of arguments are more then expected
    else:
        await message.answer('Флаги введены неверно, их слишком много!')
        return

    # if 1st argument is username
    if flag_username_or_telegram_id[0] == '@':
        client_id = await postgesql_db.get_clientID_by_username(flag_username_or_telegram_id)

    # if 1st argument is telegram_id
    else:
        client_id = await postgesql_db.get_clientID_by_telegramID(int(flag_username_or_telegram_id))

    # check 2nd argument as protocol_id
    match flag_protocol:
        case 'w':
            protocol_id = 1
        case 'x':
            protocol_id = 2
        case 's':
            protocol_id = 3
        case _:
            await message.answer('Протокол введен неверно!')
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
            await message.answer('Локация введена неверно!')
            return

    answer_text = '<code>INSERT INTO configurations(client_id, protocol_id, location_id, os, file_type, telegram_file_id, date_of_receipt) '
    answer_text += f"VALUES({client_id}, {protocol_id}, {location_id}, '{os}', '{file_type}', '{link}', TIMESTAMP '{date_of_receipt_date} {date_of_receipt_time}');</code>"
    await message.answer(answer_text, parse_mode='HTML')


@admin_mw.admin_only()
async def show_earnings(message: Message):
    """Send message with information about earned money per current month."""
    earnings_per_current_month: float = await postgesql_db.get_earnings_per_month()
    await message.answer(f'Так-так! Заработок за текущий месяц составляет <b>{earnings_per_current_month}₽</b>! \U00002728 \U00002728', parse_mode='HTML')


@admin_mw.admin_only()
async def check_user_configs(message: Message):
    """Send messages with configurations of another client.

    Used for test.
    """
    # taking user info (telegramID or username) from text after command
    user_info = message.text.split(' ')[1]

    # if user_info is username
    if user_info[0] == '@':
        client_id = await postgesql_db.get_clientID_by_username(user_info)

    # if user_info is user telegramID
    else:
        client_id = await postgesql_db.get_clientID_by_telegramID(user_info)

    # get information about specified client's configurations
    configurations_info = await postgesql_db.get_configurations_info(client_id)
    await message.answer(f'Информация о всех ваших конфигурациях, теперь не нужно искать их по диалогу с ботом!\n\nВсего конфигураций <b>{len(configurations_info)}</b>.',
                         parse_mode='HTML')

    # send message for every configuration
    for file_type, date_of_receipt, os, is_chatgpt_available, name, country, city, bandwidth, ping, telegram_file_id in configurations_info:
        await service_functions.send_configuration(message.from_user.id, file_type, date_of_receipt, os, is_chatgpt_available, name, country, city, bandwidth, ping, telegram_file_id)

    await message.answer('Напоминаю правила (/rules):\n1. Одно устройство - одна конфигурация.\n2. Конфигурациями делиться с другими людьми запрещено!')


@admin_mw.admin_only()
async def get_file_id(message: Message):
    """Send message with added file id."""
    # if message contains photo
    if message.photo:
        await message.answer(f'file_id фото\n<code>{message.photo[0].file_id}</code>', parse_mode='HTML')

    # if message contains document
    elif message.document:
        await message.answer(f'file_id документа:\n<code>{message.document.file_id}</code>', parse_mode='HTML')

    # any other case
    else:
        await message.answer('Файл не был прикреплен вместе с вызовом команды /fileid (/fid)!')


@admin_mw.admin_only()
async def send_configuration_fsm_start(call: CallbackQuery, state: FSMContext):
    """Start FSM for sending configurations for a client after pressing inline button and send instruction."""
    await admin_fsm.SendConfig.ready.set()
    async with state.proxy() as data:
        data['telegram_id'] = call.data

    guide_text = 'Активировано машинное состояние! Пришлите мне сообщение в формате (вместо переноса строк используйте пробелы):\n\n'
    guide_text += '<b>protocol</b> — <code>wireguard/wg/w</code> | <code>xtls-reality/xtls/reality/x</code> | <code>shadosocks/ss/s</code>\n'
    guide_text += '<b>location</b> — <code>netherlands/n</code> | <code>latvia/l</code> | <code>germany/g</code> | <code>usa/u</code>\n'
    guide_text += '<b>os</b> — <code>android</code> | <code>ios</code> | <code>windows</code> | <code>macos/mac</code> | <code>linux</code>\n'
    guide_text += '<b>link</b> — если вместо фото или файла *.conf нужна ссылка для XTLS/SS для ПК\n\n'
    guide_text += '<b>Не забываем прикрепить файл, если требуется!</b>'
    await call.message.answer(guide_text, parse_mode='HTML')
    await call.answer()


@admin_mw.admin_only()
async def send_configuration(message: Message, state: FSMContext):
    """Check configuration sended by admin and send it to client."""
    async with state.proxy() as data:
        telegram_id = int(data['telegram_id'])
    client_id = await postgesql_db.get_clientID_by_telegramID(telegram_id)

    try:
        # if message is text
        if text := message.text:
            # create configuration
            file_type = 'link'
            flag_protocol, flag_location, flag_os, flag_link = text.split(' ')
            await service_functions.create_configuration(client_id, file_type, flag_protocol, flag_location, flag_os, flag_link)
            _, date_of_receipt, os, is_chatgpt_available, name, country, city, bandwidth, ping, telegram_file_id = (await postgesql_db.get_configurations_info(client_id))[-1]

        # if message is document
        elif document := message.document:
            # create configuration
            file_type = 'document'
            flag_protocol, flag_location, flag_os = message.caption.split(' ')
            telegram_file_id = document.file_id
            await service_functions.create_configuration(client_id, file_type, flag_protocol, flag_location, flag_os, telegram_file_id=telegram_file_id)
            file_type, date_of_receipt, os, is_chatgpt_available, name, country, city, bandwidth, ping, telegram_file_id = (await postgesql_db.get_configurations_info(client_id))[-1]

        # if message is photo
        elif photo := message.photo:
            # create configuration
            file_type = 'photo'
            flag_protocol, flag_location, flag_os = message.caption.split(' ')
            telegram_file_id = photo[0].file_id
            await service_functions.create_configuration(client_id, file_type, flag_protocol, flag_location, flag_os, telegram_file_id=telegram_file_id)
            file_type, date_of_receipt, os, is_chatgpt_available, name, country, city, bandwidth, ping, telegram_file_id = (await postgesql_db.get_configurations_info(client_id))[-1]

        # other cases
        else:
            await message.reply('Вы предоставили неверный тип вложения!')
            return
        
        # send message to client, admin and finish FSM for sending configurations
        await bot.send_message(telegram_id, 'Ура, конфигурация получена!')
        await service_functions.send_configuration(telegram_id, file_type, date_of_receipt, os, is_chatgpt_available, name, country, city, bandwidth, ping, telegram_file_id)
        await message.reply(f'Отлично, конфигурация типа <b>{file_type}</b> отправлена!', parse_mode='HTML')
        await state.finish()

    # catch create_configuration() exceptions
    except ValueError as ve:
        await message.reply(f'Ошибка: {ve}\nСкорее всего, вы указали неверное число флагов!')
    except Exception as e:
        await message.reply(f'Ошибка: {e}')


def register_handlers_admin(dp: Dispatcher):
    dp.register_message_handler(fsm_reset, Text(equals=['_сброс_FSM', '_вернуться']), state='*')
    dp.register_message_handler(fsm_reset, commands=['reset'], state='*')
    dp.register_message_handler(show_admin_keyboard, commands=['admin'])
    dp.register_message_handler(notifications_menu, Text(equals='_отправка_сообщений'))
    dp.register_message_handler(notifications_send_message_everyone_fsm_start, Text(equals='_отправить_всем'))
    dp.register_message_handler(notifications_send_message_everyone, state=admin_fsm.SendMessage.everyone_decision, content_types='any')
    dp.register_message_handler(notifications_send_message_selected_fsm_start, Text(equals='_отправить_избранным'))
    dp.register_message_handler(notifications_send_message_selected_list, state=admin_fsm.SendMessage.selected_list)
    dp.register_message_handler(notifications_send_message_selected, state=admin_fsm.SendMessage.selected_decision, content_types='any')
    dp.register_message_handler(show_user_info_sql_fsm_start, Text(equals='_SQL_вставка_пользователя'))
    dp.register_message_handler(show_user_info_sql_fsm_start, commands=['sql_user'])
    dp.register_message_handler(show_user_info_sql, state=admin_fsm.UserInfo.ready)
    dp.register_message_handler(show_user_config_sql_cm_start, Text(equals='_SQL_вставка_конфигурации'))
    dp.register_message_handler(show_user_config_sql_cm_start, commands=['sql_config'])
    dp.register_message_handler(check_user_configs, state=admin_fsm.ConfigInfo.ready, commands=['check_configs'])
    dp.register_message_handler(show_user_config_sql, state=admin_fsm.ConfigInfo.ready, content_types=['text', 'photo', 'document'])
    dp.register_message_handler(show_earnings, Text(equals='* Заработок за месяц'))
    dp.register_message_handler(get_file_id, Text(equals='_узнать_id_файла'), content_types=['text', 'photo', 'document'])
    dp.register_message_handler(get_file_id, commands=['fileid', 'fid'], commands_ignore_caption=False, content_types=['text', 'photo', 'document'])
    dp.register_callback_query_handler(send_configuration_fsm_start, lambda call: call.data.isdigit(), state='*')
    dp.register_message_handler(send_configuration, content_types=['text', 'photo', 'document'], state=admin_fsm.SendConfig.ready)
