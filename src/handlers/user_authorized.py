import random
from decimal import Decimal
from aiogram import F, Router
from aiogram.enums import ChatAction
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from src.middlewares import user_authorized_mw, throttling_mw
from src.keyboards import user_authorized_kb
from src.states import user_authorized_fsm
from src.database import postgres_dbms
from src.services import internal_functions, aiomoney, localization as loc
from src.services.date_formatting import format_localized_bonus_days, format_localized_datetime
from src.config import settings
from src.runtime import bot


router = Router(name="user_authorized")


async def _safe_delete_message(chat_id: int, message_id: int) -> None:
    """Delete a message ignoring 'message to delete not found' errors."""
    try:
        await bot.delete_message(chat_id, message_id)
    except TelegramBadRequest:
        pass


@router.message(F.text == loc.auth.btns['sub_status'])
@user_authorized_mw.authorized_only()
async def subscription_status(message: Message):
    """Send message with subscription status."""
    # if admin hasn't still sent client's first configuration
    if await postgres_dbms.is_subscription_not_started(message.from_user.id):
        # if client needs to renew subscription before receiving his first configuration
        await internal_functions.notify_client_if_subscription_must_be_renewed_to_receive_configuration(message.from_user.id)

        await message.answer(loc.auth.msgs['sub_isnt_active'])
        return

    elif await postgres_dbms.is_subscription_free(message.from_user.id):
        await message.answer(loc.auth.msgs['sub_is_free'])
        return

    elif await postgres_dbms.is_subscription_active(message.from_user.id):
        await message.answer(loc.auth.msgs['sub_active'])

    else:
        await message.answer(loc.auth.msgs['sub_inactive'])

    await message.answer(loc.auth.msgs['sub_expiration_date'].format(format_localized_datetime(await postgres_dbms.get_subscription_expiration_date(message.from_user.id))))


@router.message(
    F.text == loc.auth.btns['return_main_menu'],
    StateFilter(None, user_authorized_fsm.AccountMenu.menu, user_authorized_fsm.PaymentMenu.menu),
)
@user_authorized_mw.authorized_only()
async def submenu_fsm_cancel(message: Message, state: FSMContext):
    """Cancel FSM state for submenu and return to menu keyboard regardless of machine state."""
    await state.clear()
    await message.answer(loc.auth.msgs['return_to_main_menu'], reply_markup=user_authorized_kb.menu)


@router.message(F.text == loc.auth.btns['sub_renewal'])
@user_authorized_mw.authorized_only()
async def sub_renewal_fsm_start(message: Message, state: FSMContext):
    """Start FSM for subscription renewal and show subscription renewal keyboard."""
    if await postgres_dbms.is_subscription_free(message.from_user.id):
        await message.answer(loc.auth.msgs['sub_renewal_free'])
        return

    await state.set_state(user_authorized_fsm.PaymentMenu.menu)
    await message.answer(loc.auth.msgs['go_sub_renewal_menu'], reply_markup=user_authorized_kb.sub_renewal)


@router.message(
    F.text == loc.auth.btns['payment_1mnth'],
    StateFilter(user_authorized_fsm.PaymentMenu.menu),
)
@user_authorized_mw.authorized_only()
@throttling_mw.antiflood(rate_limit=4)
async def sub_renewal_months_1(message: Message, state: FSMContext):
    """Create subscription renewal payment for 1 month."""
    await internal_functions.sub_renewal(message, state, months_number=1, discount=0.)


@router.message(
    F.text == loc.auth.btns['payment_3mnth'],
    StateFilter(user_authorized_fsm.PaymentMenu.menu),
)
@user_authorized_mw.authorized_only()
@throttling_mw.antiflood(rate_limit=4)
async def sub_renewal_months_3(message: Message, state: FSMContext):
    """Create subscription renewal payment for 3 months."""
    await internal_functions.sub_renewal(message, state, months_number=3, discount=.1)


@router.message(
    F.text == loc.auth.btns['payment_12mnth'],
    StateFilter(user_authorized_fsm.PaymentMenu.menu),
)
@user_authorized_mw.authorized_only()
@throttling_mw.antiflood(rate_limit=4)
async def sub_renewal_months_12(message: Message, state: FSMContext):
    """Create subscription renewal payment for 12 months."""
    await internal_functions.sub_renewal(message, state, months_number=12, discount=.15)


@router.message(
    F.text == loc.auth.btns['payment_history'],
    StateFilter(user_authorized_fsm.PaymentMenu.menu),
)
@user_authorized_mw.authorized_only()
async def sub_renewal_payment_history(message: Message):
    """Send messages with successful payments history."""
    payment_history = await postgres_dbms.get_payments_successful_info(await postgres_dbms.get_clientID_by_telegramID(message.from_user.id))
    is_payment_found = False

    payment_price: Decimal
    for payment_id, sub_title, payment_price, payment_months_number, payment_date in payment_history:
        await message.answer(loc.auth.msgs['payment_history_message'].format(sub_title, payment_months_number, float(payment_price), format_localized_datetime(payment_date), payment_id))
        is_payment_found = True

    if not is_payment_found:
        await message.answer(loc.auth.msgs['cant_find_payments'])


@router.message(
    F.text == loc.auth.btns['payment_cancel'],
    StateFilter(None, user_authorized_fsm.PaymentMenu.verification),
)
@user_authorized_mw.authorized_only()
async def sub_renewal_submenu_fsm_cancel(message: Message, state: FSMContext):
    """Cancel FSM state for subscription renewal, try to delete payment message and return to subscription renewal keyboard."""
    last_payment_message_id = await postgres_dbms.get_payment_last_message_id(await postgres_dbms.get_clientID_by_telegramID(message.from_user.id))

    await _safe_delete_message(message.chat.id, last_payment_message_id)

    await state.set_state(user_authorized_fsm.PaymentMenu.menu)
    await message.answer(loc.auth.msgs['cancel_payment'], reply_markup=user_authorized_kb.sub_renewal)


@router.message(
    F.text == loc.auth.btns['payment_check'],
    StateFilter(user_authorized_fsm.PaymentMenu.verification),
)
@user_authorized_mw.authorized_only()
@throttling_mw.antiflood(rate_limit=4)
async def sub_renewal_verification(message: Message, state: FSMContext):
    """Verify client's payments (per last hour) are successful according to YooMoney information."""
    wallet = aiomoney.YooMoneyWallet(settings.payments.yoomoney.token.get_secret_value())

    client_id = await postgres_dbms.get_clientID_by_telegramID(message.from_user.id)
    client_payments_ids = await postgres_dbms.get_paymentIDs_last(client_id, minutes=60)
    await message.answer(loc.auth.msgs['check_payment_hour'])
    await bot.send_chat_action(message.from_user.id, ChatAction.TYPING)

    is_payment_found = False
    for [payment_id] in client_payments_ids:
        if await postgres_dbms.get_payment_status(payment_id) == False and await wallet.check_payment_on_successful(payment_id):
            months_number = await postgres_dbms.get_payment_months_number(payment_id)
            await postgres_dbms.update_payment_successful(payment_id, client_id, months_number)

            await state.set_state(user_authorized_fsm.PaymentMenu.menu)
            await message.answer(loc.auth.msgs['payment_found'].format(payment_id), reply_markup=user_authorized_kb.sub_renewal)

            message_id = await postgres_dbms.get_payment_telegram_message_id(payment_id)
            await _safe_delete_message(message.chat.id, message_id)

            await internal_functions.notify_admin_payment_success(client_id, months_number)
            await internal_functions.check_referral_reward(client_id)
            is_payment_found = True

    if not is_payment_found:
        await message.answer(loc.auth.msgs['cant_find_payments'])
        await message.answer(loc.auth.msgs['restore_payments'])


@router.message(F.text == loc.auth.btns['personal_account'])
@user_authorized_mw.authorized_only()
async def account_fsm_start(message: Message, state: FSMContext):
    """Start FSM for account menu and show account menu keyboard."""
    await state.set_state(user_authorized_fsm.AccountMenu.menu)
    await message.answer(loc.auth.msgs['go_personal_account'], reply_markup=user_authorized_kb.account)


@router.message(
    F.text == loc.auth.btns['about_client'],
    StateFilter(user_authorized_fsm.AccountMenu.menu),
)
@user_authorized_mw.authorized_only()
async def account_client_info(message: Message):
    """Send message with information about client."""
    _, name, surname, username, register_date, _ = await postgres_dbms.get_client_info_by_telegramID(message.from_user.id)

    surname_str = ''
    if surname is not None:
        surname_str = loc.auth.msgs['client_info_surname_str'].format(surname)

    username_str = ''
    if username is not None:
        username_str = loc.auth.msgs['client_info_username_str'].format(username)

    await message.answer(loc.auth.msgs['client_info'].format(name, message.from_user.id, format_localized_datetime(register_date), surname_str=surname_str, username_str=username_str))


@router.message(
    F.text == loc.auth.btns['about_sub'],
    StateFilter(user_authorized_fsm.AccountMenu.menu),
)
@user_authorized_mw.authorized_only()
async def account_subscription_info(message: Message):
    """Send message with information about client's subscription."""
    _, title, description, price = await postgres_dbms.get_subscription_info_by_clientID(await postgres_dbms.get_clientID_by_telegramID(message.from_user.id))
    await message.answer(loc.auth.msgs['subscription_info'].format(title, description, price))


@router.message(
    F.text == loc.auth.btns['return_to_account_menu_1'],
    StateFilter(
        None,
        user_authorized_fsm.AccountMenu.configs,
        user_authorized_fsm.AccountMenu.ref_program,
        user_authorized_fsm.AccountMenu.settings,
    ),
)
@router.message(
    F.text == loc.auth.btns['return_to_account_menu_2'],
    StateFilter(None, user_authorized_fsm.AccountMenu.promo),
)
@user_authorized_mw.authorized_only()
async def account_submenu_fsm_cancel(message: Message, state: FSMContext):
    """Cancel FSM state for account submenu and return to account menu keyboard."""
    await state.set_state(user_authorized_fsm.AccountMenu.menu)
    await message.answer(loc.auth.msgs['return_to_personal_account'], reply_markup=user_authorized_kb.account)


@router.message(
    F.text == loc.auth.btns['ref_program'],
    StateFilter(user_authorized_fsm.AccountMenu.menu),
)
@user_authorized_mw.authorized_only()
@user_authorized_mw.nonblank_subscription_only()
async def account_ref_program_fsm_start(message: Message, state: FSMContext):
    """Start FSM for account referral program menu and show account referral program menu keyboard."""
    await state.set_state(user_authorized_fsm.AccountMenu.ref_program)
    await internal_functions.send_photo_safely(message.from_user.id,
                                               telegram_file_id=loc.auth.tfids['ref_program_info'],
                                               caption=loc.auth.msgs['ref_program_info'],
                                               reply_markup=user_authorized_kb.ref_program)


@router.message(
    F.text == loc.auth.btns['promo'],
    StateFilter(user_authorized_fsm.AccountMenu.menu),
)
@user_authorized_mw.authorized_only()
@user_authorized_mw.nonblank_subscription_only()
async def account_promo_fsm_start(message: Message, state: FSMContext):
    """Start FSM for account promocodes menu and show account promocodes menu keyboard."""
    await state.set_state(user_authorized_fsm.AccountMenu.promo)
    await message.answer(loc.auth.msgs['go_promo_menu'], reply_markup=user_authorized_kb.promo)
    await message.answer(loc.auth.msgs['enter_promo'])


@router.message(
    F.text == loc.auth.btns['configs'],
    StateFilter(user_authorized_fsm.AccountMenu.menu),
)
@user_authorized_mw.authorized_only()
@user_authorized_mw.nonblank_subscription_only()
async def account_configurations_fsm_start(message: Message, state: FSMContext):
    """Start FSM for account configurations menu and show account configurations menu keyboard."""
    await internal_functions.notify_client_if_subscription_must_be_renewed_to_receive_configuration(message.from_user.id)

    await state.set_state(user_authorized_fsm.AccountMenu.configs)
    await message.answer(loc.auth.msgs['go_config_menu'], reply_markup=user_authorized_kb.config)


@router.message(
    F.text == loc.auth.btns['settings'],
    StateFilter(user_authorized_fsm.AccountMenu.menu),
)
@user_authorized_mw.authorized_only()
async def account_settings_fsm_start(message: Message, state: FSMContext):
    """Start FSM for account settings menu and show account settings menu keyboard."""
    await state.set_state(user_authorized_fsm.AccountMenu.settings)
    await message.answer(loc.auth.msgs['go_settings'], reply_markup=user_authorized_kb.settings)


@router.message(
    F.text == loc.auth.btns['ref_program_participation'],
    StateFilter(user_authorized_fsm.AccountMenu.ref_program),
)
@user_authorized_mw.authorized_only()
@user_authorized_mw.nonblank_subscription_only()
async def account_ref_program_info(message: Message):
    """Send message with information about client's participation in referral program."""
    who_invited_client = await postgres_dbms.get_invited_by_client_info(message.from_user.id)
    who_was_invited_by_client = await postgres_dbms.get_invited_clients_list(message.from_user.id)

    if who_invited_client:
        name, username = who_invited_client
        username_str = await internal_functions.format_none_string(username)
        await message.answer(loc.auth.msgs['invited_by'].format(name, username_str))
    else:
        await message.answer(loc.auth.msgs['invited_by_nobody'])

    if who_was_invited_by_client:
        invited_str = ''
        for idx, (name, username) in enumerate(who_was_invited_by_client):
            username_str = await internal_functions.format_none_string(username)
            invited_str += loc.auth.msgs['who_was_invited_str'].format(idx + 1, name, username_str)

        await message.answer(loc.auth.msgs['who_was_invited'].format(invited_str=invited_str))
    else:
        await message.answer(loc.auth.msgs['nobody_was_invited'])


@router.message(
    F.text == loc.auth.btns['generate_invite'],
    StateFilter(user_authorized_fsm.AccountMenu.ref_program),
)
@user_authorized_mw.authorized_only()
@user_authorized_mw.nonblank_subscription_only()
async def account_ref_program_invite(message: Message):
    """Send message with random invite text from messages.py."""
    ref_promocode = await postgres_dbms.get_referral_promo(message.from_user.id)
    text: str = random.choice(loc.auth.msgs['ref_program_invites_texts']).format(ref_promocode)
    await message.answer(text)


@router.message(
    F.text == loc.auth.btns['show_ref_code'],
    StateFilter(user_authorized_fsm.AccountMenu.ref_program),
)
@user_authorized_mw.authorized_only()
@user_authorized_mw.nonblank_subscription_only()
async def account_ref_program_promocode(message: Message):
    """Send message with client's own referral promocode."""
    ref_promo_phrase: str = await postgres_dbms.get_referral_promo(message.from_user.id)
    await message.answer(loc.auth.msgs['your_ref_code'].format(ref_promo_phrase))


@router.message(
    F.text == loc.auth.btns['used_promos'],
    StateFilter(user_authorized_fsm.AccountMenu.promo),
)
@user_authorized_mw.authorized_only()
@user_authorized_mw.nonblank_subscription_only()
async def account_promo_info(message: Message):
    """Send message with information about entered by client promocodes."""
    ref_promos, global_promos, local_promos = await postgres_dbms.get_client_entered_promos(await postgres_dbms.get_clientID_by_telegramID(message.from_user.id))

    ref_promo_str = ''
    if ref_promos:
        ref_promo_phrase, client_creator_name = ref_promos
        ref_promo_str = loc.auth.msgs['ref_promo_str'].format(ref_promo_phrase, client_creator_name)

    global_promos_str = ''
    if global_promos:
        global_promo_row_str = ''
        for idx, (global_promo_phrase, bonus_time, date_of_entry) in enumerate(global_promos):
            global_promo_row_str += loc.auth.msgs['global_promo_row_str'].format(idx + 1, global_promo_phrase, format_localized_bonus_days(bonus_time), format_localized_datetime(date_of_entry))
        global_promos_str = loc.auth.msgs['global_promos_str'].format(global_promo_row_str=global_promo_row_str)

    local_promos_str = ''
    if local_promos:
        local_promo_row_str = ''
        for idx, (local_promo_phrase, bonus_time, date_of_entry) in enumerate(local_promos):
            local_promo_row_str += loc.auth.msgs['local_promo_row_str'].format(idx + 1, local_promo_phrase, format_localized_bonus_days(bonus_time), format_localized_datetime(date_of_entry))
        local_promos_str = loc.auth.msgs['local_promos_str'].format(local_promo_row_str=local_promo_row_str)

    if ref_promo_str + global_promos_str + local_promos_str == '':
        await message.answer(loc.auth.msgs['no_promo_entered'])
    else:
        await message.answer(ref_promo_str + global_promos_str + local_promos_str)


@router.message(StateFilter(user_authorized_fsm.AccountMenu.promo))
@user_authorized_mw.authorized_only()
@user_authorized_mw.nonblank_subscription_only()
async def account_promo_check(message: Message, state: FSMContext):
    """Check entered promocode is valid, send information about successfuly entered promocode, update subscription period for client.

    If specified promocode is local promocode, it can also change subscription type for client.
    """
    if await postgres_dbms.is_referral_promo(message.text):
        await message.answer(loc.auth.msgs['error_promo_entered_ref_code'])
        return

    client_id = await postgres_dbms.get_clientID_by_telegramID(message.from_user.id)
    global_promo_info = await postgres_dbms.get_global_promo_info(message.text)
    local_promo_info = await postgres_dbms.get_local_promo_info(message.text)

    if global_promo_info:
        global_promo_id, _, _, bonus_time = global_promo_info

        if not await postgres_dbms.is_global_promo_already_entered(client_id, global_promo_id):
            if await postgres_dbms.is_global_promo_valid(global_promo_id):
                if await postgres_dbms.is_global_promo_has_remaining_activations(global_promo_id):
                    await postgres_dbms.insert_client_entered_global_promo(client_id, global_promo_id, bonus_time)
                    await internal_functions.notify_admin_promo_entered(client_id, message.text, 'global')
                    await message.answer(loc.auth.msgs['global_promo_accepted'].format(format_localized_bonus_days(bonus_time)), reply_markup=user_authorized_kb.account)
                    await state.set_state(user_authorized_fsm.AccountMenu.menu)
                else:
                    await message.answer(loc.auth.msgs['error_promo_limit_activations'])
            else:
                await message.answer(loc.auth.msgs['error_promo_expired'])
        else:
            await message.answer(loc.auth.msgs['error_promo_already_entered'])

    elif local_promo_info:
        local_promo_id, _, bonus_time, provided_sub_id = local_promo_info

        if await postgres_dbms.is_local_promo_accessible(client_id, local_promo_id):
            if not await postgres_dbms.is_local_promo_already_entered(client_id, local_promo_id):
                if await postgres_dbms.is_local_promo_valid(local_promo_id):
                    await postgres_dbms.insert_client_entered_local_promo(client_id, local_promo_id, bonus_time)
                    await internal_functions.notify_admin_promo_entered(client_id, message.text, 'local')

                    new_sub_str = ''
                    if provided_sub_id:
                        await postgres_dbms.update_client_subscription(client_id, provided_sub_id)
                        _, title, _, price = await postgres_dbms.get_subscription_info_by_subID(provided_sub_id)
                        new_sub_str = loc.auth.msgs['new_sub_str'].format(title, price)

                    await message.answer(loc.auth.msgs['loсal_promo_accepted'].format(format_localized_bonus_days(bonus_time), new_sub_str=new_sub_str), reply_markup=user_authorized_kb.account)
                    await state.set_state(user_authorized_fsm.AccountMenu.menu)
                else:
                    await message.answer(loc.auth.msgs['error_promo_expired'])
            else:
                await message.answer(loc.auth.msgs['error_promo_already_entered'])
        else:
            await message.answer(loc.auth.msgs['error_promo_inaccessible'])
    else:
        await message.answer(loc.auth.msgs['error_promo_not_exist'])


@router.message(
    F.text == loc.auth.btns['current_configs'],
    StateFilter(user_authorized_fsm.AccountMenu.configs),
)
@user_authorized_mw.authorized_only()
@user_authorized_mw.nonblank_subscription_only()
async def account_configurations_info(message: Message):
    """Send messages with all client's available configurations."""
    configurations_info = await postgres_dbms.get_configurations_info(await postgres_dbms.get_clientID_by_telegramID(message.from_user.id))
    await message.answer(loc.auth.msgs['configs_info'].format(len(configurations_info)))

    for file_type, date_of_receipt, os, name, country, city, bandwidth, ping, available_services, link, config_id, server_name in configurations_info:
        await internal_functions.send_configuration(message.from_user.id, file_type, date_of_receipt, os, name, country, city, bandwidth, ping, available_services, link, config_id, server_name)

    await message.answer(loc.auth.msgs['configs_rules'])


@router.message(
    F.text == loc.auth.btns['return_to_configs_menu'],
    StateFilter(
        None,
        user_authorized_fsm.ConfigMenu.platform,
        user_authorized_fsm.ConfigMenu.os,
        user_authorized_fsm.ConfigMenu.chatgpt,
    ),
)
@user_authorized_mw.authorized_only()
async def account_configurations_submenu_fsm_cancel(message: Message, state: FSMContext):
    """Cancel FSM state for account configurations submenu and return to account configurations menu keyboard."""
    await state.set_state(user_authorized_fsm.AccountMenu.configs)
    await message.answer(loc.auth.msgs['return_to_configs_menu'], reply_markup=user_authorized_kb.config)


@router.message(
    F.text == loc.auth.btns['request_config'],
    StateFilter(user_authorized_fsm.AccountMenu.configs),
)
@user_authorized_mw.authorized_only()
@user_authorized_mw.nonblank_subscription_only()
async def account_configurations_request_fsm_start(message: Message, state: FSMContext):
    """Start FSM for account configurations request menu, show account configurations request keyboard and request client's platform."""
    if not await postgres_dbms.is_subscription_active(message.from_user.id) \
            and not await postgres_dbms.is_subscription_free(message.from_user.id):
        await message.answer(loc.auth.msgs['cant_request_config'])
        return

    client_id = await postgres_dbms.get_clientID_by_telegramID(message.from_user.id)
    configs_number = await postgres_dbms.get_configurations_number(client_id)
    max_configs = await postgres_dbms.get_max_configurations_by_telegramID(message.from_user.id)

    if configs_number >= max_configs:
        await message.answer(loc.auth.msgs['configs_limit_reached'].format(configs_number, max_configs))
        return

    await message.answer(loc.auth.msgs['ask_three_questions'].format(configs_number, max_configs))

    await state.set_state(user_authorized_fsm.ConfigMenu.platform)
    await message.answer("<b>Выберите свою платформу</b>", reply_markup=user_authorized_kb.config_platform)


# LEGACY: pre-Remnawave config distribution handlers, kept for edge cases (Stage 9)
@router.message(
    F.text.in_({"📱 Смартфон", "💻 ПК"}),
    StateFilter(user_authorized_fsm.ConfigMenu.platform),
)
@user_authorized_mw.authorized_only()
async def account_configurations_request_platform(message: Message, state: FSMContext):
    """Change account configurations request FSM state, save client's platform and request user's OS."""
    await state.update_data(platform=message.text)

    if message.text == "📱 Смартфон":
        await message.answer("<b>Укажите операционную систему</b>", reply_markup=user_authorized_kb.config_mobile_os)
    else:
        await message.answer("<b>Укажите операционную систему</b>", reply_markup=user_authorized_kb.config_desktop_os)

    await state.set_state(user_authorized_fsm.ConfigMenu.os)


@router.message(
    F.text.in_({"Android", "IOS (iPhone)", "Windows", "macOS", "Linux"}),
    StateFilter(user_authorized_fsm.ConfigMenu.os),
)
@user_authorized_mw.authorized_only()
async def account_configurations_request_os(message: Message, state: FSMContext):
    """Change account configurations request FSM state, save client's OS and request client's ChatGPT option."""
    await state.update_data(os_name=message.text)

    await state.set_state(user_authorized_fsm.ConfigMenu.chatgpt)
    await message.answer("<b>Используете ли вы ChatGPT?</b>", reply_markup=user_authorized_kb.config_chatgpt)


@router.message(
    F.text.lower() == "что это?",
    StateFilter(user_authorized_fsm.ConfigMenu.chatgpt),
)
@user_authorized_mw.authorized_only()
async def account_configurations_request_chatgpt_info(message: Message):
    """Send message with information about ChatGPT."""
    await message.answer("<b>ChatGPT</b> — нейронная сеть в виде чат-бота, способная отвечать на сложные вопросы и вести осмысленный диалог!")


@router.message(
    F.text.in_({"Использую", "Не использую"}),
    StateFilter(user_authorized_fsm.ConfigMenu.chatgpt),
)
@user_authorized_mw.authorized_only()
async def account_configurations_request_chatgpt(message: Message, state: FSMContext):
    """Change FSM state to account configurations menu, save client's ChatGPT option and send information about client's new configuration request to admin."""
    await state.update_data(chatgpt=message.text)
    data = await state.get_data()

    # send information about client's new configuration request to admin
    await internal_functions.send_configuration_request_to_admin(
        {'fullname': message.from_user.full_name, 'username': message.from_user.username, 'id': message.from_user.id},
        data,
        is_new_client=False,
    )

    await message.answer(loc.auth.msgs['wait_for_admin'], reply_markup=user_authorized_kb.config)
    await message.answer(loc.auth.msgs['i_wanna_sleep'])
    await state.set_state(user_authorized_fsm.AccountMenu.configs)


@router.message(
    F.text == loc.auth.btns['return_to_settings'],
    StateFilter(
        None,
        user_authorized_fsm.SettingsMenu.chatgpt,
        user_authorized_fsm.SettingsMenu.notifications,
    ),
)
@user_authorized_mw.authorized_only()
async def account_settings_submenu_fsm_cancel(message: Message, state: FSMContext):
    """Cancel FSM state for account settings submenu and return to account settings menu keyboard."""
    await state.set_state(user_authorized_fsm.AccountMenu.settings)
    await message.answer(loc.auth.msgs['return_to_settings'], reply_markup=user_authorized_kb.settings)


@router.message(
    F.text == loc.auth.btns['settings_chatgpt_mode'],
    StateFilter(user_authorized_fsm.AccountMenu.settings),
)
@user_authorized_mw.authorized_only()
async def account_settings_chatgpt(message: Message, state: FSMContext):
    """Change account settings FSM state and show dynamic account settings ChatGPT mode keyboard."""
    await state.set_state(user_authorized_fsm.SettingsMenu.chatgpt)
    await message.answer(loc.auth.msgs['go_settings_chatgpt'], reply_markup=await user_authorized_kb.settings_chatgpt(await postgres_dbms.get_clientID_by_telegramID(message.from_user.id)))
    await message.answer(loc.auth.msgs['settings_chatgpt_info'])


@router.message(
    F.text.in_({loc.auth.btns[key] for key in ('chatgpt_on', 'chatgpt_off')}),
    StateFilter(user_authorized_fsm.SettingsMenu.chatgpt),
)
@user_authorized_mw.authorized_only()
async def account_settings_chatgpt_mode(message: Message, state: FSMContext):
    """Turn on/off client's ChatGPT mode for answering unrecognized messages."""
    chatgpt_mode_status: bool = await postgres_dbms.update_chatgpt_mode(await postgres_dbms.get_clientID_by_telegramID(message.from_user.id))

    if await state.get_state() == user_authorized_fsm.SettingsMenu.chatgpt.state:
        reply_keyboard = await user_authorized_kb.settings_chatgpt(await postgres_dbms.get_clientID_by_telegramID(message.from_user.id))
    else:
        reply_keyboard = None

    if chatgpt_mode_status:
        await message.answer(loc.auth.msgs['chatgpt_on'], reply_markup=reply_keyboard)
    else:
        await message.answer(loc.auth.msgs['chatgpt_off'], reply_markup=reply_keyboard)


@router.message(
    F.text == loc.auth.btns['settings_notifications'],
    StateFilter(user_authorized_fsm.AccountMenu.settings),
)
@user_authorized_mw.authorized_only()
async def account_settings_notifications(message: Message, state: FSMContext):
    """Change account settings FSM state and show dynamic account settings notifications keyboard."""
    client_id = await postgres_dbms.get_clientID_by_telegramID(message.from_user.id)
    await state.set_state(user_authorized_fsm.SettingsMenu.notifications)
    await message.answer(loc.auth.msgs['go_settings_notifications'], reply_markup=await user_authorized_kb.settings_notifications(client_id))
    await message.answer(loc.auth.msgs['settings_notifications_info'])


@router.message(
    F.text.in_({loc.auth.btns[key] for key in ('1d_on', '1d_off')}),
    StateFilter(user_authorized_fsm.SettingsMenu.notifications),
)
@user_authorized_mw.authorized_only()
async def account_settings_notifications_1d(message: Message):
    """Turn on/off client's receiving notifications 1 day before subscription expiration."""
    client_id = await postgres_dbms.get_clientID_by_telegramID(message.from_user.id)
    expiration_in_1d_state = await postgres_dbms.update_notifications_1d(client_id)

    if expiration_in_1d_state:
        await message.answer(loc.auth.msgs['1d_on'], reply_markup=await user_authorized_kb.settings_notifications(client_id))
    else:
        await message.answer(loc.auth.msgs['1d_off'], reply_markup=await user_authorized_kb.settings_notifications(client_id))


@router.message(
    F.text.in_({loc.auth.btns[key] for key in ('3d_on', '3d_off')}),
    StateFilter(user_authorized_fsm.SettingsMenu.notifications),
)
@user_authorized_mw.authorized_only()
async def account_settings_notifications_3d(message: Message):
    """Turn on/off client's receiving notifications 3 days before subscription expiration."""
    client_id = await postgres_dbms.get_clientID_by_telegramID(message.from_user.id)
    expiration_in_3d_state = await postgres_dbms.update_notifications_3d(client_id)

    if expiration_in_3d_state:
        await message.answer(loc.auth.msgs['3d_on'], reply_markup=await user_authorized_kb.settings_notifications(client_id))
    else:
        await message.answer(loc.auth.msgs['3d_off'], reply_markup=await user_authorized_kb.settings_notifications(client_id))


@router.message(
    F.text.in_({loc.auth.btns[key] for key in ('7d_on', '7d_off')}),
    StateFilter(user_authorized_fsm.SettingsMenu.notifications),
)
@user_authorized_mw.authorized_only()
async def account_settings_notifications_7d(message: Message):
    """Turn on/off client's receiving notifications 7 days before subscription expiration."""
    client_id = await postgres_dbms.get_clientID_by_telegramID(message.from_user.id)
    expiration_in_7d_state = await postgres_dbms.update_notifications_7d(client_id)

    if expiration_in_7d_state:
        await message.answer(loc.auth.msgs['7d_on'], reply_markup=await user_authorized_kb.settings_notifications(client_id))
    else:
        await message.answer(loc.auth.msgs['7d_off'], reply_markup=await user_authorized_kb.settings_notifications(client_id))


@router.callback_query(F.data.startswith('basic--'))
@user_authorized_mw.authorized_only()
@user_authorized_mw.nonblank_subscription_only()
async def configuration_instruction(call: CallbackQuery):
    """Send message with instruction for configuration specified by inline button."""
    _, configuration_protocol_name, configuration_os = call.data.split('--')

    instruction_text = loc.auth.msgs['basic_instructions'][configuration_protocol_name.lower()][configuration_os.lower()]
    instruction_images_list = loc.auth.tfids['basic_instructions'][configuration_protocol_name.lower()][configuration_os.lower()]

    await internal_functions.reply_media_group_safely(call.message,
                                                      telegram_files_ids_list=instruction_images_list,
                                                      caption=instruction_text)
    await call.answer()


@router.callback_query(F.data.startswith('advanced--'))
@user_authorized_mw.authorized_only()
@user_authorized_mw.nonblank_subscription_only()
async def configuration_advanced_instruction(call: CallbackQuery):
    """Send message with advanced instruction for configuration specified by inline button."""
    _, configuration_protocol_name, configuration_os = call.data.split('--')

    instruction_text = loc.auth.msgs['advanced_instructions'][configuration_protocol_name.lower()][configuration_os.lower()]
    instruction_images_list = loc.auth.tfids['advanced_instructions'][configuration_protocol_name.lower()][configuration_os.lower()]

    await internal_functions.reply_media_group_safely(call.message,
                                                      telegram_files_ids_list=instruction_images_list,
                                                      caption=instruction_text)
    await call.answer()


@router.message(F.text == loc.auth.btns['rules'])
@router.message(Command(commands=['rules']))
@user_authorized_mw.authorized_only()
async def show_project_rules(message: Message):
    """Send message with information about project rules."""
    await internal_functions.send_photo_safely(message.from_user.id,
                                               telegram_file_id=loc.auth.tfids['rules'],
                                               caption=loc.auth.msgs['rules'])


@router.message(Command(commands=['restore_payments']))
@user_authorized_mw.authorized_only()
@throttling_mw.antiflood(rate_limit=4)
async def restore_payments(message: Message):
    """Try to verify client's payments (per whole time) are successful according to YooMoney information."""
    wallet = aiomoney.YooMoneyWallet(settings.payments.yoomoney.token.get_secret_value())
    client_id = await postgres_dbms.get_clientID_by_telegramID(message.from_user.id)
    client_payments_ids = await postgres_dbms.get_paymentIDs(client_id)

    is_payment_found = False
    await bot.send_chat_action(message.from_user.id, ChatAction.TYPING)
    for [payment_id] in client_payments_ids:
        if await postgres_dbms.get_payment_status(payment_id) == False and await wallet.check_payment_on_successful(payment_id):
            months_number = await postgres_dbms.get_payment_months_number(payment_id)
            await postgres_dbms.update_payment_successful(payment_id, client_id, months_number)

            await message.answer(loc.auth.msgs['payment_found'].format(payment_id))

            message_id = await postgres_dbms.get_payment_telegram_message_id(payment_id)
            await _safe_delete_message(message.chat.id, message_id)

            await internal_functions.notify_admin_payment_success(client_id, months_number)
            await internal_functions.check_referral_reward(client_id)
            is_payment_found = True

    if not is_payment_found:
        await message.answer(loc.auth.msgs['cant_find_payments_restore'])


def register_handlers_authorized_client(dp):
    """Attach the `user_authorized` router to the dispatcher."""
    dp.include_router(router)
