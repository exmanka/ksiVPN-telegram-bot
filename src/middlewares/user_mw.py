from aiogram.types import Message
from aiogram.dispatcher.middlewares import BaseMiddleware
from aiogram.dispatcher.handler import CancelHandler, current_handler
from src.database import postgres_dbms


def unauthorized_only():
    """Decorator for handlers available only for unauthorized users."""
    def wrapper(func):
        setattr(func, 'unauthorized_only', True)

        return func
    return wrapper


def authorized_only():
    """Decorator for handlers available only for authorized clients."""
    def wrapper(func):
        setattr(func, 'authorized_only', True)

        return func
    return wrapper


class CheckAuthorized(BaseMiddleware):
    """Custom class for aiogram middlware for checking authorized-only clients handlers."""
    async def on_process_message(self, message: Message, _: dict):
        """Check authorized-only clients handler on message process."""
        # if current event was caught by handler
        if handler := current_handler.get():
            only_for_unauthorized_users = getattr(handler, 'unauthorized_only', False)

            # if current handler has attribute 'unauthorized_only' and client is already registered
            if only_for_unauthorized_users and await postgres_dbms.is_user_registered(message.from_user.id):
                await message.answer('Вы уже зарегистрировались!')
                raise CancelHandler()

            only_for_authorized_users = getattr(handler, 'authorized_only', False)

            # if current handler has attribute 'authorized_only' and client isn't registered
            if only_for_authorized_users and not await postgres_dbms.is_user_registered(message.from_user.id):
                await message.answer('Ууупс! Эта функция доступна только зарегистрированным пользователям!')
                raise CancelHandler()
