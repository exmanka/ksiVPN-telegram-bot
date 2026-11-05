"""``sync_panel_user`` — the single place that writes expireAt/squads of an existing panel user.

Covers every transition of the «Telegram-only» grace period with the DB layer and
the panel calls mocked:

- outside grace: expireAt = real expiration, squads untouched;
- entering grace: pre-grace squads captured from the panel, then [grace squad] +
  grace external squad (only if configured) + expireAt = expiration + days;
- re-entering after a failed attempt: captured state is not overwritten;
- leaving grace: captured internal squads and external squad restored (external
  squad cleared with null when the user had none), grace state forgotten;
- the window boundaries and free subscriptions.
"""

import uuid
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from src.config.schema import GraceSettings
from src.services import internal_functions as inf
from src.services.remnawave_service import UNSET


BASE = uuid.UUID('aaaaaaaa-0000-0000-0000-000000000001')
TG = uuid.UUID('aaaaaaaa-0000-0000-0000-000000000002')
GRACE_EXT = uuid.UUID('bbbbbbbb-0000-0000-0000-000000000001')
PROMO_EXT = uuid.UUID('bbbbbbbb-0000-0000-0000-000000000002')
RW_USER = uuid.UUID('cccccccc-0000-0000-0000-000000000001')

EXPIRATION = datetime(2026, 11, 10, 12, 0)


def _state(now, **overrides) -> dict:
    state = {
        'remnawave_uuid': RW_USER,
        'expiration_date': EXPIRATION,
        'price': 199,
        'grace_started_at': None,
        'pre_grace_internal_squads': None,
        'pre_grace_external_squad_uuid': None,
        'now': now,
    }
    state.update(overrides)
    return state


@pytest.fixture
def grace(monkeypatch):
    """Enable grace (3 days, with external squad) for the module under test; return a setter."""
    def configure(**kwargs):
        params = dict(enabled=True, days=3, internal_squad_uuid=TG, external_squad_uuid=GRACE_EXT)
        params.update(kwargs)
        monkeypatch.setattr(inf.settings.remnawave, 'grace', GraceSettings(**params))
    configure()
    return configure


@pytest.fixture
def panel(monkeypatch):
    mocks = {
        'update_panel_user': AsyncMock(),
        'get_panel_user_squads': AsyncMock(return_value=([BASE, TG], PROMO_EXT)),
    }
    for name, mock in mocks.items():
        monkeypatch.setattr(inf, name, mock)
    return mocks


@pytest.fixture
def db(monkeypatch):
    mocks = {
        'get_client_panel_state': AsyncMock(),
        'start_client_grace': AsyncMock(return_value=True),
        'clear_client_grace': AsyncMock(),
        'get_random_active_remnawave_squad_uuid': AsyncMock(return_value=BASE),
    }
    for name, mock in mocks.items():
        monkeypatch.setattr(inf.remnawave_db, name, mock)
    return mocks


# --- is_in_grace_window -------------------------------------------------------

@pytest.mark.parametrize('now, price, expected', [
    (EXPIRATION - timedelta(seconds=1), 199, False),          # still active
    (EXPIRATION, 199, True),                                   # exactly at expiration
    (EXPIRATION + timedelta(days=3) - timedelta(seconds=1), 199, True),
    (EXPIRATION + timedelta(days=3), 199, False),              # window is half-open
    (EXPIRATION + timedelta(hours=1), 0, False),               # free subscription
])
def test_grace_window(now, price, expected):
    grace = GraceSettings(enabled=True, days=3, internal_squad_uuid=TG)
    assert inf.is_in_grace_window(EXPIRATION, price, now, grace) is expected


def test_grace_window_disabled():
    grace = GraceSettings(enabled=False, days=3)
    assert inf.is_in_grace_window(EXPIRATION, 199, EXPIRATION + timedelta(hours=1), grace) is False


def test_grace_window_respects_configured_days():
    grace = GraceSettings(enabled=True, days=1, internal_squad_uuid=TG)
    assert inf.is_in_grace_window(EXPIRATION, 199, EXPIRATION + timedelta(hours=25), grace) is False


# --- sync_panel_user ----------------------------------------------------------

async def test_no_record(db, panel, grace):
    db['get_client_panel_state'].return_value = None

    assert await inf.sync_panel_user(1) is inf.PanelSyncResult.NO_RECORD
    panel['update_panel_user'].assert_not_awaited()


async def test_active_subscription_only_syncs_real_expiration(db, panel, grace):
    db['get_client_panel_state'].return_value = _state(now=EXPIRATION - timedelta(days=1))

    assert await inf.sync_panel_user(1) is inf.PanelSyncResult.REGULAR
    panel['update_panel_user'].assert_awaited_once_with(RW_USER, expire_at=EXPIRATION)
    panel['get_panel_user_squads'].assert_not_awaited()


async def test_entering_grace_captures_and_applies_grace_state(db, panel, grace):
    db['get_client_panel_state'].return_value = _state(now=EXPIRATION + timedelta(seconds=1))

    assert await inf.sync_panel_user(1) is inf.PanelSyncResult.GRACE

    db['start_client_grace'].assert_awaited_once_with(1, [BASE, TG], PROMO_EXT)
    panel['update_panel_user'].assert_awaited_once_with(
        RW_USER, expire_at=EXPIRATION + timedelta(days=3), internal_squads=[TG], external_squad=GRACE_EXT,
    )


async def test_entering_grace_uses_configured_days(db, panel, grace):
    grace(days=1)
    db['get_client_panel_state'].return_value = _state(now=EXPIRATION + timedelta(seconds=1))

    await inf.sync_panel_user(1)

    assert panel['update_panel_user'].await_args.kwargs['expire_at'] == EXPIRATION + timedelta(days=1)


async def test_entering_grace_without_external_squad_leaves_it_untouched(db, panel, grace):
    grace(external_squad_uuid=None)
    db['get_client_panel_state'].return_value = _state(now=EXPIRATION + timedelta(seconds=1))

    await inf.sync_panel_user(1)

    assert panel['update_panel_user'].await_args.kwargs['external_squad'] is UNSET


async def test_retry_in_grace_does_not_recapture(db, panel, grace):
    db['get_client_panel_state'].return_value = _state(
        now=EXPIRATION + timedelta(minutes=1),
        grace_started_at=EXPIRATION, pre_grace_internal_squads=[BASE, TG], pre_grace_external_squad_uuid=PROMO_EXT,
    )

    assert await inf.sync_panel_user(1) is inf.PanelSyncResult.GRACE
    panel['get_panel_user_squads'].assert_not_awaited()
    db['start_client_grace'].assert_not_awaited()
    panel['update_panel_user'].assert_awaited_once()


async def test_user_with_only_grace_squad_is_not_captured_as_pre_grace(db, panel, grace):
    panel['get_panel_user_squads'].return_value = ([TG], GRACE_EXT)
    db['get_client_panel_state'].return_value = _state(now=EXPIRATION + timedelta(seconds=1))

    await inf.sync_panel_user(1)

    db['start_client_grace'].assert_awaited_once_with(1, None, None)


async def test_leaving_grace_restores_squads_and_external(db, panel, grace):
    new_expiration = EXPIRATION + timedelta(days=31)
    db['get_client_panel_state'].return_value = _state(
        now=EXPIRATION + timedelta(days=1), expiration_date=new_expiration,
        grace_started_at=EXPIRATION, pre_grace_internal_squads=[BASE, TG], pre_grace_external_squad_uuid=PROMO_EXT,
    )

    assert await inf.sync_panel_user(1) is inf.PanelSyncResult.REGULAR

    panel['update_panel_user'].assert_awaited_once_with(
        RW_USER, expire_at=new_expiration, internal_squads=[BASE, TG], external_squad=PROMO_EXT,
    )
    db['clear_client_grace'].assert_awaited_once_with(1)


async def test_leaving_grace_clears_external_squad_when_user_had_none(db, panel, grace):
    db['get_client_panel_state'].return_value = _state(
        now=EXPIRATION + timedelta(days=1), expiration_date=EXPIRATION + timedelta(days=31),
        grace_started_at=EXPIRATION, pre_grace_internal_squads=[BASE, TG], pre_grace_external_squad_uuid=None,
    )

    await inf.sync_panel_user(1)

    assert panel['update_panel_user'].await_args.kwargs['external_squad'] is None  # sent as JSON null


async def test_leaving_grace_without_external_config_leaves_it_untouched(db, panel, grace):
    grace(external_squad_uuid=None)
    db['get_client_panel_state'].return_value = _state(
        now=EXPIRATION + timedelta(days=1), expiration_date=EXPIRATION + timedelta(days=31),
        grace_started_at=EXPIRATION, pre_grace_internal_squads=[BASE, TG], pre_grace_external_squad_uuid=None,
    )

    await inf.sync_panel_user(1)

    assert panel['update_panel_user'].await_args.kwargs['external_squad'] is UNSET


async def test_leaving_grace_without_captured_squads_uses_fallback(db, panel, grace):
    db['get_client_panel_state'].return_value = _state(
        now=EXPIRATION + timedelta(days=1), expiration_date=EXPIRATION + timedelta(days=31),
        grace_started_at=EXPIRATION, pre_grace_internal_squads=None,
    )

    await inf.sync_panel_user(1)

    assert panel['update_panel_user'].await_args.kwargs['internal_squads'] == [BASE, TG]
    db['clear_client_grace'].assert_awaited_once_with(1)


async def test_panel_failure_on_leave_keeps_grace_state_for_retry(db, panel, grace):
    panel['update_panel_user'].side_effect = inf.RemnawaveError('panel down')
    db['get_client_panel_state'].return_value = _state(
        now=EXPIRATION + timedelta(days=1), expiration_date=EXPIRATION + timedelta(days=31),
        grace_started_at=EXPIRATION, pre_grace_internal_squads=[BASE, TG],
    )

    with pytest.raises(inf.RemnawaveError):
        await inf.sync_panel_user(1)
    db['clear_client_grace'].assert_not_awaited()


async def test_grace_disabled_mid_grace_restores(db, panel, grace):
    grace(enabled=False)
    db['get_client_panel_state'].return_value = _state(
        now=EXPIRATION + timedelta(hours=1),
        grace_started_at=EXPIRATION, pre_grace_internal_squads=[BASE, TG], pre_grace_external_squad_uuid=PROMO_EXT,
    )

    assert await inf.sync_panel_user(1) is inf.PanelSyncResult.REGULAR
    assert panel['update_panel_user'].await_args.kwargs['internal_squads'] == [BASE, TG]


async def test_free_subscription_never_enters_grace(db, panel, grace):
    db['get_client_panel_state'].return_value = _state(now=EXPIRATION + timedelta(hours=1), price=0)

    assert await inf.sync_panel_user(1) is inf.PanelSyncResult.REGULAR
    panel['update_panel_user'].assert_awaited_once_with(RW_USER, expire_at=EXPIRATION)


# --- sync_panel_user_safely -----------------------------------------------------

async def test_safely_alerts_admin_on_panel_error(monkeypatch):
    monkeypatch.setattr(inf, 'sync_panel_user', AsyncMock(side_effect=inf.RemnawaveError('boom')))
    deliver = AsyncMock()
    monkeypatch.setattr(inf, 'safe_deliver', deliver)

    await inf.sync_panel_user_safely(1)  # must not raise

    deliver.assert_awaited_once()


async def test_safely_alerts_admin_on_missing_record(monkeypatch):
    monkeypatch.setattr(inf, 'sync_panel_user', AsyncMock(return_value=inf.PanelSyncResult.NO_RECORD))
    deliver = AsyncMock()
    monkeypatch.setattr(inf, 'safe_deliver', deliver)

    await inf.sync_panel_user_safely(1)

    deliver.assert_awaited_once()
