from bot_init import bot, ADMIN_ID
from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Text
from aiogram.utils.exceptions import ChatNotFound
from src.states import admin_fsm
from src.keyboards import admin_kb
from src.middlewares import admin_mw
from src.database import postgesql_db


async def send_user_info(user: dict, choice: dict, is_new_user: bool):
    if is_new_user:
        await bot.send_message(ADMIN_ID,
                                f"Имя: <code>{user['fullname']}</code>\n"
                                f"Тэг: @{user['username']}\n"
                                f"ID: <code>{user['id']}</code>\n"
                                f"Промокод: <code>{choice['promo']}</code>\n"
                                f"Конфигурация: {choice['platform'][2:]}, {choice['os_name']}, {choice['chatgpt']} ChatGPT\n\n"
                                f"<b>Запрос на подключение от нового пользователя!</b>",
                                reply_markup=await admin_kb.configuration(user['id']),
                                parse_mode='HTML')
        
    else:
        await bot.send_message(ADMIN_ID,
                                f"Имя: <code>{user['fullname']}</code>\n"
                                f"Тэг: @{user['username']}\n"
                                f"ID: <code>{user['id']}</code>\n"
                                f"Конфигурация: {choice['platform'][2:]}, {choice['os_name']}, {choice['chatgpt']} ChatGPT\n\n"
                                f"<b>Запрос дополнительной конфигурации от пользователя!</b>",
                                parse_mode='HTML')
        
        await bot.send_message(ADMIN_ID,
                               f"Сообщение, на которое нужно ответить через <b>reply</b>!\n\n"
                               f"Metadata: {user['id']}",
                               parse_mode='HTML')
        
async def send_message_by_telegram_id(telegram_id: int, message: types.Message):
    # if message is text
    if text := message.text:
        await bot.send_message(telegram_id, text, parse_mode='HTML')

    # if message is animation (GIF or H.264/MPEG-4 AVC video without sound)
    elif animation := message.animation:
        await bot.send_animation(telegram_id, animation.file_id)

    # if message is audio (audio file to be treated as music)
    elif audio := message.audio:
        await bot.send_audio(telegram_id, audio.file_id, caption=message.caption, parse_mode='HTML')

    # if message is document
    elif document := message.document:
        await bot.send_document(telegram_id, document.file_id, caption=message.caption, parse_mode='HTML')

    # if message is photo
    elif photo := message.photo:
        await bot.send_photo(telegram_id, photo[0].file_id, caption=message.caption, parse_mode='HTML')

    # if message is sticker
    elif sticker := message.sticker:
        await bot.send_sticker(telegram_id, sticker.file_id)

    # if message is video
    elif video := message.video:
        await bot.send_video(telegram_id, video.file_id, caption=message.caption, parse_mode='HTML')

    # if message is video note
    elif video_note := message.video_note:
        await bot.send_video_note(telegram_id, video_note.file_id)

    # if message is voice
    elif voice := message.voice:
        await bot.send_voice(telegram_id, voice.file_id, caption=message.caption, parse_mode='HTML')

@admin_mw.admin_only()
async def cm_reset(message: types.Message, state: FSMContext):
    await state.finish()
    await message.answer('Сброс машинного состояния и клавиатуры!', reply_markup=admin_kb.menu_kb)

@admin_mw.admin_only()
async def show_admin_keyboard(message: types.Message):
    await message.reply('Для вызова данного меню используйте /admin.\b\bДоступные команды:\n\n/fileid (/fid)\n/sql_user\n/sql_config', reply_markup=admin_kb.menu_kb)

@admin_mw.admin_only()
async def notifications_menu(message: types.Message):
    await message.answer('Открываю клавиатуру отправки сообщений пользователям!', reply_markup=admin_kb.notification_kb)

@admin_mw.admin_only()
async def notifications_send_message_everyone_cm_start(message: types.Message, state: FSMContext):
    await state.set_state(admin_fsm.FSMSendMessage.everyone_decision)

    answer_message = 'Активировано машинное состояние! Введите необходимую информацию следующим сообщением, а также приложите файлы при необходимости!\n\n'
    answer_message += 'Введите /perfect, чтобы подтвердить выбор последнего отправленного сообщения!'
    await message.answer(answer_message, parse_mode='HTML')

@admin_mw.admin_only()
async def notifications_send_message_everyone(message: types.Message, state: FSMContext):

    # if message looks good for admin
    if message.text and message.text == '/perfect':

        answer_message = ''
        async with state.proxy() as data:
            for idx, [telegram_id] in enumerate(postgesql_db.get_clients_telegram_ids()):

                # if user didn't write to bot
                try:
                    await send_message_by_telegram_id(telegram_id, data['message'])
                
                # add him to answer_message
                except ChatNotFound as _t:
                    name, surname, username, telegram_id, _ = postgesql_db.show_user_info(telegram_id)
                    answer_message += f'{idx + 1}. {name} {surname} {username} (tg_id: <code>{telegram_id}</code>)\n'

        # if some users didn't write to bot
        if answer_message:
            answer_message = 'Ладненько, сообщение отправлено!\n\nПользователи, до которых сообщение не дошло:\n' + answer_message

        # if all users use bot
        else:
            answer_message = 'Ладненько, сообщение отправлено!\n\nУра, сообщение получат все пользователи сервиса!'

        await message.answer(answer_message)

        return

    await message.answer('Вот так будет выглядеть Ваше сообщение:')

    # echo message
    await send_message_by_telegram_id(message.from_user.id, message)

    # save last message
    async with state.proxy() as data:
        data['message'] = message

@admin_mw.admin_only()
async def notifications_send_message_selected_cm_start(message: types.Message, state: FSMContext):
    await state.set_state(admin_fsm.FSMSendMessage.selected_list)

    answer_message = 'Активировано машинное состояние! Введите через запятую <b>username</b> или <b>telegram_id</b> пользователей, для которых предназначена рассылка.'
    await message.answer(answer_message, parse_mode='HTML')

@admin_mw.admin_only()
async def notifications_send_message_selected_list(message: types.Message, state: FSMContext):

    # parse users mentioned in message
    selected_users = message.text.split(' ')

    selected_telegram_ids = []
    for user in selected_users:

        # if user mentioned by username and exists in db
        if user[0] == '@':
            if telegram_id := postgesql_db.get_telegramID_by_username(user):
                selected_telegram_ids.append(telegram_id[0])

        # if user mentioned by telegram_id and exists in db
        elif postgesql_db.find_clientID_by_telegramID(user):
            selected_telegram_ids.append(user)

    async with state.proxy() as data:
        data['selected_telegram_ids'] = selected_telegram_ids
        
    await state.set_state(admin_fsm.FSMSendMessage.selected_decision)

    # show selected users info
    answer_message = ''
    for idx, telegram_id in enumerate(selected_telegram_ids):
        name, surname, username, telegram_id, _ = postgesql_db.show_user_info(telegram_id)
        answer_message += f'{idx + 1}. {name} {surname} {username} (tg_id: <code>{telegram_id}</code>)\n'

    # if at least 1 user is in db
    if answer_message:
        answer_message = 'Сообщение будет отправленно пользователям:\n\n' + answer_message

    # if mentioned people are not in db
    else:
        answer_message = 'Вы ошиблись при вводе пользователей! Сообщение ни до кого не дойдет!'

    await message.answer(answer_message, parse_mode='HTML')

    answer_message = 'Теперь введите необходимую информацию следующим сообщением, а также приложите файлы при необходимости!\n\n'
    answer_message += 'Введите /perfect, чтобы подтвердить выбор последнего отправленного сообщения!'
    await message.answer(answer_message)

@admin_mw.admin_only()
async def notifications_send_message_selected(message: types.Message, state: FSMContext):

    # if message looks good for admin
    if message.text and message.text == '/perfect':

        answer_message = ''
        async with state.proxy() as data:
            for idx, telegram_id in enumerate(data['selected_telegram_ids']):

                # if user didn't write to bot
                try:
                    await send_message_by_telegram_id(telegram_id, data['message'])
                
                # add him to answer_message
                except ChatNotFound as _t:
                    name, surname, username, telegram_id, _ = postgesql_db.show_user_info(telegram_id)
                    answer_message += f'{idx + 1}. {username} ({name}, {surname}), telegram_id <b>{telegram_id}</b>\n'

        # if some users didn't write to bot
        if answer_message:
            answer_message = 'Ладненько, сообщение отправлено!\n\nПользователи, до которых сообщение не дошло:\n' + answer_message

        # if all users use bot
        else:
            answer_message = 'Ладненько, сообщение отправлено!\n\nУра, сообщение получат все указанные пользователи!'

        await message.answer(answer_message)
        await cm_reset(message, state)

        return

    await message.answer('Вот так будет выглядеть Ваше сообщение:')

    # echo message
    await send_message_by_telegram_id(message.from_user.id, message)

    # save last message
    async with state.proxy() as data:
        data['message'] = message

@admin_mw.admin_only()
async def show_user_info_sql_cm_start(message: types.Message):
    await admin_fsm.FSMUserInfo.ready.set()

    message_answer = 'Активировано состояние для получения SQL-запроса на вставку пользователя! Перешлите мне сообщение, и я выведу всю возможную информацию!\n\n'
    message_answer += 'Кстати, проверить, какие конфигурации доступны пользователю можно командой /check_configs <telegram_id> | <username>'
    await message.reply(message_answer)

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
    await admin_fsm.FSMConfigInfo.ready.set()
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
        await message.answer('Файл не был прикреплен вместе с вызовом команды /fileid (/fid)!')

@admin_mw.admin_only()
async def send_configuration(message: types.Message):
    try:
        # if message is text
        if text := message.text:
            await bot.send_message(message.reply_to_message.text.split(' ')[-1], 'Готово! Ваш файл конфигурации от сервера в ' +\
                            text)
        
        # if message is document
        elif document := message.document:
            await bot.send_document(message.reply_to_message.text.split(' ')[-1], document.file_id, message.caption)

        # if message is photo
        elif photo := message.photo:
            await bot.send_photo(message.reply_to_message.text.split(' ')[-1], photo[0].file_id,\
                            'Готово! Ваш QR-код от сервера в ' + message.caption)
            
        # other cases
        else:
            await message.reply('Вы предоставили неверный тип вложения!')

    except AttributeError:
        await message.reply('Вы не указали получателя!')
    except IndexError:
        await message.reply('Указано неподходящее сообщение!')
    except TypeError:
        await message.reply('Вы не указали страну подключения!')

def register_handlers_admin(dp : Dispatcher):
    dp.register_message_handler(cm_reset, Text(equals=['_сброс_FSM', '_вернуться']), state='*')
    dp.register_message_handler(cm_reset, commands=['reset'], state='*')
    dp.register_message_handler(show_admin_keyboard, commands=['admin'])
    dp.register_message_handler(notifications_menu, Text(equals='_отправка_сообщений'))
    dp.register_message_handler(notifications_send_message_everyone_cm_start, Text(equals='_отправить_всем'))
    dp.register_message_handler(notifications_send_message_everyone, state=admin_fsm.FSMSendMessage.everyone_decision, content_types='any')
    dp.register_message_handler(notifications_send_message_selected_cm_start, Text(equals='_отправить_избранным'))
    dp.register_message_handler(notifications_send_message_selected_list, state=admin_fsm.FSMSendMessage.selected_list)
    dp.register_message_handler(notifications_send_message_selected, state=admin_fsm.FSMSendMessage.selected_decision, content_types='any')
    dp.register_message_handler(show_user_info_sql_cm_start, Text(equals='_SQL_вставка_пользователя'))
    dp.register_message_handler(show_user_info_sql_cm_start, commands=['sql_user'])
    dp.register_message_handler(show_user_info_sql, state=admin_fsm.FSMUserInfo.ready)
    dp.register_message_handler(show_user_config_sql_cm_start, Text(equals='_SQL_вставка_конфигурации'))
    dp.register_message_handler(show_user_config_sql_cm_start, commands=['sql_config'])
    dp.register_message_handler(check_user_configs, state=admin_fsm.FSMConfigInfo.ready, commands=['check_configs'])
    dp.register_message_handler(show_user_config_sql, state=admin_fsm.FSMConfigInfo.ready, content_types=['text', 'photo', 'document'])
    dp.register_message_handler(get_file_id, Text(equals='_узнать_id_файла'), content_types=['text', 'photo', 'document'])
    dp.register_message_handler(get_file_id, commands=['fileid', 'fid'], commands_ignore_caption=False, content_types=['text', 'photo', 'document'])
    dp.register_message_handler(send_configuration, content_types=['text', 'photo', 'document'])
