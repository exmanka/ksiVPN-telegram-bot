from aiogram.types import Message
from aiogram.dispatcher.middlewares import BaseMiddleware
from aiogram.dispatcher.handler import CancelHandler, current_handler
from src.database import postgres_dbms
from src.services import localization as loc


def authorized_only():
    """Decorator for handlers available only for authorized clients."""
    def wrapper(func):
        setattr(func, 'authorized_only', True)

        return func
    return wrapper


def nonblank_subscription_only():
    """Decorator for handlers available only for clients with nonblank subscription."""
    def wrapper(func):
        setattr(func, 'nonblank_only', True)

        return func
    return wrapper


class CheckAuthorized(BaseMiddleware):
    """Custom class for aiogram middlware for checking authorized-only clients handlers."""
    async def on_process_message(self, message: Message, _: dict):
        """Check authorized-only clients handler on message process."""
        # if current event was caught by handler
        if handler := current_handler.get():

            # if current handler has attribute 'authorized_only' and client isn't registered
            if getattr(handler, 'authorized_only', False) and not await postgres_dbms.is_user_registered(message.from_user.id):
                await message.answer(loc.mw.msgs['authorized_only'])
                raise CancelHandler()

            # if current handler has attribute 'nonblank_only' and client has blank subscription
            if getattr(handler, 'nonblank_only', False) and await postgres_dbms.is_subscription_blank(message.from_user.id):
                await message.answer(loc.mw.msgs['nonblank_only'])
                raise CancelHandler()
