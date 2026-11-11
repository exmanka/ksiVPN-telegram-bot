"""Contract of the subscription events worker (``src.services.subscription_events``).

The schedule itself is built by a Postgres trigger and is not tested here.
What we DO test:

- Event validation: stale ``for_expiration`` snapshot, free subscription and
  unknown kind are claimed without notifying anyone.
- Reminders honour the client's notification toggles and are delivered at most
  once (claim before send).
- ``expired`` notifies the client and the admin (with the subscription URL).
- ``first_connect`` skips the stale/free checks; it is sent only while the
  subscription is active, the client has a panel subscription link and
  Remnawave has seen no connection yet; an inactive subscription drops the event.
- Handler failure → event postponed (RETRY); the loop keeps going.
- Sleep timeout: clamped to ``[0, SAFETY_CAP]``; a wake-up (NOTIFY) cuts the sleep short.
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from src.services import localization as loc
from src.services import subscription_events as se


EXPIRATION = datetime(2026, 11, 10, 12, 0)
REMNAWAVE_UUID = UUID('22222222-2222-2222-2222-222222222222')


def _event(**overrides) -> dict:
    event = {
        'id': 1,
        'client_id': 100,
        'kind': 'remind_1d',
        'fire_at': EXPIRATION,
        'for_expiration': EXPIRATION,
        'attempts': 0,
        'expiration_date': EXPIRATION,
        'subscription_active': True,
        'telegram_id': 555,
        'name': 'Ivan',
        'surname': None,
        'username': 'ivan',
        'sub_expiration_in_1d': True,
        'sub_expiration_in_3d': True,
        'sub_expiration_in_7d': True,
        'price': 199,
        'remnawave_uuid': REMNAWAVE_UUID,
        'remnawave_subscription_url': 'https://sub.example/abc',
    }
    event.update(overrides)
    return event


@pytest.fixture
def db(monkeypatch):
    """Mock the DB layer used by the worker; claim succeeds by default."""
    mocks = {
        'claim_subscription_event': AsyncMock(return_value=True),
        'postpone_subscription_event': AsyncMock(),
        'delete_pending_subscription_event': AsyncMock(return_value=True),
        'fetch_due_subscription_events': AsyncMock(return_value=[]),
        'get_next_subscription_event_delay': AsyncMock(return_value=None),
    }
    for name, mock in mocks.items():
        monkeypatch.setattr(se.subscription_events_db, name, mock)
    return mocks


@pytest.fixture
def sent(monkeypatch):
    """Capture (telegram_id, text) of every delivered message."""
    messages: list[tuple[int, str]] = []

    async def fake_notify_user(telegram_id, text, reply_markup=None):
        messages.append((telegram_id, text))

    async def fake_notify_admin(text):
        messages.append((se.settings.bot.admin_id, text))

    monkeypatch.setattr(se, '_notify_user', fake_notify_user)
    monkeypatch.setattr(se, '_notify_admin', fake_notify_admin)
    return messages


# --- process_event: validation ---------------------------------------------

async def test_stale_snapshot_is_claimed_without_notification(db, sent):
    event = _event(expiration_date=datetime(2026, 12, 10, 12, 0))

    assert await se.process_event(event) is se.EventOutcome.DONE

    db['claim_subscription_event'].assert_awaited_once_with(1)
    assert sent == []


async def test_free_subscription_is_claimed_without_notification(db, sent):
    assert await se.process_event(_event(kind='expired', price=0)) is se.EventOutcome.DONE

    db['claim_subscription_event'].assert_awaited_once_with(1)
    assert sent == []


async def test_unknown_kind_is_claimed_without_notification(db, sent):
    assert await se.process_event(_event(kind='mystery')) is se.EventOutcome.DONE

    db['claim_subscription_event'].assert_awaited_once_with(1)
    assert sent == []


# --- reminders ----------------------------------------------------------------

@pytest.mark.parametrize('kind, column, loc_key', [
    ('remind_7d', 'sub_expiration_in_7d', 'sub_expires_7d'),
    ('remind_3d', 'sub_expiration_in_3d', 'sub_expires_3d'),
    ('remind_1d', 'sub_expiration_in_1d', 'sub_expires_1d'),
])
async def test_reminder_notifies_client_and_admin(db, sent, kind, column, loc_key):
    await se.process_event(_event(kind=kind, **{column: True}))

    assert sent[0] == (555, loc.auth.msgs[loc_key])
    assert sent[1][0] == se.settings.bot.admin_id
    assert sent[1][1] == loc.admn.msgs[loc_key].format(100, ' ivan', 'Ivan', '', 555)


async def test_reminder_disabled_in_settings_is_claimed_silently(db, sent):
    await se.process_event(_event(kind='remind_7d', sub_expiration_in_7d=False))

    db['claim_subscription_event'].assert_awaited_once_with(1)
    assert sent == []


async def test_reminder_without_settings_row_defaults_to_enabled(db, sent):
    await se.process_event(_event(kind='remind_3d', sub_expiration_in_3d=None))

    assert sent[0] == (555, loc.auth.msgs['sub_expires_3d'])


async def test_reminder_already_claimed_is_not_sent_again(db, sent):
    db['claim_subscription_event'].return_value = False

    assert await se.process_event(_event(kind='remind_1d')) is se.EventOutcome.DONE
    assert sent == []


# --- expired ------------------------------------------------------------------

async def test_expired_notifies_client_and_admin_with_subscription_url(db, sent):
    await se.process_event(_event(kind='expired'))

    assert sent[0] == (555, loc.auth.msgs['sub_expired'])
    assert sent[1][1] == loc.admn.msgs['sub_expired'].format(100, ' ivan', 'Ivan', '', 555, 'https://sub.example/abc')


async def test_expired_without_panel_record_uses_placeholder_url(db, sent):
    await se.process_event(_event(kind='expired', remnawave_subscription_url=None))

    assert sent[1][1] == loc.admn.msgs['sub_expired'].format(100, ' ivan', 'Ivan', '', 555, 'N/A')


async def test_expired_already_claimed_is_not_sent_again(db, sent):
    db['claim_subscription_event'].return_value = False

    await se.process_event(_event(kind='expired'))
    assert sent == []


# --- worker loop --------------------------------------------------------------

@pytest.mark.parametrize('delay, expected', [
    (None, se.SAFETY_CAP_SECONDS),
    (12.5, 12.5),
    (-3.0, 0.0),
    (se.SAFETY_CAP_SECONDS * 4, se.SAFETY_CAP_SECONDS),
])
def test_compute_sleep_timeout(delay, expected):
    assert se.compute_sleep_timeout(delay) == expected


async def test_run_once_processes_due_events_and_returns_next_delay(db, monkeypatch):
    events = [_event(id=1), _event(id=2)]
    db['fetch_due_subscription_events'].side_effect = [events, []]
    db['get_next_subscription_event_delay'].return_value = 42.0
    processed = []

    async def fake_process(event):
        processed.append(event['id'])
        return se.EventOutcome.DONE

    monkeypatch.setattr(se, 'process_event', fake_process)

    assert await se.SubscriptionEventsWorker().run_once() == 42.0
    assert processed == [1, 2]
    db['postpone_subscription_event'].assert_not_awaited()


async def test_failing_event_is_postponed_and_others_still_processed(db, monkeypatch):
    db['fetch_due_subscription_events'].return_value = [_event(id=1), _event(id=2)]
    processed = []

    async def fake_process(event):
        if event['id'] == 1:
            raise RuntimeError('boom')
        processed.append(event['id'])
        return se.EventOutcome.DONE

    monkeypatch.setattr(se, 'process_event', fake_process)

    await se.SubscriptionEventsWorker().run_once()

    assert processed == [2]
    db['postpone_subscription_event'].assert_awaited_once_with(1, se.RETRY_DELAY_SECONDS)


async def test_retry_outcome_is_postponed(db, monkeypatch):
    db['fetch_due_subscription_events'].return_value = [_event(id=7)]
    monkeypatch.setattr(se, 'process_event', AsyncMock(return_value=se.EventOutcome.RETRY))

    await se.SubscriptionEventsWorker().run_once()

    db['postpone_subscription_event'].assert_awaited_once_with(7, se.RETRY_DELAY_SECONDS)


async def test_full_batch_is_drained_until_short_batch(db, monkeypatch):
    monkeypatch.setattr(se, 'BATCH_LIMIT', 2)
    db['fetch_due_subscription_events'].side_effect = [
        [_event(id=1), _event(id=2)],
        [_event(id=3)],
    ]
    monkeypatch.setattr(se, 'process_event', AsyncMock(return_value=se.EventOutcome.DONE))

    await se.SubscriptionEventsWorker().run_once()

    assert db['fetch_due_subscription_events'].await_count == 2


async def test_db_error_backs_off(db):
    db['fetch_due_subscription_events'].side_effect = ConnectionError('db down')

    assert await se.SubscriptionEventsWorker().run_once() == se.ERROR_BACKOFF_SECONDS


async def test_notify_cuts_sleep_short(db):
    db['get_next_subscription_event_delay'].return_value = None  # would sleep SAFETY_CAP
    worker = se.SubscriptionEventsWorker()
    task = asyncio.create_task(worker._run_loop())
    await asyncio.sleep(0)  # let the first iteration run and go to sleep
    calls_before = db['fetch_due_subscription_events'].await_count

    worker._on_notify(None, 0, 'subscription_events', '100')
    for _ in range(5):
        await asyncio.sleep(0)

    assert db['fetch_due_subscription_events'].await_count == calls_before + 1
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


# --- grace period ---------------------------------------------------------------

@pytest.fixture
def grace_on(monkeypatch, db):
    """Enable a 3-day grace period; mock the panel sync."""
    from src.config.schema import GraceSettings
    monkeypatch.setattr(se.settings.remnawave, 'grace', GraceSettings(
        enabled=True, days=3, internal_squad_uuid='11111111-1111-1111-1111-111111111111'))
    sync = AsyncMock(return_value=se.internal_functions.PanelSyncResult.GRACE)
    monkeypatch.setattr(se.internal_functions, 'sync_panel_user', sync)
    return sync


async def test_expired_with_grace_enters_grace(db, sent, grace_on):
    assert await se.process_event(_event(kind='expired')) is se.EventOutcome.DONE

    grace_on.assert_awaited_once_with(100)
    db['claim_subscription_event'].assert_awaited_once_with(1)
    assert sent[0][0] == 555 and 'Telegram' in sent[0][1]
    assert sent[0][1] != loc.auth.msgs['sub_expired']
    assert sent[1][1] == loc.admn.msgs['sub_expired_grace'].format(
        100, ' ivan', 'Ivan', '', 555, 'https://sub.example/abc', se.format_localized_datetime(EXPIRATION + se.timedelta(days=3)))


async def test_expired_with_grace_message_uses_configured_days(db, sent, grace_on, monkeypatch):
    from src.config.schema import GraceSettings
    monkeypatch.setattr(se.settings.remnawave, 'grace', GraceSettings(
        enabled=True, days=1, internal_squad_uuid='11111111-1111-1111-1111-111111111111'))

    await se.process_event(_event(kind='expired'))

    expected = loc.auth.msgs['sub_expired_grace'].format(
        days=se.format_localized_bonus_days(se.timedelta(days=1)))
    assert sent[0][1] == expected


async def test_expired_grace_panel_failure_retries_and_alerts_admin_once(db, sent, grace_on):
    grace_on.side_effect = se.RemnawaveError('panel down')

    assert await se.process_event(_event(kind='expired', attempts=0)) is se.EventOutcome.RETRY
    db['claim_subscription_event'].assert_not_awaited()
    assert [tid for tid, _ in sent] == [se.settings.bot.admin_id]

    sent.clear()
    assert await se.process_event(_event(kind='expired', attempts=3)) is se.EventOutcome.RETRY
    assert sent == []  # no repeated admin alerts on later attempts


@pytest.mark.parametrize('result', ['REGULAR', 'NO_RECORD'])
async def test_expired_without_grace_result_falls_back_to_regular_message(db, sent, grace_on, result):
    grace_on.return_value = getattr(se.internal_functions.PanelSyncResult, result)

    await se.process_event(_event(kind='expired'))

    assert sent[0] == (555, loc.auth.msgs['sub_expired'])


async def test_expired_grace_disabled_does_not_touch_panel(db, sent, monkeypatch):
    sync = AsyncMock()
    monkeypatch.setattr(se.internal_functions, 'sync_panel_user', sync)

    await se.process_event(_event(kind='expired'))

    sync.assert_not_awaited()
    assert sent[0] == (555, loc.auth.msgs['sub_expired'])


# --- first connection reminder ------------------------------------------------------

@pytest.fixture
def panel(monkeypatch):
    """Mock the panel lookup of the first connection; the client has never connected by default."""
    mock = AsyncMock(return_value=None)
    monkeypatch.setattr(se, 'get_panel_user_first_connected_at', mock)
    return mock


def _first_connect(**overrides) -> dict:
    return _event(kind='first_connect', fire_at=datetime(2026, 10, 3, 12, 0), **overrides)


async def test_first_connect_reminds_client_and_admin(db, sent, panel):
    assert await se.process_event(_first_connect()) is se.EventOutcome.DONE

    panel.assert_awaited_once_with(REMNAWAVE_UUID)
    db['claim_subscription_event'].assert_awaited_once_with(1)
    assert sent[0] == (555, loc.auth.msgs['first_connect_reminder'].format(url='https://sub.example/abc'))
    assert sent[1] == (se.settings.bot.admin_id, loc.admn.msgs['first_connect_reminder'].format(
        100, ' ivan', 'Ivan', '', 555, 'https://sub.example/abc'))


async def test_first_connect_attaches_subscription_keyboard(db, panel, monkeypatch):
    notify_user = AsyncMock()
    monkeypatch.setattr(se, '_notify_user', notify_user)
    monkeypatch.setattr(se, '_notify_admin', AsyncMock())

    await se.process_event(_first_connect())

    assert notify_user.await_args.kwargs['reply_markup'] is se.user_authorized_kb.my_subscription_inline


async def test_first_connect_already_connected_is_claimed_silently(db, sent, panel):
    panel.return_value = datetime(2026, 10, 2, 9, 0)

    assert await se.process_event(_first_connect()) is se.EventOutcome.DONE

    db['claim_subscription_event'].assert_awaited_once_with(1)
    assert sent == []


async def test_first_connect_inactive_subscription_is_dropped(db, sent, panel):
    assert await se.process_event(_first_connect(subscription_active=False)) is se.EventOutcome.DONE

    db['delete_pending_subscription_event'].assert_awaited_once_with(1)
    db['claim_subscription_event'].assert_not_awaited()
    panel.assert_not_awaited()
    assert sent == []


@pytest.mark.parametrize('overrides', [
    {'remnawave_uuid': None, 'remnawave_subscription_url': None},  # no clients_remnawave row
    {'remnawave_subscription_url': ''},
])
async def test_first_connect_without_panel_subscription_is_skipped_and_logged(db, sent, panel, caplog, overrides):
    with caplog.at_level('WARNING', logger=se.logger.name):
        assert await se.process_event(_first_connect(**overrides)) is se.EventOutcome.DONE

    db['claim_subscription_event'].assert_awaited_once_with(1)
    panel.assert_not_awaited()
    assert sent == []  # neither the client nor the admin
    assert any('no Remnawave subscription' in r.getMessage() for r in caplog.records)


async def test_first_connect_panel_failure_retries(db, sent, panel):
    panel.side_effect = se.RemnawaveError('panel down')

    assert await se.process_event(_first_connect()) is se.EventOutcome.RETRY

    db['claim_subscription_event'].assert_not_awaited()
    assert sent == []


async def test_first_connect_disabled_is_claimed_without_panel_call(db, sent, panel, monkeypatch):
    monkeypatch.setattr(se.settings.remnawave.reminder.first_connection, 'enabled', False)

    assert await se.process_event(_first_connect()) is se.EventOutcome.DONE

    db['claim_subscription_event'].assert_awaited_once_with(1)
    panel.assert_not_awaited()
    assert sent == []


@pytest.mark.parametrize('overrides', [
    {'price': 0},                                          # free subscription
    {'expiration_date': datetime(2026, 12, 10, 12, 0)},  # renewed since scheduling
])
async def test_first_connect_ignores_free_and_stale_checks(db, sent, panel, overrides):
    await se.process_event(_first_connect(**overrides))

    assert sent[0][0] == 555


async def test_first_connect_already_claimed_is_not_sent_again(db, sent, panel):
    db['claim_subscription_event'].return_value = False

    assert await se.process_event(_first_connect()) is se.EventOutcome.DONE
    assert sent == []
