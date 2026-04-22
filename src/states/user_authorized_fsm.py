from aiogram.fsm.state import State, StatesGroup


class AccountMenu(StatesGroup):
    """FSM states for account menu."""
    menu = State()
    promo = State()
    ref_program = State()
    settings = State()


class PaymentMenu(StatesGroup):
    """FSM states for payment menu."""
    menu = State()
    months_1 = State()
    months_3 = State()
    months_12 = State()
    verification = State()


class SettingsMenu(StatesGroup):
    """FSM states for settings menu."""
    chatgpt = State()
    notifications = State()
