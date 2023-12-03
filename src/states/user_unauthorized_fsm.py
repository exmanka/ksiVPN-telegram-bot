from aiogram.dispatcher.filters.state import State, StatesGroup


class RegistrationFSM(StatesGroup):
    platform = State()
    os = State()
    chatgpt = State()
    promo = State()
