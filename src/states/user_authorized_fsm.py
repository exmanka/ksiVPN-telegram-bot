from aiogram.dispatcher.filters.state import State, StatesGroup


class AccountMenu(StatesGroup):
    account_menu = State()
    account_promo = State()
    account_ref_program = State()