from aiogram.types import Message
from aiogram.dispatcher.middlewares import BaseMiddleware
from aiogram.dispatcher.handler import CancelHandler, current_handler
from aiogram.utils.exceptions import Throttled
from bot_init import dp


def antiflood(rate_limit: int):
    """Decorator for handlers with antiflood."""
    def wrapper(func):
        setattr(func, 'antiflood', True)
        setattr(func, 'rate_limit', rate_limit)

        return func
    return wrapper


class Throttling(BaseMiddleware):
    """Custom class for aiogram middlware for antiflood."""
    async def on_process_message(self, message: Message):
        """Check throttling on message process."""
        # if current event was caught by handler and current handler has attribute 'antiflood'
        if handler := current_handler.get() and getattr(handler, 'antiflood', False):
            try:
                rate_limit = getattr(handler, 'rate_limit', 2)
                await dp.throttle(key='antiflood_message', rate=rate_limit)

            # if message is throttled
            except Throttled as _t:
                await message.answer('Пожалуйста, не спамьте оплатами!')
                raise CancelHandler()
