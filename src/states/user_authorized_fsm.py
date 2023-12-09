from aiogram.dispatcher.filters.state import State, StatesGroup


class AccountMenu(StatesGroup):
    menu = State()
    promo = State()
    ref_program = State()
    configs = State()
    settings = State()


class PaymentMenu(StatesGroup):
    menu = State()
    months_1 = State()
    months_3 = State()
    months_12 = State()
    verification = State()


class ConfigMenu(StatesGroup):
    platform = State()
    os = State()
    chatgpt = State()


class SettingsMenu(StatesGroup):
    chatgpt = State()
    notifications = State()