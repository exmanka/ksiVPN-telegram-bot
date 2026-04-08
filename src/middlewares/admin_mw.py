from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import Message
from src.services import localization as loc
from src.config import settings


def admin_only():
    """Decorator for handlers available only for administrator."""
    def wrapper(func):
        setattr(func, 'admin_only', True)
        return func
    return wrapper


class CheckAdmin(BaseMiddleware):
    """Custom aiogram middleware for checking administrator-only handlers."""

    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any],
    ) -> Any:
        handler_obj = data.get("handler")
        if handler_obj is not None:
            callback = getattr(handler_obj, "callback", None)
            if getattr(callback, "admin_only", False) and event.from_user.id != settings.bot.admin_id:
                await event.answer(loc.mw.msgs['admin_only'])
                return None
        return await handler(event, data)
