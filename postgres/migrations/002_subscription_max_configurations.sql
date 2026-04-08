BEGIN;

ALTER TABLE subscriptions
    ADD COLUMN max_configurations SMALLINT NOT NULL DEFAULT 5;

COMMIT;
