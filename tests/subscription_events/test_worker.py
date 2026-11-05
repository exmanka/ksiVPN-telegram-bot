"""Contract of the subscription events worker (``src.services.subscription_events``).

The schedule itself is built by a Postgres trigger and is not tested here.
What we DO test:

- Event validation: stale ``for_expiration`` snapshot, free subscription and
  unknown kind are claimed without notifying anyone.
- Reminders honour the client's notification toggles and are delivered at most
  once (claim before send).
- ``expired`` notifies the client and the admin (with the subscription URL).
- Handler failure → event postponed (RETRY); the loop keeps going.
- Sleep timeout: clamped to ``[0, SAFETY_CAP]``; a wake-up (NOTIFY) cuts the sleep short.
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from src.services import localization as loc
from src.services import subscription_events as se


EXPIRATION = datetime(2026, 11, 10, 12, 0)


def _event(**overrides) -> dict:
    event = {
        'id': 1,
        'client_id': 100,
        'kind': 'remind_1d',
        'fire_at': EXPIRATION,
        'for_expiration': EXPIRATION,
        'attempts': 0,
        'expiration_date': EXPIRATION,
        'telegram_id': 555,
        'name': 'Ivan',
        'surname': None,
        'username': 'ivan',
        'sub_expiration_in_1d': True,
        'sub_expiration_in_3d': True,
        'sub_expiration_in_7d': True,
        'price': 199,
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

    async def fake_notify_user(telegram_id, text):
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
