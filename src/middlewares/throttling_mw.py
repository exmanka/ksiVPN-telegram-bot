import time
from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import Message
from src.services import localization as loc


def antiflood(rate_limit: int):
    """Decorator for handlers with antiflood."""
    def wrapper(func):
        setattr(func, 'antiflood', True)
        setattr(func, 'rate_limit', rate_limit)
        return func
    return wrapper


class Throttling(BaseMiddleware):
    """Custom aiogram middleware for antiflood.

    Simple in-memory per-user rate limiter. State is lost on bot restart, which is
    acceptable for antiflood semantics.
    """

    def __init__(self) -> None:
        self._last_call: Dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any],
    ) -> Any:
        handler_obj = data.get("handler")
        if handler_obj is not None:
            callback = getattr(handler_obj, "callback", None)
            if getattr(callback, "antiflood", False):
                rate_limit = getattr(callback, "rate_limit", 2)
                user_id = event.from_user.id
                now = time.monotonic()
                last = self._last_call.get(user_id, 0.0)
                if now - last < rate_limit:
                    await event.answer(loc.mw.msgs['antiflood'])
                    return None
                self._last_call[user_id] = now
        return await handler(event, data)
