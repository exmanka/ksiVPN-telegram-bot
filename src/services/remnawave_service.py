"""Integration layer between the bot and Remnawave Panel.

All public functions raise RemnawaveError on panel-side failures so callers
can decide whether to retry, notify the admin, or silently skip.
"""
import logging
import re
import uuid
from datetime import datetime, timezone

import httpx
from remnawave.models import CreateUserRequestDto, UpdateUserRequestDto

from src.database import postgres_dbms
from src.services.remnawave_client import remnawave_sdk


logger = logging.getLogger(__name__)

_USERNAME_RE = re.compile(r'^[a-zA-Z0-9_-]{3,36}$')


class RemnawaveError(Exception):
    """Raised when a Remnawave Panel API call fails."""


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
        response = await remnawave_sdk.users.create_user(dto)
    except httpx.HTTPError as exc:
        raise RemnawaveError(f"HTTP error while creating panel user: {exc}") from exc
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
        await remnawave_sdk.users.update_user(dto)
    except httpx.HTTPError as exc:
        raise RemnawaveError(f"HTTP error while updating panel user expiry: {exc}") from exc
    except Exception as exc:
        raise RemnawaveError(f"Unexpected error while updating panel user expiry: {exc}") from exc

    logger.info("Updated expire_at for Remnawave user %s to %s", remnawave_uuid, new_expire_at)

