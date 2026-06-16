"""Вывод telegram_id всех пользователей указанного internal squad-а в Remnawave Panel.

Назначение
----------
По имени internal squad-а ищет всех его участников в Remnawave Panel и выводит
их telegram_id. Данные берутся напрямую из панели — БД бота не используется.

Требования
----------
  Python 3.12 (.venv-3.12):
      .venv-3.12/bin/pip install remnawave

Переменные окружения (Remnawave):
    REMNAWAVE_BASE_URL    — корневой URL панели (https://panel.example.com)
    REMNAWAVE_TOKEN       — API Bearer-токен (панель → API Tokens)
    REMNAWAVE_CADDY_TOKEN — необязательно, если панель за Caddy с токен-авторизацией

Использование:
    .venv-3.12/bin/python scripts/list_squad_telegram_ids.py "Squad Name"
    .venv-3.12/bin/python scripts/list_squad_telegram_ids.py "Squad Name" --active-only
    .venv-3.12/bin/python scripts/list_squad_telegram_ids.py "Squad Name" --page-size 200
"""
import argparse
import asyncio
import logging
import os
from datetime import datetime, timezone
from uuid import UUID

from remnawave import RemnawaveSDK
from remnawave.models import UserResponseDto


logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger('list_squad_telegram_ids')

# ---------------------------------------------------------------------------
# Config from env
# ---------------------------------------------------------------------------

REMNAWAVE_BASE_URL = os.getenv('REMNAWAVE_BASE_URL', '')
REMNAWAVE_TOKEN = os.getenv('REMNAWAVE_TOKEN', '')
REMNAWAVE_CADDY_TOKEN = os.getenv('REMNAWAVE_CADDY_TOKEN')

DEFAULT_PAGE_SIZE = 100


def _build_sdk() -> RemnawaveSDK:
    if not REMNAWAVE_BASE_URL:
        raise SystemExit("REMNAWAVE_BASE_URL is not set")
    if not REMNAWAVE_TOKEN:
        raise SystemExit("REMNAWAVE_TOKEN is not set")
    kwargs: dict = {"base_url": REMNAWAVE_BASE_URL, "token": REMNAWAVE_TOKEN}
    if REMNAWAVE_CADDY_TOKEN:
        kwargs["caddy_token"] = REMNAWAVE_CADDY_TOKEN
    return RemnawaveSDK(**kwargs)


# ---------------------------------------------------------------------------
# Panel helpers
# ---------------------------------------------------------------------------

async def _resolve_squad_uuid(sdk: RemnawaveSDK, name: str) -> UUID:
    response = await sdk.internal_squads.get_internal_squads()
    matches = [s for s in response.internal_squads if s.name == name]
    if not matches:
        available = ', '.join(sorted(s.name for s in response.internal_squads)) or '<none>'
        raise SystemExit(f"Internal squad '{name}' not found. Available: {available}")
    if len(matches) > 1:
        raise SystemExit(
            f"Internal squad name '{name}' is ambiguous — {len(matches)} matches in panel")
    return matches[0].uuid


async def _fetch_all_panel_users(sdk: RemnawaveSDK,
                                 page_size: int) -> list[UserResponseDto]:
    """Fetch all users from the panel using offset pagination."""
    all_users: list[UserResponseDto] = []
    start = 0

    while True:
        response = await sdk.users.get_all_users(start=start, size=page_size)
        all_users.extend(response.users)
        logger.debug("Fetched %d/%d panel users", len(all_users), response.total)

        if len(all_users) >= response.total:
            break
        start += page_size

    return all_users


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main(squad_name: str, page_size: int, active_only: bool) -> None:
    sdk = _build_sdk()

    logger.info("Resolving internal squad '%s' …", squad_name)
    squad_uuid = await _resolve_squad_uuid(sdk, squad_name)
    logger.info("Squad uuid: %s", squad_uuid)

    logger.info("Fetching panel users …")
    panel_users = await _fetch_all_panel_users(sdk, page_size)
    logger.info("Total panel users: %d", len(panel_users))

    members = [u for u in panel_users
               if any(s.uuid == squad_uuid for s in u.active_internal_squads)]

    if active_only:
        now = datetime.now(timezone.utc)
        before = len(members)
        members = [u for u in members if u.expire_at.astimezone(timezone.utc) > now]
        logger.info("Active-only filter: %d → %d members", before, len(members))

    telegram_ids = [u.telegram_id for u in members if u.telegram_id is not None]
    without_tg = len(members) - len(telegram_ids)

    logger.info(
        "Squad members: %d  (with telegram_id: %d, without: %d)",
        len(members), len(telegram_ids), without_tg,
    )

    if telegram_ids:
        print(' '.join(str(tg_id) for tg_id in telegram_ids))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='List telegram_id of all users in a Remnawave internal squad (by name).')
    parser.add_argument('squad_name', help='Internal squad name (exact match)')
    parser.add_argument(
        '--active-only', action='store_true',
        help='Include only users whose subscription has not expired (expire_at > now UTC)',
    )
    parser.add_argument(
        '--page-size', type=int, default=DEFAULT_PAGE_SIZE,
        metavar='N',
        help=f'Users per API page (default: {DEFAULT_PAGE_SIZE})',
    )
    args = parser.parse_args()
    asyncio.run(main(
        squad_name=args.squad_name,
        page_size=args.page_size,
        active_only=args.active_only,
    ))
