from aiogram import Dispatcher
from aiogram.types import Message
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Text
from src.middlewares import user_mw
from src.keyboards import user_unauthorized_kb
from src.states import user_unauthorized_fsm
from src.database import postgesql_db
from src.services import service_functions, localization as loc


@user_mw.unauthorized_only()
async def fsm_cancel(message: Message, state: FSMContext):
    """Cancel FSM state for registration."""
    await state.finish()
    await message.answer(loc.msgs.unauth['return_to_main_menu'], parse_mode='HTML', reply_markup=user_unauthorized_kb.welcome)


@user_mw.unauthorized_only()
async def authorization_fsm_start(message: Message):
    """Start FSM for registration and request user's platform."""
    await message.answer(loc.msgs.unauth['need_define_config'], parse_mode='HTML')
    await message.answer(loc.msgs.unauth['ask_four_questions'], parse_mode='HTML')
    await message.answer(loc.msgs.unauth['choose_your_platform'], parse_mode='HTML', reply_markup=user_unauthorized_kb.reg_platform)
    await user_unauthorized_fsm.RegistrationMenu.platform.set()


@user_mw.unauthorized_only()
async def authorization_take_platform(message: Message, state: FSMContext):
    """Change FSM state, save user's platform and request user's OS."""
    async with state.proxy() as data:
        data['platform'] = message.text

    # if user chooses smartphone option
    if message.text == loc.btns.unauth['smartphone']:

        await message.answer(loc.msgs.unauth['choose_your_os'], parse_mode='HTML', reply_markup=user_unauthorized_kb.reg_mobile_os)

    # if user chooses pc option
    else:
        await message.answer(loc.msgs.unauth['choose_your_os'], parse_mode='HTML', reply_markup=user_unauthorized_kb.reg_desktop_os)

    await state.set_state(user_unauthorized_fsm.RegistrationMenu.os)


@user_mw.unauthorized_only()
async def authorization_take_os(message: Message, state: FSMContext):
    """Change FSM state, save user's OS and request user's ChatGPT option."""
    async with state.proxy() as data:
        data['os_name'] = message.text

    await message.answer(loc.msgs.unauth['choose_chatgpt_option'], parse_mode='HTML', reply_markup=user_unauthorized_kb.reg_chatgpt)
    await state.set_state(user_unauthorized_fsm.RegistrationMenu.chatgpt)


@user_mw.unauthorized_only()
async def authorization_show_info_chatgpt(message: Message):
    """Send message with information about ChatGPT."""
    await message.answer(loc.msgs.unauth['chatgpt_info'], parse_mode='HTML')


@user_mw.unauthorized_only()
async def authorization_take_chatgpt(message: Message, state: FSMContext):
    """Change FSM state, save user's ChatGPT option and request user's referral promo."""
    async with state.proxy() as data:
        data['chatgpt'] = message.text

    await message.answer(loc.msgs.unauth['enter_ref_promo'], parse_mode='HTML', reply_markup=user_unauthorized_kb.reg_ref_promo)
    await state.set_state(user_unauthorized_fsm.RegistrationMenu.promo)


@user_mw.unauthorized_only()
async def authorization_promo_yes(message: Message, state: FSMContext):
    """Check entered referral promocode, notify old client about new client used his referral promocode, complete authorization."""
    # if referral promocode exists in system
    if await postgesql_db.is_referral_promo(message.text):
        async with state.proxy() as data:
            data['promo'] = message.text

        # send information to old client that new client joined project by his referral promocode
        _, client_creator_id, provided_sub_id, _, bonus_time_parsed = await postgesql_db.get_refferal_promo_info_by_phrase(message.text)
        await service_functions.notify_client_new_referal(client_creator_id, message.from_user.first_name, message.from_user.username)

        # send information about promocode bonus time to new client
        client_creator_name, *_ = await postgesql_db.get_client_info_by_clientID(client_creator_id)
        await message.answer(loc.msgs.unauth['ref_promo_accepted'].format(client_creator_name, bonus_time_parsed), parse_mode='HTML')

        # send information about subscription available by referral promocode
        _, title, _, price = await postgesql_db.get_subscription_info_by_subID(provided_sub_id)
        await message.answer(loc.msgs.unauth['sub_info'].format(title, price), parse_mode='HTML')

        # complete authorization
        await service_functions.authorization_complete(message, state)

    # if referral promocode wasn't recognized
    else:
        await message.answer(loc.msgs.unauth['invalid_promo'])
        async with state.proxy() as data:
            data['promo'] = None


@user_mw.unauthorized_only()
async def authorization_promo_no(message: Message, state: FSMContext):
    """Complete authorization without referral promocode."""
    async with state.proxy() as data:
        data['promo'] = None

    await service_functions.authorization_complete(message, state)
    await message.answer(loc.msgs.unauth['need_renew_sub'], parse_mode='HTML')


def register_handlers_unauthorized_client(dp: Dispatcher):
    dp.register_message_handler(fsm_cancel,
                                Text(equals=loc.btns.unauth['cancel'],
                                     ignore_case=True),
                                state=[None,
                                       user_unauthorized_fsm.RegistrationMenu.platform,
                                       user_unauthorized_fsm.RegistrationMenu.os,
                                       user_unauthorized_fsm.RegistrationMenu.chatgpt,
                                       user_unauthorized_fsm.RegistrationMenu.promo])

    dp.register_message_handler(authorization_fsm_start,
                                Text(equals=loc.btns.unauth['join'],
                                     ignore_case=True))
    
    dp.register_message_handler(authorization_take_platform,
                                Text(equals=[loc.btns.unauth['smartphone'],
                                             loc.btns.unauth['pc']]),
                                state=user_unauthorized_fsm.RegistrationMenu.platform)
    
    dp.register_message_handler(authorization_take_os,
                                Text(equals=[loc.btns.unauth['android'],
                                             loc.btns.unauth['ios'],
                                             loc.btns.unauth['windows'],
                                             loc.btns.unauth['macos'],
                                             loc.btns.unauth['linux']]),
                                state=user_unauthorized_fsm.RegistrationMenu.os)
    
    dp.register_message_handler(authorization_show_info_chatgpt,
                                Text(equals=loc.btns.unauth['what_is_chatgpt'],
                                     ignore_case=True),
                                state=user_unauthorized_fsm.RegistrationMenu.chatgpt)
    
    dp.register_message_handler(authorization_take_chatgpt,
                                Text(equals=[loc.btns.unauth['use_chatgpt'],
                                             loc.btns.unauth['dont_use_chatgpt']]),
                                state=user_unauthorized_fsm.RegistrationMenu.chatgpt)
    
    dp.register_message_handler(authorization_promo_no,
                                Text(equals=loc.btns.unauth['no_promo']),
                                state=user_unauthorized_fsm.RegistrationMenu.promo)
    
    dp.register_message_handler(authorization_promo_yes,
                                state=user_unauthorized_fsm.RegistrationMenu.promo)
