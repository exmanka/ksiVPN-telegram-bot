"""Integration layer between the bot and Remnawave Panel.

All public functions raise RemnawaveError on panel-side failures so callers
can decide whether to retry, notify the admin, or silently skip.
"""
import asyncio
import logging
import re
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Awaitable, Callable
from zoneinfo import ZoneInfo

import httpx
from remnawave.exceptions import NetworkError as RemnawaveNetworkError
from remnawave.exceptions import ServerError as RemnawaveServerError
from remnawave.models import CreateUserRequestDto
from remnawave.models.hwid import DeleteUserHwidDeviceRequestDto, HwidDeviceDto

from src.config import settings
from src.database import remnawave_db
from src.services.remnawave_client import remnawave_http, remnawave_sdk


logger = logging.getLogger(__name__)

_USERNAME_RE = re.compile(r'^[a-zA-Z0-9_-]{3,36}$')


class RemnawaveError(Exception):
    """Raised when a Remnawave Panel API call fails."""


class _TransientPanelError(Exception):
    """5xx answer to a raw (non-SDK) panel call — retried like the SDK's ServerError."""


class _Unset(Enum):
    UNSET = 'UNSET'


# Sentinel for update_panel_user: «leave this field as it is» (``None`` means «clear it»).
UNSET = _Unset.UNSET


# Delays between retry attempts (seconds). Length = number of retries.
# 2 retries → 3 total attempts, max wait ≈ 3 s before raising RemnawaveError.
_RETRY_DELAYS: tuple[float, ...] = (1.0, 2.0)


_RETRYABLE = (httpx.HTTPError, RemnawaveServerError, RemnawaveNetworkError, _TransientPanelError)


async def _call_with_http_retry(coro_factory: Callable[[], Awaitable[Any]], *, label: str) -> Any:
    """Execute coro_factory(), retrying on transient errors with exponential backoff.

    Retried:
    - httpx.HTTPError — raw network / TLS failures (before SDK processing)
    - RemnawaveServerError — panel 5xx responses
    - RemnawaveNetworkError — SDK-level network errors

    Not retried: 4xx client errors (BadRequestError, ValidationError, NotFoundError,
    ConflictError, etc.) — a retry won't fix a logic/validation problem.

    :param coro_factory: zero-arg callable returning the coroutine to await
    :param label: human-readable name for log messages
    :raises RemnawaveError: when all attempts are exhausted
    """
    last_exc: Exception | None = None
    total_attempts = len(_RETRY_DELAYS) + 1

    for attempt in range(1, total_attempts + 1):
        try:
            return await coro_factory()
        except _RETRYABLE as exc:
            last_exc = exc
            if attempt < total_attempts:
                delay = _RETRY_DELAYS[attempt - 1]
                logger.warning(
                    "%s: attempt %d/%d failed (%s), retrying in %.1fs",
                    label, attempt, total_attempts, exc, delay,
                )
                await asyncio.sleep(delay)

    raise RemnawaveError(f"Transient error after {total_attempts} attempts in {label}: {last_exc}") from last_exc


def _sanitize_username(telegram_id: int, tg_username: str | None) -> str:
    """Return a panel-safe username (^[a-zA-Z0-9_-]{3,36}$).

    Falls back to tg_{telegram_id} when the Telegram handle doesn't fit.
    """
    if tg_username and _USERNAME_RE.match(tg_username.lstrip('@')):
        return tg_username.lstrip('@')
    return f"tg_{telegram_id}"


def _to_utc(dt: datetime) -> datetime:
    """Convert naive datetime from the bot DB to UTC-aware.

    asyncpg returns TIMESTAMP WITHOUT TIME ZONE as naive datetime.
    The bot stores all datetimes in the application timezone (settings.tz),
    so we must attach that zone before converting to UTC — not blindly attach UTC.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=ZoneInfo(settings.tz)).astimezone(timezone.utc)
    return dt.astimezone(timezone.utc)


def _to_api_datetime(dt: datetime) -> str:
    """Serialize a bot datetime for the panel API: UTC, ISO-8601 with milliseconds and ``Z``.

    The panel's validator rejects ``+00:00`` offsets, so ``isoformat()`` can't be used as is.
    """
    return _to_utc(dt).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'


async def create_panel_user(telegram_id: int,
                            tg_username: str | None,
                            expire_at: datetime) -> tuple[uuid.UUID, str]:
    """Create a new user in Remnawave Panel.

    Assigns a random active internal squad from the local DB.
    Returns (remnawave_uuid, subscription_url).
    Raises RemnawaveError on any API failure.
    """
    username = _sanitize_username(telegram_id, tg_username)
    squad_uuid = await remnawave_db.get_random_active_remnawave_squad_uuid()
    if squad_uuid is None:
        logger.warning("No active Remnawave squads in DB — creating user without squad assignment")

    squads = [squad_uuid] if squad_uuid else []
    # The Telegram-only grace squad is kept on every user as a permanent "reserve" server,
    # so the app already has its config when the grace period starts.
    grace = settings.remnawave.grace
    if grace.enabled and grace.squad_uuid and grace.squad_uuid not in squads:
        squads.append(grace.squad_uuid)

    try:
        dto = CreateUserRequestDto(
            username=username,
            expire_at=_to_utc(expire_at),
            telegram_id=telegram_id,
            active_internal_squads=squads or None,
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


def build_update_user_payload(remnawave_uuid: uuid.UUID,
                              *,
                              expire_at: datetime,
                              internal_squads: list[uuid.UUID] | _Unset = UNSET,
                              external_squad: uuid.UUID | None | _Unset = UNSET) -> dict[str, Any]:
    """Build the JSON body of ``PATCH /api/users``. ``UNSET`` fields are omitted; ``None`` is sent as null."""
    payload: dict[str, Any] = {
        'uuid': str(remnawave_uuid),
        'expireAt': _to_api_datetime(expire_at),
    }
    if internal_squads is not UNSET:
        payload['activeInternalSquads'] = [str(s) for s in internal_squads]
    if external_squad is not UNSET:
        payload['externalSquadUuid'] = str(external_squad) if external_squad is not None else None
    return payload


async def update_panel_user(remnawave_uuid: uuid.UUID,
                            *,
                            expire_at: datetime,
                            internal_squads: list[uuid.UUID] | _Unset = UNSET,
                            external_squad: uuid.UUID | None | _Unset = UNSET) -> None:
    """Update expireAt and, optionally, squads of a panel user in one atomic ``PATCH /api/users``.

    ``internal_squads`` replaces the whole ``activeInternalSquads`` list. ``external_squad=None``
    removes the user from its external squad — that's why this goes through the raw httpx client
    instead of ``users.update_user`` (the SDK drops ``None`` fields). ``status`` is never sent:
    moving expireAt into the future reactivates an EXPIRED user, and a manual DISABLED survives.

    Raises RemnawaveError on any API failure.
    """
    payload = build_update_user_payload(
        remnawave_uuid, expire_at=expire_at, internal_squads=internal_squads, external_squad=external_squad,
    )

    async def _patch() -> None:
        response = await remnawave_http.patch('/users', json=payload)
        if response.status_code >= 500:
            raise _TransientPanelError(f'PATCH /users -> {response.status_code}: {response.text[:300]}')
        if response.status_code >= 400:
            raise RemnawaveError(f'PATCH /users -> {response.status_code}: {response.text[:300]}')

    try:
        await _call_with_http_retry(_patch, label="update_panel_user")
    except RemnawaveError:
        raise
    except Exception as exc:
        raise RemnawaveError(f"Unexpected error while updating panel user: {exc}") from exc

    logger.info("Updated Remnawave user %s: %s", remnawave_uuid,
                {k: v for k, v in payload.items() if k != 'uuid'})


async def get_panel_user_squads(remnawave_uuid: uuid.UUID) -> tuple[list[uuid.UUID], uuid.UUID | None]:
    """Return (active internal squad UUIDs, external squad UUID or None) of a panel user.

    Raises RemnawaveError on any API failure.
    """
    try:
        user = await _call_with_http_retry(
            lambda: remnawave_sdk.users.get_user_by_uuid(str(remnawave_uuid)),
            label="get_panel_user_squads",
        )
    except RemnawaveError:
        raise
    except Exception as exc:
        raise RemnawaveError(f"Unexpected error while fetching panel user: {exc}") from exc

    return [squad.uuid for squad in user.active_internal_squads], user.external_squad_uuid


async def get_user_hwid_devices(remnawave_uuid: uuid.UUID) -> list[HwidDeviceDto]:
    """Return HWID devices registered in Remnawave Panel for the user.

    Raises RemnawaveError on any API failure.
    """
    try:
        response = await _call_with_http_retry(
            lambda: remnawave_sdk.hwid.get_hwid_user(str(remnawave_uuid)),
            label="get_user_hwid_devices",
        )
    except RemnawaveError:
        raise
    except Exception as exc:
        raise RemnawaveError(f"Unexpected error while fetching panel user HWID devices: {exc}") from exc

    return response.devices


async def delete_user_hwid_device(remnawave_uuid: uuid.UUID, hwid: str) -> None:
    """Delete a HWID device of the user in Remnawave Panel.

    Raises RemnawaveError on any API failure.
    """
    try:
        dto = DeleteUserHwidDeviceRequestDto(user_uuid=remnawave_uuid, hwid=hwid)
        await _call_with_http_retry(
            lambda: remnawave_sdk.hwid.delete_hwid_to_user(dto),
            label="delete_user_hwid_device",
        )
    except RemnawaveError:
        raise
    except Exception as exc:
        raise RemnawaveError(f"Unexpected error while deleting panel user HWID device: {exc}") from exc

    logger.info("Deleted HWID device %s of Remnawave user %s", hwid, remnawave_uuid)
