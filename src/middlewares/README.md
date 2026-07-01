# Middlewares
Current directory contains middlewares for checking user is unauthorized, authorized or admin.

Note: `admin_mw`, `throttling_mw`, `user_authorized_mw` and `user_unauthorized_mw` are aiogram **dispatcher** middlewares (`BaseMiddleware`), attached in `main.py` via `dp.*.middleware(...)` — they run on incoming updates. `retry_mw` is a **session request** middleware (`BaseRequestMiddleware`), attached to the Bot's session in `src/bot.py:build_bot` — it retries outgoing Telegram API calls. Different aiogram layer; do not register it via `dp.*.middleware`.
