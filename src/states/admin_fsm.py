from aiogram.dispatcher.filters.state import State, StatesGroup


class SendConfig(StatesGroup):
    """FSM state for configuration sending."""
    ready = State()


class UserInfo(StatesGroup):
    """FSM state for getting user information."""
    ready = State()


class ConfigInfo(StatesGroup):
    """FSM state for getting configuration information."""
    ready = State()


class SendMessage(StatesGroup):
    """FSM states for sending messages to clients via bot."""
    everyone_decision = State()
    selected_list = State()
    selected_decision = State()
