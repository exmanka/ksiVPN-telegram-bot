"""Pytest top-level fixtures and import-time bootstrapping.

Tests must be able to import ``src.payments.*`` without the bot's real config
chain (dynaconf → Pydantic Settings → real env vars). We set placeholder env
vars before any ``src.*`` import so config validation passes with dummy values;
individual tests then construct ``PaymentService`` / providers directly with
their own arguments instead of relying on the singleton in ``src.payments.runtime``.

This keeps tests pure-unit: no Docker, no Redis, no Postgres, no Telegram.
"""

import os
import sys
from pathlib import Path


# Add repo root to sys.path so ``from src.payments...`` works when running
# pytest from any cwd.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


# Set dummy env so that ``from src.config import settings`` succeeds during
# import of modules under test. Tests that need real config swap values
# via monkeypatch at the point of use.
os.environ.setdefault("TGBOT_BOT__TOKEN", "1:test-dummy-token")
os.environ.setdefault("TGBOT_BOT__ADMIN_ID", "1")
os.environ.setdefault("TGBOT_CONNECTIONS__POSTGRES__HOST", "localhost")
os.environ.setdefault("TGBOT_CONNECTIONS__POSTGRES__USER", "test")
os.environ.setdefault("TGBOT_CONNECTIONS__POSTGRES__PASSWORD", "test")
os.environ.setdefault("TGBOT_CONNECTIONS__POSTGRES__DB", "test")
os.environ.setdefault("TGBOT_CONNECTIONS__REDIS__HOST", "localhost")
os.environ.setdefault("TGBOT_CONNECTIONS__REDIS__PASSWORD", "test")
os.environ.setdefault("TGBOT_PAYMENTS__YOOMONEY__ENABLED", "true")
os.environ.setdefault("TGBOT_PAYMENTS__YOOMONEY__TOKEN", "test-token")
os.environ.setdefault("TGBOT_PAYMENTS__YOOMONEY__NOTIFICATION_SECRET", "test-notification-secret")
os.environ.setdefault("TGBOT_PAYMENTS__YOOKASSA__ENABLED", "true")
os.environ.setdefault("TGBOT_PAYMENTS__YOOKASSA__SHOP_ID", "123456")
os.environ.setdefault("TGBOT_PAYMENTS__YOOKASSA__SECRET_KEY", "test-secret-key")
os.environ.setdefault("TGBOT_PAYMENTS__RETURN_URL", "https://t.me/ksiVPN_bot")
# Fiscalization defaults off in tests — no «Мой налог» credentials needed
os.environ.setdefault("TGBOT_PAYMENTS__FISCALIZATION_ENABLED", "false")
os.environ.setdefault("TGBOT_PAYMENTS__YOOMONEY__FISCALIZATION_ENABLED", "false")
os.environ.setdefault("TGBOT_PAYMENTS__YOOKASSA__FISCALIZATION_ENABLED", "false")
os.environ.setdefault("TGBOT_LOCALIZATION__LANGUAGE", "ru")
os.environ.setdefault("TGBOT_REMNAWAVE__BASE_URL", "https://panel.example.com")
os.environ.setdefault("TGBOT_REMNAWAVE__TOKEN", "test-remnawave-token-12345")
os.environ.setdefault("TGBOT_TZ", "UTC")
