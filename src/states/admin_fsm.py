from aiogram.dispatcher.filters.state import State, StatesGroup


class FSMAdmin(StatesGroup):
    photo = State()
    name = State()
    description = State()
    price = State()

class FSMUserInfo(StatesGroup):
    ready = State()

class FSMConfigInfo(StatesGroup):
    ready = State()

class FSMSendMessage(StatesGroup):
    echo = State()
    decision_to_send = State()