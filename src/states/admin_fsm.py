from aiogram.fsm.state import State, StatesGroup


class SendConfig(StatesGroup):
    """FSM state for configuration sending."""
    ready = State()


class SendMessage(StatesGroup):
    """FSM states for sending messages to clients via bot."""
    everyone_decision = State()
    selected_list = State()
    selected_decision = State()
