from aiogram.types import Message
from aiogram.dispatcher.middlewares import BaseMiddleware
from aiogram.dispatcher.handler import CancelHandler, current_handler
from src.database import postgres_dbms
from src.services import localization as loc


def unauthorized_only():
    """Decorator for handlers available only for unauthorized users."""
    def wrapper(func):
        setattr(func, 'unauthorized_only', True)

        return func
    return wrapper


class CheckUnauthorized(BaseMiddleware):
    """Custom class for aiogram middlware for checking unauthorized-only clients handlers."""
    async def on_process_message(self, message: Message, _: dict):
        """Check authorized-only clients handler on message process."""
        # if current event was caught by handler
        if handler := current_handler.get():
            
            # if current handler has attribute 'unauthorized_only' and client is already registered
            only_for_unauthorized_users = getattr(handler, 'unauthorized_only', False)
            if only_for_unauthorized_users and await postgres_dbms.is_user_registered(message.from_user.id):
                await message.answer(loc.mw.msgs['unauthorized_only'])
                raise CancelHandler()
