CREATE TABLE clients (
	id SERIAL PRIMARY KEY,
	name VARCHAR(64) NOT NULL,
	surname VARCHAR(64),
	username VARCHAR(33),
	telegram_id BIGINT NOT NULL UNIQUE,
	register_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
	used_ref_promo_id INT
);
INSERT INTO clients (name, surname, username, telegram_id, register_date)
VALUES('Michael', NULL, NULL, 467321357, 'EPOCH');


CREATE INDEX clients_idx
ON clients(telegram_id);


CREATE TABLE subscriptions (
	id SMALLSERIAL PRIMARY KEY,
	price INT NOT NULL,
	title VARCHAR(32) NOT NULL,
	description VARCHAR(128),
	max_configurations SMALLINT NOT NULL DEFAULT 5,
	-- Subscription type that invitees receive via this user's referral promo code.
	-- Populated after self-insert; updated via ALTER TABLE below.
	ref_provided_sub_id SMALLINT NOT NULL DEFAULT 1
);
INSERT INTO subscriptions (price, title, description, max_configurations, ref_provided_sub_id)
VALUES(199, 'Standard subscription', 'Here is standard subscription description.', 3, 1);
INSERT INTO subscriptions (price, title, description, max_configurations, ref_provided_sub_id)
VALUES(75, 'Low-cost subscription', 'Here is low-cost subscription description.', 3, 2);
-- Add FK after both rows exist (self-referential constraint requires target rows to be present).
ALTER TABLE subscriptions
    ADD CONSTRAINT subscriptions_ref_provided_sub_id_fkey
    FOREIGN KEY (ref_provided_sub_id) REFERENCES subscriptions(id) ON DELETE RESTRICT;


CREATE TABLE clients_subscriptions (
	client_id INT UNIQUE NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
	sub_id SMALLINT NOT NULL REFERENCES subscriptions(id) ON DELETE CASCADE,
	paid_days_counter INT NOT NULL DEFAULT 0,
	expiration_date TIMESTAMP NOT NULL
);
INSERT INTO clients_subscriptions(client_id, sub_id, paid_days_counter, expiration_date)
VALUES(1, 1, 300, TIMESTAMP '2030-01-01 00:00');


-- Upcoming expiration events (7d/3d/1d reminders, expiration) and «first connection»
-- reminders (``first_connect``) per client.
-- ``for_expiration`` is the expiration_date snapshot an event was computed from.
-- ``first_connect`` rows are never deleted by the bot: their presence marks a client
-- whose reminder set has already been scheduled.
CREATE TABLE subscription_events (
	id BIGSERIAL PRIMARY KEY,
	client_id INT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
	kind VARCHAR(16) NOT NULL,
	fire_at TIMESTAMP NOT NULL,
	for_expiration TIMESTAMP NOT NULL,
	attempts SMALLINT NOT NULL DEFAULT 0,
	created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
	done_at TIMESTAMP
);

CREATE INDEX subscription_events_pending_idx
ON subscription_events(fire_at) WHERE done_at IS NULL;

CREATE INDEX subscription_events_client_pending_idx
ON subscription_events(client_id) WHERE done_at IS NULL;

CREATE INDEX subscription_events_first_connect_idx
ON subscription_events(client_id) WHERE kind = 'first_connect';


-- One-row table filled by the bot on startup from settings.remnawave.reminder.first_connection:
-- delays of the «first connection» reminders, counted from subscription activation.
CREATE TABLE subscription_events_settings (
	id BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (id),
	first_connect_delays INTERVAL[] NOT NULL DEFAULT ARRAY[INTERVAL '48 hours']
);
INSERT INTO subscription_events_settings DEFAULT VALUES;


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

CREATE TRIGGER clients_subscriptions_expiration_events
AFTER INSERT OR UPDATE OF expiration_date ON clients_subscriptions
FOR EACH ROW EXECUTE FUNCTION clients_subscriptions_expiration_changed();


CREATE OR REPLACE FUNCTION create_ref_promocode() RETURNS text
AS $$
DECLARE
    ref_promo text;
    done boolean;
BEGIN
    done := false;
    WHILE NOT done LOOP
        ref_promo := 'REF'||upper(substring(md5(''||now()::text||random()::text) for 7));
        done := NOT exists(SELECT 1 FROM promocodes_ref WHERE phrase=ref_promo);
    END LOOP;
    RETURN ref_promo;
END;
$$ LANGUAGE PLPGSQL VOLATILE;


CREATE TABLE promocodes_ref (
	id SERIAL PRIMARY KEY,
	phrase VARCHAR(10) UNIQUE NOT NULL DEFAULT create_ref_promocode(),
	client_creator_id INT UNIQUE NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
	provided_sub_id SMALLINT NOT NULL REFERENCES subscriptions(id) ON DELETE CASCADE,
	bonus_time INTERVAL NOT NULL DEFAULT INTERVAL '30 days'
);
INSERT INTO promocodes_ref(client_creator_id, provided_sub_id)
VALUES(1, 2);


CREATE TABLE promocodes_global (
	id SMALLSERIAL PRIMARY KEY,
	phrase VARCHAR(32) UNIQUE NOT NULL,
	expiration_date TIMESTAMP NOT NULL,
	remaining_activations INT NOT NULL,
	bonus_time INTERVAL NOT NULL
);
INSERT INTO promocodes_global(phrase, expiration_date, remaining_activations, bonus_time)
VALUES('GLOBAL_PROMO_EXAMPLE', TIMESTAMP '2030-01-01', 3, INTERVAL '30 days');


CREATE TABLE clients_promo_global (
	client_id INT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
	promocode_id SMALLINT NOT NULL REFERENCES promocodes_global(id) ON DELETE CASCADE,
	date_of_entry TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);


CREATE TABLE promocodes_local (
	id SMALLSERIAL PRIMARY KEY,
	phrase VARCHAR(32) UNIQUE NOT NULL,
	expiration_date TIMESTAMP NOT NULL,
	provided_sub_id SMALLINT REFERENCES subscriptions(id) ON DELETE CASCADE,
	bonus_time INTERVAL NOT NULL
);
INSERT INTO promocodes_local(phrase, expiration_date, provided_sub_id, bonus_time)
VALUES('LOCAL_PROMO_EXAMPLE', TIMESTAMP '2030-01-01', 2, INTERVAL '30 days');


CREATE TABLE clients_promo_local (
	accessible_client_id INT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
	promocode_id SMALLINT NOT NULL REFERENCES promocodes_local(id) ON DELETE CASCADE,
	date_of_entry TIMESTAMP DEFAULT NULL
);
INSERT INTO clients_promo_local(accessible_client_id, promocode_id)
VALUES(1, 1);


CREATE TABLE payments (
	id BIGSERIAL PRIMARY KEY,
	client_id INT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
	sub_id SMALLINT NOT NULL REFERENCES subscriptions(id) ON DELETE CASCADE,
	price DECIMAL(6, 2) NOT NULL,
	days_number SMALLINT NOT NULL,
	is_successful BOOLEAN NOT NULL DEFAULT FALSE,        -- legacy mirror of status='succeeded'; kept for compat
	telegram_message_id INT,
	date_of_initiation TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
	provider VARCHAR(32) NOT NULL,                       -- 'yoomoney' | 'yookassa' | ...
	external_id VARCHAR(128),                            -- provider-side payment id (NULL until create_invoice succeeds)
	status VARCHAR(16) NOT NULL DEFAULT 'pending',       -- pending | succeeded | failed | expired
	paid_at TIMESTAMP,
	updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
	raw_payload JSONB,                                   -- webhook body or last get_status response
	fiscal_receipt_url VARCHAR(256)                      -- public «Мой налог» print URL (NULL if fiscalization disabled or failed)
);

CREATE UNIQUE INDEX payments_provider_external_id_uniq
	ON payments(provider, external_id)
	WHERE external_id IS NOT NULL;

CREATE INDEX payments_pending_reconciler_idx
	ON payments(provider, date_of_initiation)
	WHERE status = 'pending';


CREATE TABLE settings (
	client_id INT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
	sub_expiration_in_1d BOOLEAN NOT NULL DEFAULT TRUE,
	sub_expiration_in_3d BOOLEAN NOT NULL DEFAULT TRUE,
	sub_expiration_in_7d BOOLEAN NOT NULL DEFAULT TRUE,
	chatgpt_mode BOOLEAN NOT NULL DEFAULT FALSE
);
INSERT INTO settings(client_id)
VALUES(1);


CREATE TABLE clients_remnawave (
	client_id INT UNIQUE NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
	remnawave_uuid UUID UNIQUE NOT NULL,
	remnawave_subscription_url TEXT NOT NULL,
	grace_started_at TIMESTAMP,
	pre_grace_internal_squads UUID[],
	pre_grace_external_squad_uuid UUID,
	created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
	updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX clients_remnawave_client_id_idx
ON clients_remnawave(client_id);


CREATE TABLE remnawave_internal_squads (
	id SMALLSERIAL PRIMARY KEY,
	squad_uuid UUID UNIQUE NOT NULL,
	name VARCHAR(64) NOT NULL,
	is_active BOOLEAN NOT NULL DEFAULT TRUE,      -- synced from panel; FALSE = squad no longer exists in panel
	is_assignable BOOLEAN NOT NULL DEFAULT TRUE,  -- eligible for random assignment to new users; set FALSE for test/admin squads
	created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
	updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO remnawave_internal_squads(squad_uuid, name)
VALUES('62965f73-f945-4c49-8803-8db86ff69fe8', 'basic');
