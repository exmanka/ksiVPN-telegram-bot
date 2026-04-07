from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import Message
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
    """Custom aiogram middleware for checking authorized-only client handlers."""

    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any],
    ) -> Any:
        handler_obj = data.get("handler")
        if handler_obj is not None:
            callback = getattr(handler_obj, "callback", None)

            if getattr(callback, "authorized_only", False) and not await postgres_dbms.is_user_registered(event.from_user.id):
                await event.answer(loc.mw.msgs['authorized_only'])
                return None

            if getattr(callback, "nonblank_only", False) and await postgres_dbms.is_subscription_blank(event.from_user.id):
                await event.answer(loc.mw.msgs['nonblank_only'])
                return None

        return await handler(event, data)
