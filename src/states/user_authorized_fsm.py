from aiogram.fsm.state import State, StatesGroup


class AccountMenu(StatesGroup):
    """FSM states for account menu."""
    menu = State()
    promo = State()
    ref_program = State()
    settings = State()


class PaymentMenu(StatesGroup):
    """FSM states for payment menu.

    Flow:
        menu -> (user picks 30/90/365) -> provider_selection
        provider_selection -> (user picks YooKassa/YooMoney) -> verification
        verification -> (webhook arrives OR user taps «Проверить») -> menu
        any of these -> (user taps cancel) -> menu
    """
    menu = State()
    provider_selection = State()
    verification = State()


class SettingsMenu(StatesGroup):
    """FSM states for settings menu."""
    chatgpt = State()
    notifications = State()
