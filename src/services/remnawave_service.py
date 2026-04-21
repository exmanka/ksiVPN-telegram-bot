"""Integration layer between the bot and Remnawave Panel.

All public functions raise RemnawaveError on panel-side failures so callers
can decide whether to retry, notify the admin, or silently skip.
"""
import asyncio
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

import httpx
from remnawave.models import CreateUserRequestDto, UpdateUserRequestDto

from src.database import postgres_dbms
from src.services.remnawave_client import remnawave_sdk


logger = logging.getLogger(__name__)

_USERNAME_RE = re.compile(r'^[a-zA-Z0-9_-]{3,36}$')


class RemnawaveError(Exception):
    """Raised when a Remnawave Panel API call fails."""


# Delays between retry attempts (seconds). Length = number of retries.
# 2 retries → 3 total attempts, max wait ≈ 3 s before raising RemnawaveError.
_RETRY_DELAYS: tuple[float, ...] = (1.0, 2.0)


async def _call_with_http_retry(coro_factory: Callable[[], Awaitable[Any]], *, label: str) -> Any:
    """Execute coro_factory(), retrying on httpx.HTTPError with exponential backoff.

    Only httpx.HTTPError (network / 5xx) is retried — other exceptions indicate
    a logic error (bad DTO, SDK bug) that a retry won't fix.

    :param coro_factory: zero-arg callable returning the coroutine to await
    :param label: human-readable name for log messages
    :raises RemnawaveError: when all attempts are exhausted
    """
    last_exc: httpx.HTTPError | None = None
    total_attempts = len(_RETRY_DELAYS) + 1

    for attempt in range(1, total_attempts + 1):
        try:
            return await coro_factory()
        except httpx.HTTPError as exc:
            last_exc = exc
            if attempt < total_attempts:
                delay = _RETRY_DELAYS[attempt - 1]
                logger.warning(
                    "%s: attempt %d/%d failed (%s), retrying in %.1fs",
                    label, attempt, total_attempts, exc, delay,
                )
                await asyncio.sleep(delay)

    raise RemnawaveError(f"HTTP error after {total_attempts} attempts in {label}: {last_exc}") from last_exc


def _sanitize_username(telegram_id: int, tg_username: str | None) -> str:
    """Return a panel-safe username (^[a-zA-Z0-9_-]{3,36}$).

    Falls back to tg_{telegram_id} when the Telegram handle doesn't fit.
    """
    if tg_username and _USERNAME_RE.match(tg_username.lstrip('@')):
        return tg_username.lstrip('@')
    return f"tg_{telegram_id}"


def _to_utc(dt: datetime) -> datetime:
    """Attach UTC tzinfo to a naive datetime (asyncpg returns naive TZ-less stamps)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


async def create_panel_user(telegram_id: int,
                            tg_username: str | None,
                            expire_at: datetime) -> tuple[uuid.UUID, str]:
    """Create a new user in Remnawave Panel.

    Assigns a random active internal squad from the local DB.
    Returns (remnawave_uuid, subscription_url).
    Raises RemnawaveError on any API failure.
    """
    username = _sanitize_username(telegram_id, tg_username)
    squad_uuid = await postgres_dbms.get_random_active_remnawave_squad_uuid()
    if squad_uuid is None:
        logger.warning("No active Remnawave squads in DB — creating user without squad assignment")

    try:
        dto = CreateUserRequestDto(
            username=username,
            expire_at=_to_utc(expire_at),
            telegram_id=telegram_id,
            active_internal_squads=[squad_uuid] if squad_uuid else None,
        )
        response = await _call_with_http_retry(
            lambda: remnawave_sdk.users.create_user(dto),
            label="create_panel_user",
        )
    except RemnawaveError:
        raise
    except Exception as exc:
        raise RemnawaveError(f"Unexpected error while creating panel user: {exc}") from exc

    logger.info("Created Remnawave user %s (tg_id=%s)", response.uuid, telegram_id)
    return response.uuid, response.subscription_url


async def extend_panel_user_expiry(remnawave_uuid: uuid.UUID,
                                   new_expire_at: datetime) -> None:
    """Update expire_at for an existing Remnawave panel user.

    Raises RemnawaveError on any API failure.
    """
    try:
        dto = UpdateUserRequestDto(
            uuid=remnawave_uuid,
            expire_at=_to_utc(new_expire_at),
        )
        await _call_with_http_retry(
            lambda: remnawave_sdk.users.update_user(dto),
            label="extend_panel_user_expiry",
        )
    except RemnawaveError:
        raise
    except Exception as exc:
        raise RemnawaveError(f"Unexpected error while updating panel user expiry: {exc}") from exc

    logger.info("Updated expire_at for Remnawave user %s to %s", remnawave_uuid, new_expire_at)

