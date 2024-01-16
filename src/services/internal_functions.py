import asyncio
from aiogram.types import Message
from aiogram.dispatcher import FSMContext
from aiogram.utils.exceptions import MessageToDeleteNotFound
from src.keyboards import user_authorized_kb, admin_kb
from src.states import user_authorized_fsm
from src.database import postgres_dbms
from src.services import aiomoney, localization as loc
from bot_init import bot, ADMIN_ID, YOOMONEY_TOKEN


async def format_none_string(string: str | None, prefix: str = ' ', postfix: str = '') -> str:
    """Return empty string '' if specified object is None, else return specified specified string with prefix and postfix.
    
    Use for fast object conversion before str.format method usage.

    :param string: object that needs to be formatted
    :param prefix: prefix added to specified string if it's not None, defaults to ' '
    :param postfix: prefix added to specified string if it's not None, defaults to ''
    :return: empty string or prefix + string + postfix
    """    
    return '' if string is None else prefix + string + postfix


async def send_message_by_telegram_id(telegram_id: int, message: Message):
    """Send specified message by provided telegram_id.

    :param telegram_id:
    :param message:
    :raises Exception: unrecognized message type
    """
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

    # other cases
    else:
        raise Exception('unrecognized message type')


async def send_configuration(telegram_id: int,
                             configuration_file_type: str,
                             configuration_date_of_receipt: str,
                             configuration_os: str,
                             configuration_is_chatgpt_available: bool,
                             configuration_protocol_name: str,
                             server_country: str,
                             server_city: str,
                             server_bandwidth: int,
                             server_ping: int,
                             configuration_telegram_file_id: str):
    """Send message with specified configuration by telegram_id.

    :param telegram_id:
    :param configuration_file_type: file type ('photo', 'document' or 'link)
    :param configuration_date_of_receipt: date the configuration was created
    :param configuration_os: name of OS provided by configuration
    :param configuration_is_chatgpt_available: is ChatGPT available for configuration
    :param configuration_protocol_name: name of protocol provided by configuration
    :param server_country: name of country where server provided by configuration is situated
    :param server_city: name of city where server provided by configuration is situated
    :param server_bandwidth: bandwidth of server provided by configuration
    :param server_ping: average ping of server provided by configuration
    :param configuration_telegram_file_id: telegram file id of provided configuration
    :raises Exception: wrong file type
    """
    answer_text = await create_configuration_description(configuration_date_of_receipt, configuration_os, configuration_is_chatgpt_available, configuration_protocol_name, server_country, server_city, server_bandwidth, server_ping)

    # if config was generated as photo
    if configuration_file_type == 'photo':
        await bot.send_photo(telegram_id, configuration_telegram_file_id, answer_text, parse_mode='HTML', protect_content=True,
                             reply_markup=await user_authorized_kb.configuration_instruction_inlkb(configuration_protocol_name, configuration_os))

    # if config was generated as document
    elif configuration_file_type == 'document':
        await bot.send_document(telegram_id, configuration_telegram_file_id, caption=answer_text, parse_mode='HTML', protect_content=True,
                                reply_markup=await user_authorized_kb.configuration_instruction_inlkb(configuration_protocol_name, configuration_os))

    # if config was generated as link
    elif configuration_file_type == 'link':
        answer_text = f'<code>{configuration_telegram_file_id}</code>\n\n' + answer_text
        await bot.send_message(telegram_id, answer_text, parse_mode='HTML',
                               reply_markup=await user_authorized_kb.configuration_instruction_inlkb(configuration_protocol_name, configuration_os))

    else:
        raise Exception('wrong file type')


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

    # if request was sended by new client with zero configurations
    if is_new_client:

        # if client didn't enter referral promocode during registration
        if choice['promo'] is None:
            ref_promo_str = loc.internal.msgs['config_request_new_client_no_ref_promo_str']

        # if client entered referral promocode during registration
        else:

            # get information about entered referral promocode
            _, client_creator_id, provided_sub_id, _, bonus_time_parsed = await postgres_dbms.get_refferal_promo_info_by_phrase(choice['promo'])
            client_creator_name, client_creator_surname, client_creator_username, client_creator_telegram_id, *_ = await postgres_dbms.get_client_info_by_clientID(client_creator_id)
            *_, price = await postgres_dbms.get_subscription_info_by_subID(provided_sub_id)

            # convert surname and username for beautiful formatting
            client_creator_surname_str = await format_none_string(client_creator_surname)
            client_creator_username_str = await format_none_string(client_creator_username)
            ref_promo_str = loc.internal.msgs['config_request_new_client_ref_promo_str'].\
                format(choice['promo'], client_creator_name, client_creator_surname_str, client_creator_username_str, client_creator_telegram_id, bonus_time_parsed, price)

        await bot.send_message(ADMIN_ID,
                               loc.internal.msgs['config_request_new_client'].\
                                format(client['fullname'], username_str, client['id'], choice['platform'][2:], choice['os_name'], choice['chatgpt'], client_id, ref_promo_str=ref_promo_str),
                               reply_markup=await admin_kb.configuration_inline(client['id']),
                               parse_mode='HTML')

    # if request was sended by old client with at least one configuration
    else:
        await bot.send_message(ADMIN_ID,
                               loc.internal.msgs['config_request_old_client'].\
                                format(client['fullname'], username_str, client['id'], choice['platform'][2:], choice['os_name'], choice['chatgpt'], client_id),
                               reply_markup=await admin_kb.configuration_inline(client['id']),
                               parse_mode='HTML')


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
        id, _, expiration_date_parsed, *_, bonus_time_parsed = await postgres_dbms.get_global_promo_info(promo_phrase)

    elif promo_type == 'local':
        id, _, expiration_date_parsed, _, bonus_time_parsed, provided_sub_id = await postgres_dbms.get_local_promo_info(promo_phrase)

        # if local promo changes client's subscription
        if provided_sub_id:
            *_, price = await postgres_dbms.get_subscription_info_by_subID(provided_sub_id)
            new_sub_str = loc.internal.msgs['admin_promo_was_etnered_local_promo_new_sub_str'].format(price)

    else:
        raise Exception('wrong promo type was entered')

    await bot.send_message(ADMIN_ID,
                           loc.internal.msgs['admin_promo_was_entered'].\
                            format(client_id, username_str, name, surname_str, telegram_id, promo_type, id, bonus_time_parsed, expiration_date_parsed, new_sub_str=new_sub_str),
                           parse_mode='HTML')


async def notify_admin_payment_success(client_id: int, months_number: int):
    """Send message for admin with information about new successful client's payment.

    :param client_id:
    :param months_number: number of month client paid for
    """
    name, surname, username, telegram_id, *_ = await postgres_dbms.get_client_info_by_clientID(client_id)

    # convert surname and username for beautiful formatting
    surname_str = await format_none_string(surname)
    username_str = await format_none_string(username)
    await bot.send_message(ADMIN_ID, loc.internal.msgs['admin_successful_payment'].format(months_number, client_id, username_str, name, surname_str, telegram_id),
                           parse_mode='HTML')


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
    *_, bonus_time_parsed = await postgres_dbms.get_refferal_promo_info_by_clientCreatorID(client_creator_id)

    client_creator_telegram_id = await postgres_dbms.get_telegramID_by_clientID(client_creator_id)
    await bot.send_message(client_creator_telegram_id,
                           loc.internal.msgs['ref_promo_was_entered'].format(referral_client_name, referral_client_username_str, bonus_time_parsed),
                           parse_mode='HTML')


async def create_configuration_description(configuration_date_of_receipt: str,
                                           configuration_os: str,
                                           configuration_is_chatgpt_available: bool,
                                           configuration_protocol_name: str,
                                           server_country: str,
                                           server_city: str,
                                           server_bandwidth: int,
                                           server_ping: int,
                                           link: str | None = None) -> str:
    """Return description for specified configurations.

    :param configuration_date_of_receipt: date the configuration was created
    :param configuration_os: name of OS provided by configuration
    :param configuration_is_chatgpt_available: is ChatGPT available for configuration
    :param configuration_protocol_name: name of protocol provided by configuration
    :param server_country: name of country where server provided by configuration is situated
    :param server_city: name of city where server provided by configuration is situated
    :param server_bandwidth: bandwidth of server provided by configuration
    :param server_ping: average ping of server provided by configuration
    :param server_link: vless link for XTLS-Reality configuration, defaults to None
    :return: description of configurations with HTML-tags
    :rtype: str
    """
    # convert vless link if exists
    link_str = await format_none_string(link, prefix='<code>', postfix='</code>\n\n')

    # creating answer text with ChatGPT option
    if configuration_is_chatgpt_available:
        platform_str = loc.internal.msgs['platform_str_chatgpt'].format(configuration_os)

    # creating answer text without ChatGPT option
    else:
        platform_str = loc.internal.msgs['platform_str_no_chatgpt'].format(configuration_os)

    return loc.internal.msgs['config_info'].format(configuration_date_of_receipt, configuration_protocol_name, server_country, server_city, server_bandwidth, server_ping,
                                               link_str=link_str, platform_str=platform_str)


async def create_configuration(client_id: int,
                               file_type: str,
                               flag_protocol: str,
                               flag_location: str,
                               flag_os: str,
                               flag_link: str | None = None,
                               telegram_file_id: int | None = None):
    """Create new configuration in db.

    :param client_id:
    :param file_type: file type in ('link', 'document', 'photo')
    :param flag_protocol: protocol name in ('wireguar', 'w', 'wg', 'xtls-reality', 'x', 'xtls', 'reality', 'shadowsocks', 's', 'ss')
    :param flag_location: location name in ('netherlands', 'n', 'latvia', 'l', 'germany', 'g', 'usa', 'u')
    :param flag_os: os name in ('android', 'ios', 'windows', 'linux', 'macos', 'mac')
    :param flag_link: link for XTLS-Reality starting from 'vless://'
    :param telegram_file_id:
    :raises Exception: invalid telegram_file_id
    :raises Exception: invalid file_type
    """
    link = None
    if file_type == 'link':
        protocol_id, location_id, os_enum, link = await get_configuration_sql_data(flag_protocol, flag_location, flag_os, flag_link)
        await postgres_dbms.insert_configuration(client_id, protocol_id, location_id, os_enum, file_type, link)

    elif file_type == 'document' or 'photo':
        if telegram_file_id is None:
            raise Exception(loc.internal.msgs['error_no_telegram_file_id'])

        protocol_id, location_id, os_enum, _ = await get_configuration_sql_data(flag_protocol, flag_location, flag_os, flag_link)
        await postgres_dbms.insert_configuration(client_id, protocol_id, location_id, os_enum, file_type, telegram_file_id)

    else:
        raise Exception(loc.internal.msgs['error_bad_file_type'])


async def get_configuration_sql_data(protocol: str, location: str, os: str, link: str | None = None) -> tuple[int, int, str]:
    """Return data suitable for SQL-query for configuration creation.

    :param protocol: protocol name in ('wireguar', 'w', 'wg', 'xtls-reality', 'x', 'xtls', 'reality', 'shadowsocks', 's', 'ss')
    :param location: location name in ('netherlands', 'n', 'latvia', 'l', 'germany', 'g', 'usa', 'u')
    :param os: os name in ('android', 'ios', 'windows', 'linux', 'macos', 'mac')
    :param link: link for XTLS-Reality starting from 'vless://'
    :raises Exception: invalid protocol type
    :raises Exception: invalid country
    :raises Exception: invalid OS type
    :raises Exception: invalid link
    :return: tuple (protocol_id, location_id, os_enum, link)
    """
    protocol_id = None
    match protocol.lower():
        case 'wireguard':
            protocol_id = 1
        case 'w':
            protocol_id = 1
        case 'wg':
            protocol_id = 1

        case 'x':
            protocol_id = 2
        case 'xtls':
            protocol_id = 2
        case 'reality':
            protocol_id = 2
        case 'xtls-reality':
            protocol_id = 2

        case 's':
            protocol_id = 3
        case 'ss':
            protocol_id = 3
        case 'shadowsocks':
            protocol_id = 3

        case _:
            raise Exception(loc.internal.msgs['error_bad_protocol'])

    location_id = None
    match location.lower():
        case 'n':
            location_id = 1
        case 'netherlands':
            location_id = 1

        case 'l':
            location_id = 2
        case 'latvia':
            location_id = 2

        case 'g':
            location_id = 3
        case 'germany':
            location_id = 3

        case 'u':
            location_id = 4
        case 'usa':
            location_id = 4

        case _:
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

    return protocol_id, location_id, os_enum, link


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
        await postgres_dbms.add_subscription_time(client_creator_id, days=30)

        # notify old client about new bonus
        # if client's username exists (add whitespace for good string formatting)
        ref_client_username_str = await format_none_string(ref_client_username)
        client_creator_telegram_id = await postgres_dbms.get_telegramID_by_clientID(client_creator_id)
        await bot.send_message(client_creator_telegram_id,
                               loc.internal.msgs['ref_client_paid_for_sub'].format(ref_client_name, ref_client_username_str),
                               parse_mode='HTML')


async def autocheck_payment_status(payment_id: int) -> str:
    """Automatically check payment is successful according to YooMoney for 300 seconds.

    :param payment_id:
    :return: autochecker status, 'success' - payment was successfully finished, 'failure' - payment wasn't successfully finished in 300 seconds,
    'already_checked' - payment was already checked and added to db as successful by other functions
    """
    wallet = aiomoney.YooMoneyWallet(YOOMONEY_TOKEN)

    # wait for user to redirect to Yoomoney site first 10 seconds
    await asyncio.sleep(10)

    # after that check Yoomoney payment status using linear equation
    k = 0.04
    b = 1
    for x in range(100):

        # if user has already checked successful payment and it was added to account subscription
        if await postgres_dbms.get_payment_status(payment_id):
            return 'already_checked'

        # if payment was successful according to YooMoney info
        if await wallet.check_payment_on_successful(payment_id):
            return 'success'

        await asyncio.sleep(k * x + b)

    return 'failure'


async def authorization_complete(message: Message, state: FSMContext):
    """Complete authorization of new client: add client to db and send new client's configuration request to administrator.

    :param message:
    :param state:
    """
    used_ref_promo_id = None
    provided_sub_id = None
    bonus_time = None
    client = message.from_user
    async with state.proxy() as data:

        # if new client entered referral promocode during registration
        if phrase := data['promo']:
            used_ref_promo_id, _, provided_sub_id, bonus_time, _ = await postgres_dbms.get_refferal_promo_info_by_phrase(phrase)

        await postgres_dbms.insert_client(client.first_name, client.id, client.last_name, client.username, used_ref_promo_id, provided_sub_id, bonus_time)
        await send_configuration_request_to_admin({'fullname': client.full_name, 'username': client.username, 'id': client.id}, data._data, is_new_client=True)

    await message.answer(loc.internal.msgs['wait_for_admin_answer'], reply_markup=user_authorized_kb.menu)
    await message.answer(loc.auth.msgs['i_wanna_sleep'])
    await state.finish()


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
    wallet = aiomoney.YooMoneyWallet(YOOMONEY_TOKEN)
    payment_form = await wallet.create_payment_form(
        amount_rub=payment_price,
        unique_label=payment_id,
        payment_source=aiomoney.PaymentSource.YOOMONEY_WALLET,
        success_redirect_url="https://t.me/ksiVPN_bot"
    )

    # answer with ReplyKeyboardMarkup
    await message.answer(loc.internal.msgs['wait_payment'], parse_mode='HTML', reply_markup=user_authorized_kb.sub_renewal_verification)
    await state.set_state(user_authorized_fsm.PaymentMenu.verification)

    # answer with InlineKeyboardMarkup with link to payment
    discount_str = ''
    if discount:
        discount_str = loc.internal.msgs['discount_str'].format(sub_price * months_number * discount)

    message_info = await message.answer(loc.internal.msgs['payment_form'].format(sub_title, months_number, payment_price, payment_id, discount_str=discount_str),
                                        parse_mode='HTML', reply_markup=await user_authorized_kb.sub_renewal_link_inline(payment_form.link_for_customer))

    # add telegram_id for created payment
    await postgres_dbms.update_payment_telegram_message_id(payment_id, message_info['message_id'])

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
            await bot.delete_message(message.chat.id, message_info['message_id'])

        # if already deleted
        except MessageToDeleteNotFound as _t:
            pass

        finally:
            await message.answer(loc.internal.msgs['payment_successful'].format(payment_id), reply_markup=user_authorized_kb.sub_renewal)
