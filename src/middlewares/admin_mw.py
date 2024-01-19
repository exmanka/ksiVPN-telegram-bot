from aiogram.types import Message
from aiogram.dispatcher.handler import CancelHandler, current_handler
from aiogram.dispatcher.middlewares import BaseMiddleware
from src.services import localization as loc
from bot_init import ADMIN_ID


def admin_only():
    """Decorator for handlers available only for administrator."""
    def wrapper(func):
        setattr(func, 'admin_only', True)

        return func
    return wrapper


class CheckAdmin(BaseMiddleware):
    """Custom class for aiogram middlware for checking administrator-only handlers."""
    async def on_process_message(self, message: Message, _: dict):
        """Check administrator-only handler on message process."""
        # if current event was caught by handler
        if handler := current_handler.get():
            only_for_admin = getattr(handler, 'admin_only', False)

            # if current handler has attribute 'admin_only' and telegram_id of user isn't admin's telegram_id
            if only_for_admin and not message.from_user.id == ADMIN_ID:
                await message.answer(loc.mw.msgs['admin_only'])
                raise CancelHandler()
