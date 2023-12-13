from aiogram.dispatcher.filters.state import State, StatesGroup


class FSMSendConfig(StatesGroup):
    ready = State()

class FSMUserInfo(StatesGroup):
    ready = State()

class FSMConfigInfo(StatesGroup):
    ready = State()

class FSMSendMessage(StatesGroup):
    everyone_decision = State()
    selected_list = State()
    selected_decision = State()