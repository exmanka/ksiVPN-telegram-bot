"""Push-based subscription expiration events.

The schedule lives in ``subscription_events`` and is owned by a trigger on
``clients_subscriptions.expiration_date`` (``postgres/migrations/013_subscription_events.sql``):
every change of the date rebuilds the client's pending events and fires
``pg_notify('subscription_events', client_id)``.

:class:`SubscriptionEventsWorker` keeps a single timer armed to the nearest
``fire_at``:

* ``_listen_loop`` holds a dedicated LISTEN connection and wakes the timer on
  every NOTIFY (and after every reconnect, since notifications sent while the
  connection was down are lost);
* ``_run_loop`` processes due events, then sleeps until the next ``fire_at`` or
  a wake-up, whichever comes first. Sleep is capped by ``SAFETY_CAP_SECONDS`` —
  the safety net for a lost NOTIFY, same role as the payment reconciler plays
  for missed payment webhooks.

Events are claimed (``done_at``) before user-visible side effects, so a message
is delivered at most once. An event whose ``for_expiration`` snapshot differs
from the current ``expiration_date`` is stale (the date changed after it was
scheduled) and is claimed without effect.
"""
import asyncio
import html
import logging
from datetime import timedelta
from enum import Enum

import asyncpg

from src.config import settings
from src.database import connection, subscription_events_db
from src.runtime import bot
from src.services import internal_functions, localization as loc
from src.services.date_formatting import format_localized_bonus_days, format_localized_datetime
from src.services.remnawave_service import RemnawaveError


logger = logging.getLogger(__name__)

SAFETY_CAP_SECONDS = 900            # max sleep between DB checks if NOTIFY is lost
BATCH_LIMIT = 100                   # due events fetched per query
RETRY_DELAY_SECONDS = 60            # postpone of an event whose handler failed
ERROR_BACKOFF_SECONDS = 30          # run-loop sleep after a DB error
LISTENER_HEALTHCHECK_SECONDS = 300  # ping of the idle LISTEN connection (catches half-open TCP)
LISTENER_BACKOFF_MAX_SECONDS = 60   # max delay between LISTEN reconnect attempts


class EventOutcome(Enum):
    """What the worker should do with an event after its handler ran."""
    DONE = 'done'    # event was claimed (or skipped); nothing left to do
    RETRY = 'retry'  # handler failed before claiming; postpone and try again


# kind -> (settings column that toggles the reminder, localization key)
_REMINDERS: dict[str, tuple[str, str]] = {
    'remind_7d': ('sub_expiration_in_7d', 'sub_expires_7d'),
    'remind_3d': ('sub_expiration_in_3d', 'sub_expires_3d'),
    'remind_1d': ('sub_expiration_in_1d', 'sub_expires_1d'),
}


async def _admin_client_args(event: asyncpg.Record) -> tuple:
    """Positional args shared by the admin notification templates: (client_id, username, name, surname, telegram_id)."""
    return (
        event['client_id'],
        await internal_functions.format_none_string(event['username']),
        event['name'],
        await internal_functions.format_none_string(event['surname']),
        event['telegram_id'],
    )


async def _notify_user(telegram_id: int, text: str) -> None:
    await internal_functions.safe_deliver(
        lambda: bot.send_message(telegram_id, text),
        telegram_id=telegram_id,
    )


async def _notify_admin(text: str) -> None:
    admin_id = settings.bot.admin_id
    await internal_functions.safe_deliver(
        lambda: bot.send_message(admin_id, text),
        telegram_id=admin_id,
    )


async def _handle_reminder(event: asyncpg.Record) -> EventOutcome:
    settings_column, loc_key = _REMINDERS[event['kind']]
    # A missing settings row (NULL) falls back to the column default, which is TRUE.
    if event[settings_column] is False:
        await subscription_events_db.claim_subscription_event(event['id'])
        return EventOutcome.DONE

    if not await subscription_events_db.claim_subscription_event(event['id']):
        return EventOutcome.DONE

    logger.info('Subscription event %s (%s): notifying client %s',
                event['id'], event['kind'], event['telegram_id'])
    await _notify_user(event['telegram_id'], loc.auth.msgs[loc_key])
    await _notify_admin(loc.admn.msgs[loc_key].format(*await _admin_client_args(event)))
    return EventOutcome.DONE


async def _enter_grace(event: asyncpg.Record) -> EventOutcome | None:
    """Move the panel user into the «Telegram-only» grace period.

    Returns None when the client gets no grace after all (not provisioned in the panel, or the
    event fired after the grace window already closed) so the caller falls back to the regular
    «subscription expired» flow.
    """
    try:
        result = await internal_functions.sync_panel_user(event['client_id'])
    except RemnawaveError as exc:
        # The panel already expired the user at expireAt: no access at all until this succeeds.
        logger.error('Subscription event %s: failed to start grace for client %s (attempt %s): %s',
                     event['id'], event['client_id'], event['attempts'] + 1, exc)
        if event['attempts'] == 0:
            await _notify_admin(loc.admn.msgs['grace_sync_failed'].format(
                *await _admin_client_args(event), html.escape(str(exc))))
        return EventOutcome.RETRY

    if result is not internal_functions.PanelSyncResult.GRACE:
        return None

    grace_days = settings.remnawave.grace.days
    grace_until = event['expiration_date'] + timedelta(days=grace_days)
    # No follow-up event for the end of grace: the panel expires the user at expireAt on its own,
    # and the client already knows the grace length from this message.
    if not await subscription_events_db.claim_subscription_event(event['id']):
        return EventOutcome.DONE

    logger.info('Subscription event %s (expired): client %s is in grace until %s',
                event['id'], event['telegram_id'], grace_until)
    await _notify_user(event['telegram_id'], loc.auth.msgs['sub_expired_grace'].format(
        days=format_localized_bonus_days(timedelta(days=grace_days)),
    ))
    subscription_url = event['remnawave_subscription_url'] or 'N/A'
    await _notify_admin(loc.admn.msgs['sub_expired_grace'].format(
        *await _admin_client_args(event), subscription_url, format_localized_datetime(grace_until)))
    return EventOutcome.DONE


async def _handle_expired(event: asyncpg.Record) -> EventOutcome:
    if settings.remnawave.grace.enabled:
        outcome = await _enter_grace(event)
        if outcome is not None:
            return outcome

    if not await subscription_events_db.claim_subscription_event(event['id']):
        return EventOutcome.DONE

    logger.info('Subscription event %s (expired): notifying client %s',
                event['id'], event['telegram_id'])
    await _notify_user(event['telegram_id'], loc.auth.msgs['sub_expired'])
    # Remnawave expires the panel user at expire_at on its own — no panel call here.
    subscription_url = event['remnawave_subscription_url'] or 'N/A'
    await _notify_admin(loc.admn.msgs['sub_expired'].format(*await _admin_client_args(event), subscription_url))
    return EventOutcome.DONE


_HANDLERS = {
    'remind_7d': _handle_reminder,
    'remind_3d': _handle_reminder,
    'remind_1d': _handle_reminder,
    'expired': _handle_expired,
}


async def process_event(event: asyncpg.Record) -> EventOutcome:
    """Validate a due event against the current subscription state and dispatch it to its handler."""
    if event['for_expiration'] != event['expiration_date']:
        # The date changed after this event was scheduled; the trigger has already
        # scheduled fresh events for the new date. Possible only in a narrow race
        # (the trigger deletes pending events of the old date).
        logger.info('Subscription event %s (%s) is stale: scheduled for %s, current expiration %s',
                    event['id'], event['kind'], event['for_expiration'], event['expiration_date'])
        await subscription_events_db.claim_subscription_event(event['id'])
        return EventOutcome.DONE

    if event['price'] <= 0:
        # Free subscriptions get no expiration notifications.
        await subscription_events_db.claim_subscription_event(event['id'])
        return EventOutcome.DONE

    handler = _HANDLERS.get(event['kind'])
    if handler is None:
        logger.error('Subscription event %s has unknown kind %r — skipping', event['id'], event['kind'])
        await subscription_events_db.claim_subscription_event(event['id'])
        return EventOutcome.DONE

    return await handler(event)


def compute_sleep_timeout(delay: float | None, cap: float = SAFETY_CAP_SECONDS) -> float:
    """Seconds to sleep until the next event: ``delay`` clamped to ``[0, cap]``; ``cap`` when nothing is scheduled."""
    if delay is None:
        return cap
    return max(0.0, min(delay, cap))


class SubscriptionEventsWorker:
    """Single in-process consumer of ``subscription_events`` (see module docstring)."""

    def __init__(self) -> None:
        self._wakeup = asyncio.Event()
        self._tasks: list[asyncio.Task] = []
        self._listener_conn: asyncpg.Connection | None = None

    async def start(self) -> None:
        self._tasks = [
            asyncio.create_task(self._listen_loop(), name='subscription-events-listener'),
            asyncio.create_task(self._run_loop(), name='subscription-events-runner'),
        ]
        logger.info('Subscription events worker has been started')

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []
        await self._close_listener()
        logger.info('Subscription events worker has been stopped')

    def _on_notify(self, _conn, _pid, _channel, _payload) -> None:
        self._wakeup.set()

    async def _close_listener(self) -> None:
        conn, self._listener_conn = self._listener_conn, None
        if conn is None or conn.is_closed():
            return
        try:
            await conn.close(timeout=5)
        except Exception:
            conn.terminate()

    async def _listen_loop(self) -> None:
        backoff = 1
        while True:
            try:
                lost = asyncio.Event()
                conn = await connection.create_listener_connection()
                self._listener_conn = conn
                conn.add_termination_listener(lambda _conn: lost.set())
                await conn.add_listener(subscription_events_db.SUBSCRIPTION_EVENTS_CHANNEL, self._on_notify)
                logger.info('Listening for subscription events on channel %r',
                            subscription_events_db.SUBSCRIPTION_EVENTS_CHANNEL)
                backoff = 1
                # Notifications sent while we were not listening are lost — recompute the timer.
                self._wakeup.set()

                while not lost.is_set():
                    try:
                        await asyncio.wait_for(lost.wait(), timeout=LISTENER_HEALTHCHECK_SECONDS)
                    except TimeoutError:
                        await asyncio.wait_for(conn.fetchval('SELECT 1'), timeout=10)
                logger.warning('Subscription events LISTEN connection lost; reconnecting')
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception('Subscription events LISTEN connection failed; reconnecting in %ss', backoff)
            finally:
                await self._close_listener()

            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, LISTENER_BACKOFF_MAX_SECONDS)

    async def _drain_due_events(self) -> None:
        while True:
            events = await subscription_events_db.fetch_due_subscription_events(BATCH_LIMIT)
            for event in events:
                try:
                    outcome = await process_event(event)
                except Exception:
                    logger.exception('Subscription event %s (%s) failed; retrying in %ss',
                                     event['id'], event['kind'], RETRY_DELAY_SECONDS)
                    outcome = EventOutcome.RETRY
                if outcome is EventOutcome.RETRY:
                    # No-op for an already claimed event (WHERE done_at IS NULL).
                    await subscription_events_db.postpone_subscription_event(event['id'], RETRY_DELAY_SECONDS)
            if len(events) < BATCH_LIMIT:
                return

    async def run_once(self) -> float:
        """Process due events and return how long to sleep before the next iteration."""
        # Cleared before reading the DB: a NOTIFY arriving meanwhile re-sets it,
        # so the following wait returns immediately instead of missing the change.
        self._wakeup.clear()
        try:
            await self._drain_due_events()
            delay = await subscription_events_db.get_next_subscription_event_delay()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception('Subscription events tick failed; retrying in %ss', ERROR_BACKOFF_SECONDS)
            return ERROR_BACKOFF_SECONDS
        return compute_sleep_timeout(delay)

    async def _run_loop(self) -> None:
        while True:
            timeout = await self.run_once()
            try:
                await asyncio.wait_for(self._wakeup.wait(), timeout=timeout)
            except TimeoutError:
                pass


worker = SubscriptionEventsWorker()
