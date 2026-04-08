"""Shared runtime singletons (Bot + Dispatcher).

Handlers, middlewares and services import `bot` / `dp` from here instead of
constructing them, so the wiring stays in one place and tests can swap the
underlying `settings` by monkey-patching before import.
"""
from src.bot import build_bot
from src.config import settings
from src.dispatcher import build_dispatcher


bot = build_bot(settings)
dp = build_dispatcher(settings)
