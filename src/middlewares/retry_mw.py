"""Session-level request middleware — retries outgoing Telegram API calls.

NOTE ON LAYER: unlike the other middlewares in this package (``admin_mw``,
``throttling_mw``, ``user_authorized_mw``, ``user_unauthorized_mw``), which are
aiogram **dispatcher** middlewares (``BaseMiddleware``) attached in ``main.py``
via ``dp.*.middleware(...)`` and run on **incoming** updates, this is a
**session request** middleware (``BaseRequestMiddleware``). It is attached to the
Bot's ``AiohttpSession`` in ``src/bot.py:build_bot`` and runs on **outgoing**
API calls. Do NOT register it via ``dp.*.middleware`` — that would do nothing.
"""

import asyncio
import logging

from aiogram import Bot
from aiogram.client.session.middlewares.base import (
    BaseRequestMiddleware,
    NextRequestMiddlewareType,
)
from aiogram.exceptions import TelegramNetworkError, TelegramRetryAfter
from aiogram.methods.base import Response, TelegramMethod, TelegramType
from aiohttp_socks import ProxyConnectionError, ProxyError, ProxyTimeoutError


logger = logging.getLogger(__name__)


# Transient connection failures worth retrying. Proxy errors are plain
# ``Exception`` subclasses (see aiohttp_socks._errors) — NOT aiohttp.ClientError
# — so aiogram's AiohttpSession does not wrap them into TelegramNetworkError and
# they must be listed explicitly. asyncio.TimeoutError is included as a belt-and
# -suspenders (aiogram normally wraps it, but raw timeouts can slip through some
# proxy code paths).
_RETRYABLE_NETWORK_ERRORS = (
    TelegramNetworkError,
    ProxyError,
    ProxyConnectionError,
    ProxyTimeoutError,
    asyncio.TimeoutError,
)


class RetryRequestMiddleware(BaseRequestMiddleware):
    """Retry outgoing Telegram API calls on transient network/proxy failures.

    aiogram retries only the ``getUpdates`` polling loop; individual method
    calls made inside handlers (``callback.answer``, ``send_message``, ...) get
    a single attempt. Behind an unstable SOCKS5 proxy that surfaces as
    ``ProxyError: Network unreachable`` bubbling up to the ``aiogram.event``
    logger and the user action silently failing. This session-level request
    middleware wraps every outgoing request with a bounded linear-backoff retry.

    ``TelegramRetryAfter`` (flood control, HTTP 429) is honored separately by
    sleeping the server-mandated ``retry_after`` instead of the local backoff.
    Non-retryable API errors (TelegramBadRequest, TelegramForbiddenError, ...)
    are not caught here and propagate immediately.
    """

    def __init__(self, retries: int = 3, retry_delay: float = 0.5) -> None:
        # ``retries`` = total attempts (1 initial + retries-1 retries). Clamped
        # to >= 1 so a call is always attempted at least once.
        self.retries = max(1, retries)
        self.retry_delay = retry_delay

    async def __call__(
        self,
        make_request: NextRequestMiddlewareType[TelegramType],
        bot: Bot,
        method: TelegramMethod[TelegramType],
    ) -> Response[TelegramType]:
        method_name = type(method).__name__
        for attempt in range(1, self.retries + 1):
            try:
                return await make_request(bot, method)
            except TelegramRetryAfter as e:
                # Flood control: the server dictates the wait. Still bounded by
                # the attempt budget to avoid unbounded stalls.
                if attempt == self.retries:
                    raise
                logger.warning(
                    "Flood control on %s, retrying after %ss (attempt %s/%s)",
                    method_name, e.retry_after, attempt, self.retries,
                )
                await asyncio.sleep(e.retry_after)
            except _RETRYABLE_NETWORK_ERRORS as e:
                if attempt == self.retries:
                    raise
                delay = self.retry_delay * attempt
                logger.warning(
                    "Network error on %s (%s), retrying in %ss (attempt %s/%s)",
                    method_name, type(e).__name__, delay, attempt, self.retries,
                )
                await asyncio.sleep(delay)
        # Unreachable: the loop either returns or re-raises on the final attempt.
        raise RuntimeError("retry loop exited without returning")  # pragma: no cover
