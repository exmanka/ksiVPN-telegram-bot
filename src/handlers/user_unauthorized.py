from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from src.middlewares import user_unauthorized_mw
from src.keyboards import user_unauthorized_kb
from src.states import user_unauthorized_fsm
from src.database import postgres_dbms
from src.services import internal_functions, localization as loc
from src.services.date_formatting import format_localized_bonus_days


router = Router(name="user_unauthorized")

_cancel_states = [
    None,
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


@router.message(
    F.text.lower() == loc.unauth.btns['skip_promo'].lower(),
    StateFilter(user_unauthorized_fsm.RegistrationMenu.promo),
)
@user_unauthorized_mw.unauthorized_only()
async def authorization_promo_no(message: Message, state: FSMContext):
    """Complete authorization without referral promocode."""
    await state.update_data(promo=None)
    await internal_functions.authorization_complete(message.from_user, state)


@router.message(StateFilter(user_unauthorized_fsm.RegistrationMenu.promo))
@user_unauthorized_mw.unauthorized_only()
async def authorization_promo_yes(message: Message, state: FSMContext):
    """Check entered referral promocode and complete authorization."""
    if await postgres_dbms.is_referral_promo(message.text):
        await state.update_data(promo=message.text)

        _, client_creator_id, provided_sub_id, bonus_time = await postgres_dbms.get_refferal_promo_info_by_phrase(message.text)
        await internal_functions.notify_client_new_referal(client_creator_id, message.from_user.first_name, message.from_user.username)

        client_creator_name, *_ = await postgres_dbms.get_client_info_by_clientID(client_creator_id)
        await message.answer(loc.unauth.msgs['ref_promo_accepted'].format(client_creator_name, format_localized_bonus_days(bonus_time)))

        _, title, _, price = await postgres_dbms.get_subscription_info_by_subID(provided_sub_id)
        await message.answer(loc.unauth.msgs['sub_info'].format(title, price))

        await internal_functions.authorization_complete(message.from_user, state)

    else:
        await message.answer(loc.unauth.msgs['invalid_promo'])
        await state.update_data(promo=None)


@router.message(F.text.lower() == loc.unauth.btns['join'].lower())
@user_unauthorized_mw.unauthorized_only()
async def authorization_fsm_start(message: Message, state: FSMContext):
    """Start FSM for registration and request referral promo code."""
    await message.answer(loc.unauth.msgs['enter_promo_or_skip'], reply_markup=user_unauthorized_kb.reg_promo)
    await state.set_state(user_unauthorized_fsm.RegistrationMenu.promo)


def register_handlers_unauthorized_client(dp):
    """Attach the `user_unauthorized` router to the dispatcher."""
    dp.include_router(router)
