"""One-off / maintenance script: distribute Remnawave users across basic-01/02/03 squads.

Назначение
----------
До запуска: в Remnawave Panel все клиенты бота лежат в одном internal squad —
`basic-01`. В `basic-02` уже сидят несколько тестовых клиентов, `basic-03` пуст.

Скрипт разносит пользователей по трём сквадам так, чтобы никому не сломать
активный VPN-доступ:

1. Любой пользователь, который хоть раз подключался (user_traffic.online_at IS NOT NULL),
   остаётся в текущих сквадах.
2. Не подключавшиеся клиенты в `basic-02` (тестовые) — остаются на месте.
3. Не подключавшиеся клиенты НЕ в `basic-02` с **активной** подпиской —
   переезжают в `basic-02` (одиночный сквад).
4. Не подключавшиеся клиенты НЕ в `basic-02` с истекшей подпиской —
   равномерно (round-robin по отсортированному uuid) раскидываются по
   `basic-01` / `basic-02` / `basic-03`.

Источник истины для «активная подписка»: само поле `user.expire_at` из Remnawave
Panel (бот синхронизирует `expiration_date → expire_at` после каждого изменения;
для контроля расхождений есть `scripts/check_remnawave_expiry_sync.py`).
БД боту тут не нужна — скрипт ходит только в панель.

По умолчанию — dry-run: только сводка по категориям. Ключ --apply применяет
изменения через bulk-эндпоинт `bulk_update_users_internal_squads`
(до 500 UUID за запрос).

Идемпотентность
---------------
Повторный запуск с --apply на уже мигрированной панели — no-op:
все категории, кроме KEEP_*, обнулятся.

Требования
----------
  Python 3.12 (.venv-3.12):
      .venv-3.12/bin/pip install remnawave

Переменные окружения (Remnawave):
    REMNAWAVE_BASE_URL    — корневой URL панели (https://panel.example.com)
    REMNAWAVE_TOKEN       — API Bearer-токен (панель → API Tokens)
    REMNAWAVE_CADDY_TOKEN — необязательно, если панель за Caddy с токен-авторизацией

Использование:
    # Dry-run (посмотреть кто куда поедет, без записей):
    .venv-3.12/bin/python scripts/distribute_remnawave_squads.py

    # Применить изменения:
    .venv-3.12/bin/python scripts/distribute_remnawave_squads.py --apply
"""
import argparse
import asyncio
import logging
import os
import uuid
from collections import defaultdict
from datetime import datetime, timezone

from remnawave import RemnawaveSDK
from remnawave.exceptions import ApiError as RemnawaveApiError
from remnawave.models import BulkUpdateUsersSquadsRequestDto


logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger('distribute_remnawave_squads')

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

REMNAWAVE_BASE_URL = os.getenv('REMNAWAVE_BASE_URL', '')
REMNAWAVE_TOKEN = os.getenv('REMNAWAVE_TOKEN', '')
REMNAWAVE_CADDY_TOKEN = os.getenv('REMNAWAVE_CADDY_TOKEN')

TARGET_SQUAD_NAMES = ('basic-01', 'basic-02', 'basic-03')
BULK_CHUNK_SIZE = 500  # panel limit on uuids per BulkUpdateUsersSquadsRequestDto


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

async def _resolve_target_squads(sdk: RemnawaveSDK) -> dict[str, uuid.UUID]:
    """Fetch all squads from the panel and return {name: uuid} for required basic-0N squads."""
    response = await sdk.internal_squads.get_internal_squads()
    panel_by_name = {s.name: s.uuid for s in response.internal_squads}
    missing = [name for name in TARGET_SQUAD_NAMES if name not in panel_by_name]
    if missing:
        logger.error("Target squad(s) not found in panel: %s", missing)
        logger.error("Panel has: %s", sorted(panel_by_name.keys()))
        raise SystemExit(1)
    return {name: panel_by_name[name] for name in TARGET_SQUAD_NAMES}


async def _fetch_all_panel_users(sdk: RemnawaveSDK, page_size: int) -> list:
    """Paginate sdk.users.get_all_users until total is reached."""
    all_users: list = []
    start = 0
    total: int | None = None
    while True:
        response = await sdk.users.get_all_users(start=start, size=page_size)
        page = list(response.users)
        all_users.extend(page)
        if total is None:
            total = int(response.total)
            logger.info("Panel reports %d user(s) in total", total)
        logger.info("  fetched %d/%d", len(all_users), total)
        if not page or len(all_users) >= total:
            break
        start += page_size
    return all_users


async def _bulk_set_squad(sdk: RemnawaveSDK,
                          uuids: list[uuid.UUID],
                          squad_uuid: uuid.UUID,
                          squad_name: str) -> None:
    """Apply [squad_uuid] to a list of users in chunks of BULK_CHUNK_SIZE."""
    for i in range(0, len(uuids), BULK_CHUNK_SIZE):
        chunk = uuids[i:i + BULK_CHUNK_SIZE]
        dto = BulkUpdateUsersSquadsRequestDto(
            uuids=chunk,
            active_internal_squads=[squad_uuid],
        )
        try:
            response = await sdk.users_bulk_actions.bulk_update_users_internal_squads(dto)
            logger.info(
                "  squad=%s chunk=%d/%d size=%d affected=%s",
                squad_name, i // BULK_CHUNK_SIZE + 1,
                (len(uuids) + BULK_CHUNK_SIZE - 1) // BULK_CHUNK_SIZE,
                len(chunk), response.affected_rows,
            )
        except RemnawaveApiError as exc:
            errors_detail = (
                f" | validation_errors={exc.error.errors}"
                if exc.error.errors else ""
            )
            logger.error(
                "  squad=%s chunk size=%d FAILED: %s%s | uuids=%s",
                squad_name, len(chunk), exc, errors_detail,
                [str(u) for u in chunk],
            )
        except Exception as exc:
            logger.error(
                "  squad=%s chunk size=%d FAILED: %s | uuids=%s",
                squad_name, len(chunk), exc, [str(u) for u in chunk],
            )


def _is_expire_at_active(expire_at: datetime, now_utc: datetime) -> bool:
    """Compare panel's expire_at (tz-aware UTC) to now. Defensive for naive datetimes."""
    if expire_at.tzinfo is None:
        expire_at = expire_at.replace(tzinfo=timezone.utc)
    return expire_at > now_utc


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main(apply: bool, page_size: int) -> None:
    sdk = _build_sdk()

    logger.info("Resolving target squads in panel: %s", list(TARGET_SQUAD_NAMES))
    squads = await _resolve_target_squads(sdk)
    for name, suuid in squads.items():
        logger.info("  %s → %s", name, suuid)
    basic01_uuid = squads['basic-01']
    basic02_uuid = squads['basic-02']
    basic03_uuid = squads['basic-03']
    distribution_names = ('basic-01', 'basic-02', 'basic-03')
    distribution_pool = (basic01_uuid, basic02_uuid, basic03_uuid)

    logger.info("Fetching all panel users …")
    users = await _fetch_all_panel_users(sdk, page_size=page_size)

    now_utc = datetime.now(timezone.utc)

    # ----------------------------------------------------------------------
    # Categorise
    # ----------------------------------------------------------------------
    categories: dict[str, list[uuid.UUID]] = defaultdict(list)

    distribute_candidates: list[uuid.UUID] = []  # rule 4: never connected, expired, not in basic-02
    for user in users:
        user_uuid: uuid.UUID = user.uuid
        has_connected = user.user_traffic.online_at is not None
        current_squad_uuids = {s.uuid for s in user.active_internal_squads}
        in_basic02 = basic02_uuid in current_squad_uuids
        is_active = _is_expire_at_active(user.expire_at, now_utc)

        if has_connected:
            categories['KEEP_CONNECTED'].append(user_uuid)
        elif in_basic02:
            categories['KEEP_BASIC02'].append(user_uuid)
        elif is_active:
            categories['MOVE_TO_BASIC02'].append(user_uuid)
        else:
            distribute_candidates.append(user_uuid)

    # Round-robin distribute (deterministic: sort by uuid string).
    distribute_candidates.sort(key=str)
    for idx, user_uuid in enumerate(distribute_candidates):
        target_name = distribution_names[idx % 3]
        categories[f'DISTRIBUTE_{target_name.upper().replace("-", "_")}'].append(user_uuid)

    # ----------------------------------------------------------------------
    # Summary
    # ----------------------------------------------------------------------
    summary_order = (
        'KEEP_CONNECTED',
        'KEEP_BASIC02',
        'MOVE_TO_BASIC02',
        'DISTRIBUTE_BASIC_01',
        'DISTRIBUTE_BASIC_02',
        'DISTRIBUTE_BASIC_03',
    )
    logger.info("--- Distribution summary ---")
    total = 0
    for key in summary_order:
        count = len(categories.get(key, []))
        total += count
        logger.info("  %-22s %d", key + ':', count)
    logger.info("  %-22s %d", 'TOTAL:', total)

    # ----------------------------------------------------------------------
    # Apply
    # ----------------------------------------------------------------------
    if not apply:
        logger.info("Dry-run mode — no changes written. Re-run with --apply to apply.")
        return

    # Group by target squad uuid — at most three bulk groups.
    # MOVE_TO_BASIC02 + DISTRIBUTE_BASIC_02 share the same target.
    groups: dict[uuid.UUID, tuple[str, list[uuid.UUID]]] = {
        basic01_uuid: ('basic-01', list(categories.get('DISTRIBUTE_BASIC_01', []))),
        basic02_uuid: ('basic-02', list(categories.get('MOVE_TO_BASIC02', []))
                                  + list(categories.get('DISTRIBUTE_BASIC_02', []))),
        basic03_uuid: ('basic-03', list(categories.get('DISTRIBUTE_BASIC_03', []))),
    }

    logger.info("Applying changes via bulk_update_users_internal_squads …")
    for squad_uuid, (squad_name, uuids) in groups.items():
        if not uuids:
            logger.info("  squad=%s — nothing to update", squad_name)
            continue
        logger.info("  squad=%s — updating %d user(s)", squad_name, len(uuids))
        await _bulk_set_squad(sdk, uuids, squad_uuid, squad_name)

    logger.info("Done.")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Distribute Remnawave users across basic-01/02/03 internal squads.')
    parser.add_argument('--apply', action='store_true',
                        help='Apply changes via panel API (default: dry-run)')
    parser.add_argument('--page-size', type=int, default=500,
                        help='Page size for sdk.users.get_all_users pagination (default: 500)')
    args = parser.parse_args()
    asyncio.run(main(apply=args.apply, page_size=args.page_size))
