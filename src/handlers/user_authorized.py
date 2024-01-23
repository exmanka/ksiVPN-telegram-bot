import random
from decimal import Decimal
from aiogram import Dispatcher
from aiogram.types import Message, CallbackQuery, MediaGroup
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Text
from aiogram.utils.exceptions import MessageToDeleteNotFound
from src.middlewares import user_mw, throttling_mw
from src.keyboards import user_authorized_kb
from src.states import user_authorized_fsm
from src.database import postgres_dbms
from src.services import internal_functions, aiomoney, localization as loc
from bot_init import bot, YOOMONEY_TOKEN


@user_mw.authorized_only()
async def subscription_status(message: Message):
    """Send message with subscription status."""
    # if admin hasn't still sent client's first configuration
    if await postgres_dbms.is_subscription_not_started(message.from_user.id):
        await message.answer(loc.auth.msgs['sub_isnt_active'])
        return

    # if subscription is free
    elif await postgres_dbms.is_subscription_free(message.from_user.id):
        await message.answer(loc.auth.msgs['sub_is_free'], parse_mode='HTML')
        return

    # if subscription is acive
    elif await postgres_dbms.is_subscription_active(message.from_user.id):
        await message.answer(loc.auth.msgs['sub_active'], parse_mode='HTML')

    # if subsctiption is inactive
    else:
        await message.answer(loc.auth.msgs['sub_inactive'], parse_mode='HTML')

    await message.answer(loc.auth.msgs['sub_expiration_date'].format(await postgres_dbms.get_subscription_expiration_date(message.from_user.id)),
                         parse_mode='HTML')


@user_mw.authorized_only()
async def submenu_fsm_cancel(message: Message, state: FSMContext = None):
    """Cancel FSM state for submenu and return to menu keyboard regardless of machine state."""
    if state:
        await state.finish()
    await message.answer(loc.auth.msgs['return_to_main_menu'], parse_mode='HTML', reply_markup=user_authorized_kb.menu)


@user_mw.authorized_only()
async def sub_renewal_fsm_start(message: Message):
    """Start FSM for subscription renewal and show subscription renewal keyboard."""
    # if subscription is free for client
    if await postgres_dbms.is_subscription_free(message.from_user.id):
        await message.answer(loc.auth.msgs['sub_renewal_free'], parse_mode='HTML')
        return
    
    await user_authorized_fsm.PaymentMenu.menu.set()
    await message.answer(loc.auth.msgs['go_sub_renewal_menu'], parse_mode='HTML', reply_markup=user_authorized_kb.sub_renewal)


@user_mw.authorized_only()
@throttling_mw.antiflood(rate_limit=2)
async def sub_renewal_months_1(message: Message, state: FSMContext):
    """Create subscription renewal payment for 1 month."""
    await internal_functions.sub_renewal(message, state, months_number=1, discount=0.)


@user_mw.authorized_only()
@throttling_mw.antiflood(rate_limit=2)
async def sub_renewal_months_3(message: Message, state: FSMContext):
    """Create subscription renewal payment for 3 months."""
    await internal_functions.sub_renewal(message, state, months_number=3, discount=.1)


@user_mw.authorized_only()
@throttling_mw.antiflood(rate_limit=2)
async def sub_renewal_months_12(message: Message, state: FSMContext):
    """Create subscription renewal payment for 12 months."""
    await internal_functions.sub_renewal(message, state, months_number=12, discount=.15)


@user_mw.authorized_only()
async def sub_renewal_payment_history(message: Message):
    """Send messages with successful payments history."""
    payment_history = await postgres_dbms.get_payments_successful_info(await postgres_dbms.get_clientID_by_telegramID(message.from_user.id))
    is_payment_found = False

    # send message for every successful payment
    payment_price: Decimal
    for payment_id, sub_title, payment_price, payment_months_number, payment_date in payment_history:
        await message.answer(loc.auth.msgs['payment_history_message'].format(sub_title, payment_months_number, float(payment_price), payment_date, payment_id),
                             parse_mode='HTML')

        is_payment_found = True

    # if user has no successful payments
    if not is_payment_found:
        await message.answer(loc.auth.msgs['cant_find_payments'])


@user_mw.authorized_only()
async def sub_renewal_submenu_fsm_cancel(message: Message, state: FSMContext):
    """Cancel FSM state for subscription renewal, try to delete payment message and return to subscription renewal keyboard."""
    # get last user's payment's telegram message id
    last_payment_message_id = await postgres_dbms.get_payment_last_message_id(await postgres_dbms.get_clientID_by_telegramID(message.from_user.id))

    # try to delete payment message
    try:
        await bot.delete_message(message.chat.id, last_payment_message_id)

    # if already deleted
    except MessageToDeleteNotFound as _t:
        pass

    finally:
        # update state and keyboard
        await state.set_state(user_authorized_fsm.PaymentMenu.menu)
        await message.answer(loc.auth.msgs['cancel_payment'], parse_mode='HTML', reply_markup=user_authorized_kb.sub_renewal)


@user_mw.authorized_only()
@throttling_mw.antiflood(rate_limit=2)
async def sub_renewal_verification(message: Message, state: FSMContext):
    """Verify client's payments (per last hour) are successful according to YooMoney information."""
    wallet = aiomoney.YooMoneyWallet(YOOMONEY_TOKEN)

    # get client's initiated payments for last n minutes
    client_id = await postgres_dbms.get_clientID_by_telegramID(message.from_user.id)
    client_payments_ids = await postgres_dbms.get_paymentIDs_last(client_id, minutes=60)
    await message.answer(loc.auth.msgs['check_payment_hour'])
    await bot.send_chat_action(message.from_user.id, 'typing')

    is_payment_found = False
    for [payment_id] in client_payments_ids:

        # if payment wasn't added to db as successful and payment is successful according to Yoomoney:
        if await postgres_dbms.get_payment_status(payment_id) == False and await wallet.check_payment_on_successful(payment_id):

            # update payment in db as successful
            months_number = await postgres_dbms.get_payment_months_number(payment_id)
            await postgres_dbms.update_payment_successful(payment_id, client_id, months_number)

            # answer to a client
            await state.set_state(user_authorized_fsm.PaymentMenu.menu)
            await message.answer(loc.auth.msgs['payment_found'].format(payment_id), parse_mode='HTML', reply_markup=user_authorized_kb.sub_renewal)

            # notify admin about successful payment and check referral reward for other client
            await internal_functions.notify_admin_payment_success(client_id, months_number)
            await internal_functions.check_referral_reward(client_id)

            is_payment_found = True

    if not is_payment_found:
        await message.answer(loc.auth.msgs['cant_find_payments'])
        await message.answer(loc.auth.msgs['restore_payments'])


@user_mw.authorized_only()
async def account_fsm_start(message: Message):
    """Start FSM for account menu and show account menu keyboard."""
    await user_authorized_fsm.AccountMenu.menu.set()
    await message.answer(loc.auth.msgs['go_personal_account'], parse_mode='HTML', reply_markup=user_authorized_kb.account)


@user_mw.authorized_only()
async def account_client_info(message: Message):
    """Send message with information about client."""
    _, name, surname, username, _, register_date_parsed, *_ = await postgres_dbms.get_client_info_by_telegramID(message.from_user.id)

    # if client has surname
    surname_str = ''
    if surname is not None:
        surname_str = loc.auth.msgs['client_info_surname_str'].format(surname)

    # if client has username
    username_str = ''
    if username is not None:
        username_str = loc.auth.msgs['client_info_username_str'].format(username)

    await message.answer(loc.auth.msgs['client_info'].format(name, message.from_user.id, register_date_parsed, surname_str=surname_str, username_str=username_str),
                         parse_mode='HTML')


@user_mw.authorized_only()
async def account_subscription_info(message: Message):
    """Send message with information about client's subscription."""
    _, title, description, price = await postgres_dbms.get_subscription_info_by_clientID(await postgres_dbms.get_clientID_by_telegramID(message.from_user.id))
    await message.answer(loc.auth.msgs['subscription_info'].format(title, description, price), parse_mode='HTML')


@user_mw.authorized_only()
async def account_configurations_fsm_start(message: Message, state: FSMContext):
    """Start FSM for account configurations menu and show account configurations menu keyboard."""
    await state.set_state(user_authorized_fsm.AccountMenu.configs)
    await message.answer(loc.auth.msgs['go_config_menu'], parse_mode='HTML', reply_markup=user_authorized_kb.config)


@user_mw.authorized_only()
async def account_ref_program_fsm_start(message: Message, state: FSMContext):
    """Start FSM for account referral program menu and show account referral program menu keyboard."""
    await state.set_state(user_authorized_fsm.AccountMenu.ref_program)

    # use safe sending in case new bot tries to send photo using ksiVPN's bot file_id
    await internal_functions.send_photo_safely(message.from_user.id,
                                               telegram_file_id=loc.auth.tfids['ref_program_info'],
                                               caption=loc.auth.msgs['ref_program_info'],
                                               parse_mode='HTML',
                                               reply_markup=user_authorized_kb.ref_program)


@user_mw.authorized_only()
async def account_promo_fsm_start(message: Message, state: FSMContext):
    """Start FSM for account promocodes menu and show account promocodes menu keyboard."""
    await state.set_state(user_authorized_fsm.AccountMenu.promo)
    await message.answer(loc.auth.msgs['go_promo_menu'], parse_mode='HTML', reply_markup=user_authorized_kb.promo)
    await message.answer(loc.auth.msgs['enter_promo'], parse_mode='HTML')


@user_mw.authorized_only()
async def account_settings_fsm_start(message: Message, state: FSMContext):
    """Start FSM for account settings menu and show account settings menu keyboard."""
    await state.set_state(user_authorized_fsm.AccountMenu.settings)
    await message.answer(loc.auth.msgs['go_settings'], parse_mode='HTML', reply_markup=user_authorized_kb.settings)


@user_mw.authorized_only()
async def account_submenu_fsm_cancel(message: Message, state: FSMContext):
    """Cancel FSM state for account submenu and return to account menu keyboard."""
    await state.set_state(user_authorized_fsm.AccountMenu.menu)
    await message.answer(loc.auth.msgs['return_to_personal_account'], parse_mode='HTML', reply_markup=user_authorized_kb.account)


@user_mw.authorized_only()
async def account_configurations_info(message: Message):
    """Send messages with all client's available configurations."""
    configurations_info = await postgres_dbms.get_configurations_info(await postgres_dbms.get_clientID_by_telegramID(message.from_user.id))
    await message.answer(loc.auth.msgs['configs_info'].format(len(configurations_info)), parse_mode='HTML')

    # send message for every configuration
    for file_type, date_of_receipt, os, is_chatgpt_available, name, country, city, bandwidth, ping, telegram_file_id in configurations_info:
        await internal_functions.send_configuration(message.from_user.id, file_type, date_of_receipt, os, is_chatgpt_available, name, country, city, bandwidth, ping, telegram_file_id)

    await message.answer(loc.auth.msgs['configs_rules'], parse_mode='HTML')


@user_mw.authorized_only()
async def account_configurations_submenu_fsm_cancel(message: Message, state: FSMContext):
    """Cancel FSM state for account configurations submenu and return to account configurations menu keyboard."""
    await state.set_state(user_authorized_fsm.AccountMenu.configs)
    await message.answer(loc.auth.msgs['return_to_configs_menu'], parse_mode='HTML', reply_markup=user_authorized_kb.config)


@user_mw.authorized_only()
async def account_configurations_request_fsm_start(message: Message):
    """Start FSM for account configurations request menu, show account configurations request keyboard and request client's platform."""
    # if client's subscription is not active
    if not await postgres_dbms.is_subscription_active(message.from_user.id):
        await message.answer(loc.auth.msgs['cant_request_config'])
        return

    configs_number = await postgres_dbms.get_configurations_number(await postgres_dbms.get_clientID_by_telegramID(message.from_user.id))
    await message.answer(loc.auth.msgs['ask_three_questions'].format(configs_number), parse_mode='HTML')

    await user_authorized_fsm.ConfigMenu.platform.set()
    await message.answer(loc.unauth.msgs['choose_your_platform'], parse_mode='HTML', reply_markup=user_authorized_kb.config_platform)


@user_mw.authorized_only()
async def account_configurations_request_platform(message: Message, state: FSMContext):
    """Change account configurations request FSM state, save client's platform and request user's OS."""
    async with state.proxy() as data:
        data['platform'] = message.text

    # if client chooses smartphone option
    if message.text == loc.unauth.btns['smartphone']:
        await message.answer(loc.unauth.msgs['choose_your_os'], parse_mode='HTML', reply_markup=user_authorized_kb.config_mobile_os)

    # if client chooses pc option
    else:
        await message.answer(loc.unauth.msgs['choose_your_os'], parse_mode='HTML', reply_markup=user_authorized_kb.config_desktop_os)

    await state.set_state(user_authorized_fsm.ConfigMenu.os)


@user_mw.authorized_only()
async def account_configurations_request_os(message: Message, state: FSMContext):
    """Change account configurations request FSM state, save client's OS and request client's ChatGPT option."""
    async with state.proxy() as data:
        data['os_name'] = message.text

    await state.set_state(user_authorized_fsm.ConfigMenu.chatgpt)
    await message.answer(loc.unauth.msgs['choose_chatgpt_option'], parse_mode='HTML', reply_markup=user_authorized_kb.config_chatgpt)


@user_mw.authorized_only()
async def account_configurations_request_chatgpt_info(message: Message):
    """Send message with information about ChatGPT."""
    await message.answer(loc.unauth.msgs['chatgpt_info'], parse_mode='HTML')


@user_mw.authorized_only()
async def account_configurations_request_chatgpt(message: Message, state: FSMContext):
    """Change FSM state to account configurations menu, save client's ChatGPT option and send information about client's new configuration request to admin."""
    async with state.proxy() as data:
        data['chatgpt'] = message.text

        # send information about client's new configuration request to admin
        await internal_functions.send_configuration_request_to_admin({'fullname': message.from_user.full_name, 'username': message.from_user.username,
                                                                     'id': message.from_user.id}, data._data, is_new_client=False)

    await message.answer(loc.auth.msgs['wait_for_admin'], parse_mode='HTML', reply_markup=user_authorized_kb.config)
    await message.answer(loc.auth.msgs['i_wanna_sleep'])
    await state.set_state(user_authorized_fsm.AccountMenu.configs)


@user_mw.authorized_only()
async def account_settings_submenu_fsm_cancel(message: Message, state: FSMContext):
    """Cancel FSM state for account settings submenu and return to account settings menu keyboard."""
    await state.set_state(user_authorized_fsm.AccountMenu.settings)
    await message.answer(loc.auth.msgs['return_to_settings'], parse_mode='HTML', reply_markup=user_authorized_kb.settings)


@user_mw.authorized_only()
async def account_settings_chatgpt(message: Message, state: FSMContext):
    """Change account settings FSM state and show dinamic account settings ChatGPT mode keyboard."""
    await state.set_state(user_authorized_fsm.SettingsMenu.chatgpt)
    await message.answer(loc.auth.msgs['go_settings_chatgpt'], parse_mode='HTML', reply_markup=await user_authorized_kb.settings_chatgpt(await postgres_dbms.get_clientID_by_telegramID(message.from_user.id)))
    await message.answer(loc.auth.msgs['settings_chatgpt_info'], parse_mode='HTML')


@user_mw.authorized_only()
async def account_settings_chatgpt_mode(message: Message, state: FSMContext):
    """Turn on/off client's ChatGPT mode for answering unrecognized messages."""
    # update ChatGPT mode status and get current ChatGPT mode status
    chatgpt_mode_status: bool = await postgres_dbms.update_chatgpt_mode(await postgres_dbms.get_clientID_by_telegramID(message.from_user.id))

    # if user switches ChatGPT mode from settings
    if await state.get_state() == user_authorized_fsm.SettingsMenu.chatgpt.state:
        reply_keyboard = await user_authorized_kb.settings_chatgpt(await postgres_dbms.get_clientID_by_telegramID(message.from_user.id))

    # if user switches ChatGPT mode using command
    else:
        reply_keyboard = None

    # if user turned option on
    if chatgpt_mode_status:
        await message.answer(loc.auth.msgs['chatgpt_on'], parse_mode='HTML', reply_markup=reply_keyboard)

    # if user turned option off
    else:
        await message.answer(loc.auth.msgs['chatgpt_off'], parse_mode='HTML', reply_markup=reply_keyboard)


@user_mw.authorized_only()
async def account_settings_notifications(message: Message, state: FSMContext):
    """Change account settings FSM state and show dinamic account settings notifications keyboard."""
    client_id = await postgres_dbms.get_clientID_by_telegramID(message.from_user.id)
    await state.set_state(user_authorized_fsm.SettingsMenu.notifications)
    await message.answer(loc.auth.msgs['go_settings_notifications'], parse_mode='HTML', reply_markup=await user_authorized_kb.settings_notifications(client_id))
    await message.answer(loc.auth.msgs['settings_notifications_info'], parse_mode='HTML')


@user_mw.authorized_only()
async def account_settings_notifications_1d(message: Message):
    """Turn on/off client's receiving notifications 1 day before subscription expiration."""
    client_id = await postgres_dbms.get_clientID_by_telegramID(message.from_user.id)
    expiration_in_1d_state = await postgres_dbms.update_notifications_1d(client_id)

    # if user turned option on
    if expiration_in_1d_state:
        await message.answer(loc.auth.msgs['1d_on'], parse_mode='HTML', reply_markup=await user_authorized_kb.settings_notifications(client_id))

    # if user turned option off
    else:
        await message.answer(loc.auth.msgs['1d_off'], parse_mode='HTML', reply_markup=await user_authorized_kb.settings_notifications(client_id))


@user_mw.authorized_only()
async def account_settings_notifications_3d(message: Message):
    """Turn on/off client's receiving notifications 3 days before subscription expiration."""
    client_id = await postgres_dbms.get_clientID_by_telegramID(message.from_user.id)
    expiration_in_3d_state = await postgres_dbms.update_notifications_3d(client_id)

    # if user turned option on
    if expiration_in_3d_state:
        await message.answer(loc.auth.msgs['3d_on'], parse_mode='HTML', reply_markup=await user_authorized_kb.settings_notifications(client_id))

    # if user turned option off
    else:
        await message.answer(loc.auth.msgs['3d_off'], parse_mode='HTML', reply_markup=await user_authorized_kb.settings_notifications(client_id))


@user_mw.authorized_only()
async def account_settings_notifications_7d(message: Message):
    """Turn on/off client's receiving notifications 7 days before subscription expiration."""
    client_id = await postgres_dbms.get_clientID_by_telegramID(message.from_user.id)
    expiration_in_7d_state = await postgres_dbms.update_notifications_7d(client_id)

    # if user turned option on
    if expiration_in_7d_state:
        await message.answer(loc.auth.msgs['7d_on'], parse_mode='HTML', reply_markup=await user_authorized_kb.settings_notifications(client_id))

    # if user turned option off
    else:
        await message.answer(loc.auth.msgs['7d_off'], parse_mode='HTML', reply_markup=await user_authorized_kb.settings_notifications(client_id))


@user_mw.authorized_only()
async def account_ref_program_info(message: Message):
    """Send message with information about client's participation in referral program."""
    who_invited_client = await postgres_dbms.get_invited_by_client_info(message.from_user.id)
    who_was_invited_by_client = await postgres_dbms.get_invited_clients_list(message.from_user.id)

    # if someone invited client into project
    if who_invited_client:
        name, username = who_invited_client

        # if someone has username
        username_str = await internal_functions.format_none_string(username)
        
        await message.answer(loc.auth.msgs['invited_by'].format(name, username_str), parse_mode='HTML')

    # if nobody invited client into project
    else:
        await message.answer(loc.auth.msgs['invited_by_nobody'])

    # if client invited someone into project
    if who_was_invited_by_client:
        invited_str = ''
        for idx, (name, username) in enumerate(who_was_invited_by_client):

            # if someone has username
            username_str = await internal_functions.format_none_string(username)
            
            invited_str += loc.auth.msgs['who_was_invited_str'].format(idx + 1, name, username_str)

        await message.answer(loc.auth.msgs['who_was_invited'].format(invited_str=invited_str), parse_mode='HTML')

    # if client hasn't invited other clients yet
    else:
        await message.answer(loc.auth.msgs['nobody_was_invited'])


@user_mw.authorized_only()
async def account_ref_program_invite(message: Message):
    """Send message with random invite text from messages.py."""
    ref_promocode = await postgres_dbms.get_referral_promo(message.from_user.id)
    text: str = random.choice(loc.auth.msgs['ref_program_invites_texts']).format(ref_promocode)
    await message.answer(text, parse_mode='HTML')


@user_mw.authorized_only()
async def account_ref_program_promocode(message: Message):
    """Send message with client's own referral promocode."""
    ref_promo_phrase: str = await postgres_dbms.get_referral_promo(message.from_user.id)
    await message.answer(loc.auth.msgs['your_ref_code'].format(ref_promo_phrase), parse_mode='HTML')


@user_mw.authorized_only()
async def account_promo_check(message: Message, state: FSMContext):
    """Check entered promocode is valid, send information about successfuly entered promocode, update subscription period for client.

    If specified promocode is local promocode, it can also change subscription type for client.
    """
    # if promo is referral
    if await postgres_dbms.is_referral_promo(message.text):
        await message.answer(loc.auth.msgs['error_promo_entered_ref_code'])
        return

    # get information about promocode
    client_id = await postgres_dbms.get_clientID_by_telegramID(message.from_user.id)
    global_promo_info = await postgres_dbms.get_global_promo_info(message.text)
    local_promo_info = await postgres_dbms.get_local_promo_info(message.text)

    # if promo is global and exists in system
    if global_promo_info:
        global_promo_id, *_, bonus_time, bonus_time_parsed = global_promo_info

        # if global promo wasn't entered by client before
        if not await postgres_dbms.is_global_promo_already_entered(client_id, global_promo_id):

            # if global promo didn't expire
            if await postgres_dbms.is_global_promo_valid(global_promo_id):

                # if global promo still has available activations number
                if await postgres_dbms.is_global_promo_has_remaining_activations(global_promo_id):

                    await postgres_dbms.insert_client_entered_global_promo(client_id, global_promo_id, bonus_time)
                    await internal_functions.notify_admin_promo_entered(client_id, message.text, 'global')
                    await message.answer(loc.auth.msgs['global_promo_accepted'].format(bonus_time_parsed), parse_mode='HTML', reply_markup=user_authorized_kb.account)
                    await state.set_state(user_authorized_fsm.AccountMenu.menu)

                else:
                    await message.answer(loc.auth.msgs['error_promo_limit_activations'])

            else:
                await message.answer(loc.auth.msgs['error_promo_expired'])

        else:
            await message.answer(loc.auth.msgs['error_promo_already_entered'])

    # if promo is local and exists in system
    elif local_promo_info:
        local_promo_id, *_, bonus_time, bonus_time_parsed, provided_sub_id = local_promo_info

        # if local promo accessible by client
        if await postgres_dbms.is_local_promo_accessible(client_id, local_promo_id):

            # if local promo wasn't entered by client before
            if not await postgres_dbms.is_local_promo_already_entered(client_id, local_promo_id):

                # if local promo didn't expire
                if await postgres_dbms.is_local_promo_valid(local_promo_id):

                    await postgres_dbms.insert_client_entered_local_promo(client_id, local_promo_id, bonus_time)
                    await internal_functions.notify_admin_promo_entered(client_id, message.text, 'local')

                    # if local promo changes client's subscription
                    new_sub_str = ''
                    if provided_sub_id:
                        await postgres_dbms.update_client_subscription(client_id, provided_sub_id)
                        _, title, _, price = await postgres_dbms.get_subscription_info_by_subID(provided_sub_id)
                        new_sub_str = loc.auth.msgs['new_sub_str'].format(title, price)

                    await message.answer(loc.auth.msgs['loсal_promo_accepted'].format(bonus_time_parsed, new_sub_str=new_sub_str), parse_mode='HTML', reply_markup=user_authorized_kb.account)
                    await state.set_state(user_authorized_fsm.AccountMenu.menu)

                else:
                    await message.answer(loc.auth.msgs['error_promo_expired'])

            else:
                await message.answer(loc.auth.msgs['error_promo_already_entered'])

        else:
            await message.answer(loc.auth.msgs['error_promo_inaccessible'])

    # if promo not found in system
    else:
        await message.answer(loc.auth.msgs['error_promo_not_exist'])


@user_mw.authorized_only()
async def account_promo_info(message: Message):
    """Send message with information about entered by client promocodes."""
    ref_promos, global_promos, local_promos = await postgres_dbms.get_client_entered_promos(await postgres_dbms.get_clientID_by_telegramID(message.from_user.id))

    # information about entered referral promocode
    ref_promo_str = ''
    if ref_promos:
        ref_promo_phrase, client_creator_name = ref_promos
        ref_promo_str = loc.auth.msgs['ref_promo_str'].format(ref_promo_phrase, client_creator_name)

    # information about entered global promocodes
    global_promos_str = ''
    if global_promos:
        global_promo_row_str = ''
        for idx, (global_promo_phrase, bonus_time_parsed, date_of_entry_parsed) in enumerate(global_promos):
            global_promo_row_str += loc.auth.msgs['global_promo_row_str'].format(idx + 1, global_promo_phrase, bonus_time_parsed, date_of_entry_parsed)

        global_promos_str = loc.auth.msgs['global_promos_str'].format(global_promo_row_str=global_promo_row_str)

    # information about entered local promocodes
    local_promos_str = ''
    if local_promos:
        local_promo_row_str = ''
        for idx, (local_promo_phrase, bonus_time_parsed, date_of_entry_parsed) in enumerate(local_promos):
            local_promo_row_str += loc.auth.msgs['local_promo_row_str'].format(idx + 1, local_promo_phrase, bonus_time_parsed, date_of_entry_parsed)

        local_promos_str = loc.auth.msgs['local_promos_str'].format(local_promo_row_str=local_promo_row_str)

    # user hasn't entered promocodes at all
    if ref_promo_str + global_promos_str + local_promos_str == '':
        await message.answer(loc.auth.msgs['no_promo_entered'])

    else:
        await message.answer(ref_promo_str + global_promos_str + local_promos_str, parse_mode='HTML')


@user_mw.authorized_only()
async def configuration_instruction(call: CallbackQuery):
    """Send message with instruction for configuration specified by inline button."""
    configuration_protocol_name, configuration_os = call.data.split('--')

    # answer without photos
    # await call.message.reply(loc.auth.msgs['instructions'][configuration_protocol_name.lower()][configuration_os.lower()],
    #                          parse_mode='HTML', disable_web_page_preview=True)

    # get objects from localization
    instruction_text = loc.auth.msgs['instructions'][configuration_protocol_name.lower()][configuration_os.lower()]
    instruction_images_list = loc.auth.tfids['instructions'][configuration_protocol_name.lower()][configuration_os.lower()]
    
    # use safe sending in case new bot tries to send photos using ksiVPN's bot files_ids
    await internal_functions.reply_media_group_safely(call.message,
                                                      telegram_files_ids_list=instruction_images_list,
                                                      caption=instruction_text,
                                                      parse_mode='HTML')
    await call.answer()


@user_mw.authorized_only()
async def show_project_rules(message: Message):
    """Send message with information about project rules."""
    # use safe sending in case new bot tries to send photo using ksiVPN's bot file_id
    await internal_functions.send_photo_safely(message.from_user.id,
                                               telegram_file_id=loc.auth.tfids['rules'],
                                               caption=loc.auth.msgs['rules'],
                                               parse_mode='HTML')


@user_mw.authorized_only()
@throttling_mw.antiflood(rate_limit=2)
async def restore_payments(message: Message):
    """Try to verify client's payments (per whole time) are successful according to YooMoney information."""
    # get client's initiated payments for all time
    wallet = aiomoney.YooMoneyWallet(YOOMONEY_TOKEN)
    client_id = await postgres_dbms.get_clientID_by_telegramID(message.from_user.id)
    client_payments_ids = await postgres_dbms.get_paymentIDs(client_id)

    is_payment_found = False
    await bot.send_chat_action(message.from_user.id, 'typing')
    for [payment_id] in client_payments_ids:

        # if payment wasn't added to db as successful and payment is successful according to Yoomoney:
        if await postgres_dbms.get_payment_status(payment_id) == False and await wallet.check_payment_on_successful(payment_id):

            # update payment in db as successful
            months_number = await postgres_dbms.get_payment_months_number(payment_id)
            await postgres_dbms.update_payment_successful(payment_id, client_id, months_number)

            # answer to a client
            await message.answer(loc.auth.msgs['payment_found'].format(payment_id), parse_mode='HTML')

            # notify admin about successful payment and check referral reward for other client
            await internal_functions.notify_admin_payment_success(client_id, months_number)
            await internal_functions.check_referral_reward(client_id)

            is_payment_found = True

    if not is_payment_found:
        await message.answer(loc.auth.msgs['cant_find_payments_restore'])


def register_handlers_authorized_client(dp: Dispatcher):
    dp.register_message_handler(subscription_status, Text(loc.auth.btns['sub_status']))
    dp.register_message_handler(submenu_fsm_cancel, Text(loc.auth.btns['return_main_menu']), state=[None,
                                                                                                    user_authorized_fsm.AccountMenu.menu,
                                                                                                    user_authorized_fsm.PaymentMenu.menu])
    dp.register_message_handler(sub_renewal_fsm_start, Text(loc.auth.btns['sub_renewal']))
    dp.register_message_handler(sub_renewal_months_1, Text(loc.auth.btns['payment_1mnth']), state=user_authorized_fsm.PaymentMenu.menu)
    dp.register_message_handler(sub_renewal_months_3, Text(loc.auth.btns['payment_3mnth']), state=user_authorized_fsm.PaymentMenu.menu)
    dp.register_message_handler(sub_renewal_months_12, Text(loc.auth.btns['payment_12mnth']), state=user_authorized_fsm.PaymentMenu.menu)
    dp.register_message_handler(sub_renewal_payment_history, Text(loc.auth.btns['payment_history']), state=user_authorized_fsm.PaymentMenu.menu)
    dp.register_message_handler(sub_renewal_submenu_fsm_cancel, Text(loc.auth.btns['payment_cancel']), state=[None,
                                                                                                              user_authorized_fsm.PaymentMenu.verification])
    dp.register_message_handler(sub_renewal_verification, Text(loc.auth.btns['payment_check']), state=user_authorized_fsm.PaymentMenu.verification)
    dp.register_message_handler(account_fsm_start, Text(loc.auth.btns['personal_account']))
    dp.register_message_handler(account_client_info, Text(loc.auth.btns['about_client']), state=user_authorized_fsm.AccountMenu.menu)
    dp.register_message_handler(account_subscription_info, Text(loc.auth.btns['about_sub']), state=user_authorized_fsm.AccountMenu.menu)
    dp.register_message_handler(account_submenu_fsm_cancel, Text(loc.auth.btns['return_to_account_menu_1']), state=[None,
                                                                                                                    user_authorized_fsm.AccountMenu.configs,
                                                                                                                    user_authorized_fsm.AccountMenu.ref_program,
                                                                                                                    user_authorized_fsm.AccountMenu.settings])
    dp.register_message_handler(account_submenu_fsm_cancel, Text(loc.auth.btns['return_to_account_menu_2']), state=[None,
                                                                                                                    user_authorized_fsm.AccountMenu.promo])
    dp.register_message_handler(account_ref_program_fsm_start, Text(loc.auth.btns['ref_program']), state=user_authorized_fsm.AccountMenu.menu)
    dp.register_message_handler(account_promo_fsm_start, Text(loc.auth.btns['promo']), state=user_authorized_fsm.AccountMenu.menu)
    dp.register_message_handler(account_configurations_fsm_start, Text(loc.auth.btns['configs']), state=user_authorized_fsm.AccountMenu.menu)
    dp.register_message_handler(account_settings_fsm_start, Text(loc.auth.btns['settings']), state=user_authorized_fsm.AccountMenu.menu)
    dp.register_message_handler(account_ref_program_info, Text(loc.auth.btns['ref_program_participation']), state=user_authorized_fsm.AccountMenu.ref_program)
    dp.register_message_handler(account_ref_program_invite, Text(loc.auth.btns['generate_invite']), state=user_authorized_fsm.AccountMenu.ref_program)
    dp.register_message_handler(account_ref_program_promocode, Text(loc.auth.btns['show_ref_code']), state=user_authorized_fsm.AccountMenu.ref_program)
    dp.register_message_handler(account_promo_info, Text(loc.auth.btns['used_promos']), state=user_authorized_fsm.AccountMenu.promo)
    dp.register_message_handler(account_promo_check, state=user_authorized_fsm.AccountMenu.promo)
    dp.register_message_handler(account_configurations_info, Text(loc.auth.btns['current_configs']), state=user_authorized_fsm.AccountMenu.configs)
    dp.register_message_handler(account_configurations_submenu_fsm_cancel, Text(loc.auth.btns['return_to_configs_menu']), state=[None,
                                                                                                                                 user_authorized_fsm.ConfigMenu.platform,
                                                                                                                                 user_authorized_fsm.ConfigMenu.os,
                                                                                                                                 user_authorized_fsm.ConfigMenu.chatgpt])
    dp.register_message_handler(account_configurations_request_fsm_start, Text(loc.auth.btns['request_config']), state=user_authorized_fsm.AccountMenu.configs)
    dp.register_message_handler(account_configurations_request_platform, Text([loc.unauth.btns[key] for key in ('smartphone', 'pc')]),
                                state=user_authorized_fsm.ConfigMenu.platform)
    dp.register_message_handler(account_configurations_request_os, Text([loc.unauth.btns[key] for key in ('android', 'ios', 'windows', 'macos', 'linux')]),
                                state=user_authorized_fsm.ConfigMenu.os)
    dp.register_message_handler(account_configurations_request_chatgpt_info, Text(loc.unauth.btns['what_is_chatgpt'], ignore_case=True),
                                state=user_authorized_fsm.ConfigMenu.chatgpt)
    dp.register_message_handler(account_configurations_request_chatgpt, Text([loc.unauth.btns[key] for key in ('use_chatgpt', 'dont_use_chatgpt')]),
                                state=user_authorized_fsm.ConfigMenu.chatgpt)
    dp.register_message_handler(account_settings_submenu_fsm_cancel, Text(loc.auth.btns['return_to_settings']), state=[None,
                                                                                                                       user_authorized_fsm.SettingsMenu.chatgpt,
                                                                                                                       user_authorized_fsm.SettingsMenu.notifications])
    dp.register_message_handler(account_settings_chatgpt, Text(loc.auth.btns['settings_chatgpt_mode']), state=user_authorized_fsm.AccountMenu.settings)
    dp.register_message_handler(account_settings_chatgpt_mode, Text([loc.auth.btns[key] for key in ('chatgpt_on', 'chatgpt_off')]), state=user_authorized_fsm.SettingsMenu.chatgpt)
    dp.register_message_handler(account_settings_notifications, Text(loc.auth.btns['settings_notifications']), state=user_authorized_fsm.AccountMenu.settings)
    dp.register_message_handler(account_settings_notifications_1d, Text([loc.auth.btns[key] for key in ('1d_on', '1d_off')]), state=user_authorized_fsm.SettingsMenu.notifications)
    dp.register_message_handler(account_settings_notifications_3d, Text([loc.auth.btns[key] for key in ('3d_on', '3d_off')]), state=user_authorized_fsm.SettingsMenu.notifications)
    dp.register_message_handler(account_settings_notifications_7d, Text([loc.auth.btns[key] for key in ('7d_on', '7d_off')]), state=user_authorized_fsm.SettingsMenu.notifications)
    dp.register_callback_query_handler(configuration_instruction, lambda call: '--' in call.data, state='*')
    dp.register_message_handler(show_project_rules, Text(loc.auth.btns['rules']))
    dp.register_message_handler(show_project_rules, commands=['rules'], state='*')
    dp.register_message_handler(restore_payments, commands=['restore_payments'], state='*')
    dp.register_message_handler(account_settings_chatgpt_mode, commands=['chatgpt_mode'], state='*')
