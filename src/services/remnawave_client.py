"""Remnawave Panel SDK singleton.

Built once at import time from `settings.remnawave.*` and imported by
services/scripts that need to talk to the panel. Mirrors the `src/runtime.py`
pattern used for the aiogram Bot/Dispatcher.
"""
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
