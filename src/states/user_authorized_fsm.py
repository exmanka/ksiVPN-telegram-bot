from aiogram.dispatcher.filters.state import State, StatesGroup


class AccountMenu(StatesGroup):
    """FSM states for account menu."""
    menu = State()
    promo = State()
    ref_program = State()
    configs = State()
    settings = State()


class PaymentMenu(StatesGroup):
    """FSM states for payment menu."""
    menu = State()
    months_1 = State()
    months_3 = State()
    months_12 = State()
    verification = State()


class ConfigMenu(StatesGroup):
    """FSM states for configuration request menu."""
    platform = State()
    os = State()
    chatgpt = State()


class SettingsMenu(StatesGroup):
    """FSM states for settings menu."""
    chatgpt = State()
    notifications = State()
