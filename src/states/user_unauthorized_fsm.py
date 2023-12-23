from aiogram.dispatcher.filters.state import State, StatesGroup


class RegistrationMenu(StatesGroup):
    """FSM states for registration of users."""
    platform = State()
    os = State()
    chatgpt = State()
    promo = State()
