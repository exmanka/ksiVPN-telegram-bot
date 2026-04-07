from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import Message
from src.database import postgres_dbms
from src.services import localization as loc


def unauthorized_only():
    """Decorator for handlers available only for unauthorized users."""
    def wrapper(func):
        setattr(func, 'unauthorized_only', True)
        return func
    return wrapper


class CheckUnauthorized(BaseMiddleware):
    """Custom aiogram middleware for checking unauthorized-only handlers."""

    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any],
    ) -> Any:
        handler_obj = data.get("handler")
        if handler_obj is not None:
            callback = getattr(handler_obj, "callback", None)
            if getattr(callback, "unauthorized_only", False) and await postgres_dbms.is_user_registered(event.from_user.id):
                await event.answer(loc.mw.msgs['unauthorized_only'])
                return None
        return await handler(event, data)
