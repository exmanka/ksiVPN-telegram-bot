from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from src.middlewares import user_unauthorized_mw
from src.keyboards import user_unauthorized_kb
from src.states import user_unauthorized_fsm
from src.database import postgres_dbms
from src.services import internal_functions, localization as loc


router = Router(name="user_unauthorized")

_cancel_states = [
    None,
    user_unauthorized_fsm.RegistrationMenu.platform,
    user_unauthorized_fsm.RegistrationMenu.os,
    user_unauthorized_fsm.RegistrationMenu.chatgpt,
    user_unauthorized_fsm.RegistrationMenu.promo,
]


@router.message(
    F.text.lower() == loc.unauth.btns['cancel'].lower(),
    StateFilter(*_cancel_states),
)
@user_unauthorized_mw.unauthorized_only()
async def fsm_cancel(message: Message, state: FSMContext):
    """Cancel FSM state for registration."""
    await state.clear()
    await message.answer(loc.unauth.msgs['return_to_main_menu'], reply_markup=user_unauthorized_kb.welcome)


@router.message(F.text.lower() == loc.unauth.btns['join'].lower())
@user_unauthorized_mw.unauthorized_only()
async def authorization_fsm_start(message: Message, state: FSMContext):
    """Start FSM for registration and request user's platform."""
    await message.answer(loc.unauth.msgs['need_define_config'])
    await message.answer(loc.unauth.msgs['ask_four_questions'])
    await message.answer(loc.unauth.msgs['choose_your_platform'], reply_markup=user_unauthorized_kb.reg_platform)
    await state.set_state(user_unauthorized_fsm.RegistrationMenu.platform)


@router.message(
    F.text.in_({loc.unauth.btns[key] for key in ('smartphone', 'pc')}),
    StateFilter(user_unauthorized_fsm.RegistrationMenu.platform),
)
@user_unauthorized_mw.unauthorized_only()
async def authorization_take_platform(message: Message, state: FSMContext):
    """Change FSM state, save user's platform and request user's OS."""
    await state.update_data(platform=message.text)

    # if user chooses smartphone option
    if message.text == loc.unauth.btns['smartphone']:
        await message.answer(loc.unauth.msgs['choose_your_os'], reply_markup=user_unauthorized_kb.reg_mobile_os)

    # if user chooses pc option
    else:
        await message.answer(loc.unauth.msgs['choose_your_os'], reply_markup=user_unauthorized_kb.reg_desktop_os)

    await state.set_state(user_unauthorized_fsm.RegistrationMenu.os)


@router.message(
    F.text.in_({loc.unauth.btns[key] for key in ('android', 'ios', 'windows', 'macos', 'linux')}),
    StateFilter(user_unauthorized_fsm.RegistrationMenu.os),
)
@user_unauthorized_mw.unauthorized_only()
async def authorization_take_os(message: Message, state: FSMContext):
    """Change FSM state, save user's OS and request user's ChatGPT option."""
    await state.update_data(os_name=message.text)

    await message.answer(loc.unauth.msgs['choose_chatgpt_option'], reply_markup=user_unauthorized_kb.reg_chatgpt)
    await state.set_state(user_unauthorized_fsm.RegistrationMenu.chatgpt)


@router.message(
    F.text.lower() == loc.unauth.btns['what_is_chatgpt'].lower(),
    StateFilter(user_unauthorized_fsm.RegistrationMenu.chatgpt),
)
@user_unauthorized_mw.unauthorized_only()
async def authorization_show_info_chatgpt(message: Message):
    """Send message with information about ChatGPT."""
    await message.answer(loc.unauth.msgs['chatgpt_info'])


@router.message(
    F.text.in_({loc.unauth.btns[key] for key in ('use_chatgpt', 'dont_use_chatgpt')}),
    StateFilter(user_unauthorized_fsm.RegistrationMenu.chatgpt),
)
@user_unauthorized_mw.unauthorized_only()
async def authorization_take_chatgpt(message: Message, state: FSMContext):
    """Change FSM state, save user's ChatGPT option and request user's referral promo."""
    await state.update_data(chatgpt=message.text)

    await message.answer(loc.unauth.msgs['enter_ref_promo'], reply_markup=user_unauthorized_kb.reg_ref_promo)
    await state.set_state(user_unauthorized_fsm.RegistrationMenu.promo)


@router.message(
    F.text == loc.unauth.btns['no_promo'],
    StateFilter(user_unauthorized_fsm.RegistrationMenu.promo),
)
@user_unauthorized_mw.unauthorized_only()
async def authorization_promo_no(message: Message, state: FSMContext):
    """Complete authorization without referral promocode."""
    await state.update_data(promo=None)

    await internal_functions.authorization_complete(message, state)
    await message.answer(loc.unauth.msgs['need_renew_sub'])


@router.message(StateFilter(user_unauthorized_fsm.RegistrationMenu.promo))
@user_unauthorized_mw.unauthorized_only()
async def authorization_promo_yes(message: Message, state: FSMContext):
    """Check entered referral promocode, notify old client about new client used his referral promocode, complete authorization."""
    # if referral promocode exists in system
    if await postgres_dbms.is_referral_promo(message.text):
        await state.update_data(promo=message.text)

        # send information to old client that new client joined project by his referral promocode
        _, client_creator_id, provided_sub_id, _, bonus_time_parsed = await postgres_dbms.get_refferal_promo_info_by_phrase(message.text)
        await internal_functions.notify_client_new_referal(client_creator_id, message.from_user.first_name, message.from_user.username)

        # send information about promocode bonus time to new client
        client_creator_name, *_ = await postgres_dbms.get_client_info_by_clientID(client_creator_id)
        await message.answer(loc.unauth.msgs['ref_promo_accepted'].format(client_creator_name, bonus_time_parsed))

        # send information about subscription available by referral promocode
        _, title, _, price = await postgres_dbms.get_subscription_info_by_subID(provided_sub_id)
        await message.answer(loc.unauth.msgs['sub_info'].format(title, price))

        # complete authorization
        await internal_functions.authorization_complete(message, state)

    # if referral promocode wasn't recognized
    else:
        await message.answer(loc.unauth.msgs['invalid_promo'])
        await state.update_data(promo=None)


def register_handlers_unauthorized_client(dp):
    """Attach the `user_unauthorized` router to the dispatcher."""
    dp.include_router(router)
