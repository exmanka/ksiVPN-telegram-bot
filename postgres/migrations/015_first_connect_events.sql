-- Migration 015: «first connection» reminders
--
-- A new client whose subscription becomes active but who never connects to the
-- VPN gets one or more reminders with their subscription link. The schedule is
-- owned by the same trigger as the expiration events (migration 013):
--
--   * Activation = ``expiration_date`` moves from the past (blank EPOCH or an
--     expired date) into the future, or a row is inserted with a future date.
--     On activation the trigger inserts one ``first_connect`` event per delay
--     from ``subscription_events_settings.first_connect_delays``, counted from
--     the activation moment.
--   * A reminder set is scheduled once per client lifetime: a client that has
--     any ``first_connect`` row (pending or done) is not new any more. That's
--     why ``first_connect`` rows are kept by ``regenerate_subscription_events``
--     and never purged by the bot.
--   * ``subscription_events_settings`` is a one-row table the bot fills on
--     startup from ``settings.remnawave.reminder.first_connection`` (an empty
--     array when the feature is disabled). New delays apply to activations that
--     happen after the restart; already scheduled rows keep their ``fire_at``.
--   * Whether the client has connected is checked by the bot at fire time
--     (Remnawave ``userTraffic.firstConnectedAt``), not here.
--
-- Backfill: every existing client gets a processed ``first_connect`` marker, so
-- only clients registered after this migration receive the reminders.

BEGIN;

CREATE TABLE subscription_events_settings (
    id                   BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (id),
    first_connect_delays INTERVAL[] NOT NULL DEFAULT ARRAY[INTERVAL '48 hours']
);
INSERT INTO subscription_events_settings DEFAULT VALUES;

CREATE INDEX subscription_events_first_connect_idx
ON subscription_events(client_id) WHERE kind = 'first_connect';


CREATE OR REPLACE FUNCTION regenerate_subscription_events(p_client_id INT, p_expiration TIMESTAMP) RETURNS void
AS $$
BEGIN
    DELETE FROM subscription_events
    WHERE client_id = p_client_id
      AND done_at IS NULL
      AND kind <> 'first_connect';

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

    -- Activation of a new client: schedule the «first connection» reminders.
    IF NEW.expiration_date > CURRENT_TIMESTAMP
       AND (TG_OP = 'INSERT' OR OLD.expiration_date <= CURRENT_TIMESTAMP)
       AND NOT EXISTS (SELECT 1 FROM subscription_events
                       WHERE client_id = NEW.client_id AND kind = 'first_connect') THEN
        INSERT INTO subscription_events(client_id, kind, fire_at, for_expiration)
        SELECT NEW.client_id, 'first_connect', CURRENT_TIMESTAMP + d, NEW.expiration_date
        FROM subscription_events_settings, unnest(first_connect_delays) AS d;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE PLPGSQL VOLATILE;


-- Existing clients are not new: mark them as processed.
INSERT INTO subscription_events(client_id, kind, fire_at, for_expiration, done_at)
SELECT cs.client_id, 'first_connect', CURRENT_TIMESTAMP, cs.expiration_date, CURRENT_TIMESTAMP
FROM clients_subscriptions AS cs;

COMMIT;
