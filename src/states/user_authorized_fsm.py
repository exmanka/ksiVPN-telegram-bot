from aiogram.dispatcher.filters.state import State, StatesGroup


class AccountMenu(StatesGroup):
    menu = State()
    promo = State()
    ref_program = State()
    configs = State()


class PaymentMenu(StatesGroup):
    menu = State()
    months_1 = State()
    months_3 = State()
    months_12 = State()
    months_n = State()


class ConfigMenu(StatesGroup):
    platform = State()
    os = State()
    chatgpt = State()