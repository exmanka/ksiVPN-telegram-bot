-- Migration 013: push-based subscription expiration events
--
-- Replaces the 30-minute APScheduler polling of ``clients_subscriptions`` with
-- an event schedule kept by the database itself:
--
--   * ``subscription_events`` holds one row per upcoming event of a client
--     (7d / 3d / 1d reminders and the expiration itself). ``for_expiration`` is
--     the ``expiration_date`` snapshot the event was computed from — the bot
--     skips an event whose snapshot no longer matches the current date.
--   * ``regenerate_subscription_events`` rebuilds the pending schedule of one
--     client and fires ``pg_notify('subscription_events', client_id)``; the
--     bot's worker LISTENs on that channel and re-arms its single timer to the
--     nearest ``fire_at``. NOTIFY is delivered on COMMIT.
--   * A trigger on ``clients_subscriptions.expiration_date`` calls it on every
--     change, so every writer (payments, promo codes, admin SQL, scripts) keeps
--     the schedule in sync without touching Python. Do NOT write reminder /
--     expiration events from application code.
--
-- Events in the past are never generated: extending by 1 day must not flush
-- stale 7d/3d reminders, and a blank (EPOCH) subscription gets no events.
-- Processed rows keep ``done_at`` for audit and are purged by the bot daily.
-- ``attempts`` counts postponed retries of events whose handler failed.

BEGIN;

CREATE TABLE subscription_events (
    id             BIGSERIAL PRIMARY KEY,
    client_id      INT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    kind           VARCHAR(16) NOT NULL,
    fire_at        TIMESTAMP NOT NULL,
    for_expiration TIMESTAMP NOT NULL,
    attempts       SMALLINT NOT NULL DEFAULT 0,
    created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    done_at        TIMESTAMP
);

CREATE INDEX subscription_events_pending_idx
ON subscription_events(fire_at) WHERE done_at IS NULL;

CREATE INDEX subscription_events_client_pending_idx
ON subscription_events(client_id) WHERE done_at IS NULL;


CREATE OR REPLACE FUNCTION regenerate_subscription_events(p_client_id INT, p_expiration TIMESTAMP) RETURNS void
AS $$
BEGIN
    DELETE FROM subscription_events
    WHERE client_id = p_client_id
      AND done_at IS NULL;

    INSERT INTO subscription_events(client_id, kind, fire_at, for_expiration)
    SELECT p_client_id, e.kind, p_expiration + e.offset_interval, p_expiration
    FROM (VALUES
        ('remind_7d', INTERVAL '-7 days'),
        ('remind_3d', INTERVAL '-3 days'),
        ('remind_1d', INTERVAL '-1 day'),
        ('expired',   INTERVAL '0')
    ) AS e(kind, offset_interval)
    WHERE p_expiration + e.offset_interval > CURRENT_TIMESTAMP;

    PERFORM pg_notify('subscription_events', p_client_id::text);
END;
$$ LANGUAGE PLPGSQL VOLATILE;


CREATE OR REPLACE FUNCTION clients_subscriptions_expiration_changed() RETURNS trigger
AS $$
BEGIN
    IF TG_OP = 'UPDATE' AND NEW.expiration_date IS NOT DISTINCT FROM OLD.expiration_date THEN
        RETURN NULL;
    END IF;
    PERFORM regenerate_subscription_events(NEW.client_id, NEW.expiration_date);
    RETURN NULL;
END;
$$ LANGUAGE PLPGSQL VOLATILE;

CREATE TRIGGER clients_subscriptions_expiration_events
AFTER INSERT OR UPDATE OF expiration_date ON clients_subscriptions
FOR EACH ROW EXECUTE FUNCTION clients_subscriptions_expiration_changed();


-- Backfill the schedule for every currently active subscription.
DO $$
BEGIN
    PERFORM regenerate_subscription_events(client_id, expiration_date)
    FROM clients_subscriptions
    WHERE expiration_date > CURRENT_TIMESTAMP;
END;
$$;

COMMIT;
