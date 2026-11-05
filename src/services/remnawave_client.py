"""Remnawave Panel SDK singleton.

Built once at import time from `settings.remnawave.*` and imported by
services/scripts that need to talk to the panel. Mirrors the `src/runtime.py`
pattern used for the aiogram Bot/Dispatcher.
"""
import httpx
from remnawave import RemnawaveSDK

from src.config import settings


def build_remnawave_sdk() -> RemnawaveSDK:
    kwargs: dict = {
        "base_url": settings.remnawave.base_url,
        "token": settings.remnawave.token.get_secret_value(),
    }
    if settings.remnawave.caddy_token is not None:
        kwargs["caddy_token"] = settings.remnawave.caddy_token.get_secret_value()
    return RemnawaveSDK(**kwargs)


remnawave_sdk: RemnawaveSDK = build_remnawave_sdk()

# The SDK's own httpx client: base URL with ``/api``, Bearer token, Caddy
# ``X-Api-Key`` and ``x-forwarded-*`` headers are already set on it.
# Used for the few calls the SDK can't express: its request DTOs are
# serialized with ``exclude_none=True``, so e.g. ``externalSquadUuid: null``
# (remove the user from an external squad) can't be sent through
# ``users.update_user``. Verified against remnawave/backend 2.7.4.
_sdk_http_client = remnawave_sdk._client  # pyright: ignore[reportPrivateUsage]
assert _sdk_http_client is not None  # always built by RemnawaveSDK when no client is passed
remnawave_http: httpx.AsyncClient = _sdk_http_client
