from aiogram.dispatcher.filters.state import State, StatesGroup


class FSMAdmin(StatesGroup):
    photo = State()
    name = State()
    description = State()
    price = State()

class FSMUserInfo(StatesGroup):
    ready_to_answer = State()

class FSMConfigInfo(StatesGroup):
    ready_to_answer = State()