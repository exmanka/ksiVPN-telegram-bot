from bot_init import bot, admin_ID
from aiogram import types, Dispatcher
from aiogram.dispatcher.filters import Text
from src.states import admin_fsm
from src.middlewares import admin_mw
from src.database import postgesql_db


async def send_user_info(user_info, choice_info):
    await bot.send_message(admin_ID,\
                           f"Имя: <code>{user_info['fullname']}</code>\n"
                           f"Тэг: @{user_info['username']}\n"
                           f"ID: <code>{user_info['id']}</code>\n"
                           f"Промокод: <code>{choice_info['promo']}</code>\n"
                           f"Конфигурация: {choice_info['platform'][2:]}, {choice_info['os_name']}, {choice_info['chatgpt']} ChatGPT\n\n"
                           f"<b>Запрос на подключение от пользователя!</b>",
                           parse_mode='HTML')

@admin_mw.admin_only()
async def show_user_info_sql_cm_start(message: types.Message):
    await admin_fsm.FSMUserInfo.ready_to_answer.set()
    await message.reply('Активировано состояние для получения SQL-запроса на вставку пользователя! Перешлите мне сообщение, и я выведу всю возможную информацию!')

@admin_mw.admin_only()
async def show_user_info_sql(message: types.Message):
    if message.forward_from is None:
        await message.reply('К сожалению, не могу прочитать информацию о пользователе :(')
    else:
        user_info = {'first_name': message.forward_from.first_name,
                    'last_name': message.forward_from.last_name,
                    'username': message.forward_from.username,
                    'telegram_id': message.forward_from.id}
        
        if user_info['last_name'] is None and user_info['username'] is None:
            await message.reply(f"<code>INSERT INTO clients (name, telegram_id, register_date) VALUES('{user_info['first_name']}', "
                                f"{user_info['telegram_id']}, TIMESTAMP '2023-01-01 00:00');</code>", parse_mode='HTML')
            
        elif user_info['username'] is None:
            await message.reply(f"<code>INSERT INTO clients (name, surname, telegram_id, register_date) VALUES('{user_info['first_name']}', "
                                f"'{user_info['last_name']}', {user_info['telegram_id']}, TIMESTAMP '2023-01-01 00:00');</code>", parse_mode='HTML')
        
        elif user_info['last_name'] is None:
            await message.reply(f"<code>INSERT INTO clients (name, username, telegram_id, register_date) VALUES('{user_info['first_name']}', "
                                f"'@{user_info['username']}', {user_info['telegram_id']}, TIMESTAMP '2023-01-01 00:00');</code>", parse_mode='HTML')
            
        else:
            await message.reply(f"<code>INSERT INTO clients (name, surname, username, telegram_id, register_date) VALUES('{user_info['first_name']}', "
                                f"'{user_info['last_name']}', '@{user_info['username']}', {user_info['telegram_id']}, TIMESTAMP '2023-01-01 00:00');</code>",
                                parse_mode='HTML')

@admin_mw.admin_only()
async def show_user_config_sql_cm_start(message: types.Message):
    await admin_fsm.FSMConfigInfo.ready_to_answer.set()
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
async def show_user_config_sql(message: types.Message):

    # parse arguments
    if message.photo or message.document:
        arguments = message.caption.split(' ')
    else:
        arguments = message.text.split(' ')

    # if arguments are not full
    if len(arguments) < 6:
        await message.answer('Флаги введены неверно, их слишком мало!')
        return
    
    client_id = -1
    # if 1st argument is username
    if arguments[0][0] == '@':
        client_id = postgesql_db.find_clientID_by_username(arguments[0])[0]
    
    # if 1st argument is telegram_id
    else:
        client_id = postgesql_db.find_clientID_by_telegramID(int(arguments[0]))[0]

    protocol_id = -1
    # check 3rd argument as protocol_id
    match arguments[1]:
        case 'w':
            protocol_id = 1
        case 'x':
            protocol_id = 2
        case 's':
            protocol_id = 3

    location_id = -1
    # check 4th argument as location_id
    match arguments[2]:
        case 'n':
            location_id = 1
        case 'l':
            location_id = 2
        case 'g':
            location_id = 3
        case 'u':
            location_id = 4

    file_type = '-1'
    link = '-1'
    # check 6th argument exists
    if len(arguments) == 7:
        # creating link for XTLS-Reality
        file_type = 'link'
        link = arguments[6]
    
    # if photo was sended
    elif message.photo:
        file_type = 'photo'
        link = message.photo[0].file_id

    # if document was sended
    elif message.document:
        file_type = 'document'
        link = message.document.file_id

    answer_text = '<code>INSERT INTO configurations(client_id, protocol_id, location_id, os, file_type, telegram_file_id, date_of_receipt) '
    answer_text += f"VALUES({client_id}, {protocol_id}, {location_id}, '{arguments[3]}', '{file_type}', '{link}', TIMESTAMP '{arguments[4]} {arguments[5]}');</code>"

    await message.answer(answer_text, parse_mode='HTML') 

@admin_mw.admin_only()
async def check_user_configs(message: types.Message):
    
    # taking user info (telegramID or username) from text after command
    user_info = message.text.split(' ')[1]

    # if user_info is username
    if user_info[0] == '@':
        client_id = postgesql_db.find_clientID_by_username(user_info)[0]

    # if user_info is user telegramID
    else:
        client_id = postgesql_db.find_clientID_by_telegramID(user_info)[0]

    configurations_info = postgesql_db.show_configurations_info(client_id)
    await message.answer(f'Информация о всех ваших конфигурациях, теперь не нужно искать их по диалогу с ботом!\n\nВсего конфигураций <b>{len(configurations_info)}</b>.',
                         parse_mode='HTML')

    for config in configurations_info:
        answer_text = ''
        answer_text += f'<b>Создана</b>: {config[1]}\n'

        # creating answer text with ChatGPT option
        if config[3]:
            answer_text += f'<b>Платформа</b>: {config[2]} с доступом к ChatGPT\n'

        # creating answer text without ChatGPT option
        else:
            answer_text += f'<b>Платформа</b>: {config[2]}\n'

        answer_text += f'<b>Протокол</b>: {config[4]}\n'
        answer_text += f'<b>Локация VPN</b>: {config[5]}, {config[6]}, скорость до {config[7]} Мбит/с, ожидаемый пинг {config[8]} мс.'

        # if config was generated as photo
        if config[0] == 'photo':
            await bot.send_photo(message.from_user.id, config[9], answer_text, parse_mode='HTML', protect_content=True)

        # if config was generated as document
        elif config[0] == 'document':
            await bot.send_document(message.from_user.id, config[9], caption=answer_text, parse_mode='HTML', protect_content=True)

        # if config was generated as link
        else:
            answer_text = f'<code>{config[9]}</code>\n\n' + answer_text
            await bot.send_message(message.from_user.id, answer_text, parse_mode='HTML')

    await message.answer('Напоминаю правила (/rules):\n1. Одно устройство - одна конфигурация.\n2. Конфигурациями делиться с другими людьми запрещено!')

@admin_mw.admin_only()
async def get_file_id(message: types.Message):
    if message.photo:
        await message.answer(f'file_id фото\n<code>{message.photo[0].file_id}</code>', parse_mode='HTML')
    elif message.document:
        await message.answer(f'file_id документа:\n<code>{message.document.file_id}</code>', parse_mode='HTML')
    else:
        await message.answer('Файл не был прикреплен вместе с вызовом команды /fileid!')

@admin_mw.admin_only()
async def send_config_photo(message: types.Message):
    try:
        await bot.send_photo(int(message.reply_to_message.text.split('\n')[2][3:]), message.photo[0].file_id,\
                             'Готово! Ваш QR-код от сервера в ' + message.caption)
    except AttributeError:
        await message.reply('Вы не указали получателя!')
    except IndexError:
        await message.reply('Указано неподходящее сообщение!')
    except TypeError:
        await message.reply('Вы не указали страну подключения!')

@admin_mw.admin_only()
async def send_config_file(message: types.Message):
    try:
        await bot.send_document(int(message.reply_to_message.text.split('\n')[2][3:]), message.document.file_id)
        await bot.send_message(int(message.reply_to_message.text.split('\n')[2][3:]), 'Готово! Ваш файл конфигурации от сервера в ' +\
                               message.caption)
    except AttributeError:
        await message.reply('Вы не указали получателя!')
    except IndexError:
        await message.reply('Указано неподходящее сообщение!')
    except TypeError:
        await message.reply('Вы не указали страну подключения!')


def register_handlers_admin(dp : Dispatcher):
    dp.register_message_handler(show_user_info_sql_cm_start, commands=['sql_user'], state=None)
    dp.register_message_handler(show_user_info_sql, state=admin_fsm.FSMUserInfo.ready_to_answer)
    dp.register_message_handler(show_user_config_sql_cm_start, commands=['sql_config'], state=None)
    dp.register_message_handler(check_user_configs, state=admin_fsm.FSMConfigInfo.ready_to_answer, commands=['check_configs'])
    dp.register_message_handler(show_user_config_sql, state=admin_fsm.FSMConfigInfo.ready_to_answer)
    dp.register_message_handler(show_user_config_sql, state=admin_fsm.FSMConfigInfo.ready_to_answer, content_types=['photo', 'document'])
    dp.register_message_handler(get_file_id, commands_ignore_caption=False, commands=['fileid', 'fid'], content_types=['text', 'photo', 'document'])
    dp.register_message_handler(send_config_photo, content_types=['photo'])
    dp.register_message_handler(send_config_file, content_types=['document'])
