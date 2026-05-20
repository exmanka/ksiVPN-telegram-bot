-- Migration 010: payments multi-provider support
--
-- Adds columns for multi-provider payment routing: provider name, provider-side
-- external_id, status enum, paid_at, updated_at, raw_payload (for webhook bodies).
--
-- Existing column is_successful is preserved for backward compatibility with
-- code paths that have not yet migrated to the status enum. New write paths
-- update BOTH columns. A separate cleanup migration may drop is_successful
-- once the refactor lands fully.
--
-- Backfill assumes all existing payments came from YooMoney with label = payments.id
-- (matches current aiomoney behavior — see src/services/aiomoney.py).
--
-- Run with the bot stopped to avoid races on payments INSERT/UPDATE during ALTER TABLE.
-- One-way migration: rollback only via pg_dump taken before this script.

BEGIN;

ALTER TABLE payments
    ADD COLUMN provider     VARCHAR(32),
    ADD COLUMN external_id  VARCHAR(128),
    ADD COLUMN status       VARCHAR(16) NOT NULL DEFAULT 'pending',
    ADD COLUMN paid_at      TIMESTAMP,
    ADD COLUMN updated_at   TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ADD COLUMN raw_payload  JSONB;

-- Backfill: every existing payment is a YooMoney P2P transfer with label == payments.id
UPDATE payments
SET provider    = 'yoomoney',
    external_id = id::text,
    status      = CASE WHEN is_successful THEN 'succeeded' ELSE 'pending' END,
    paid_at     = CASE WHEN is_successful THEN date_of_initiation ELSE NULL END;

ALTER TABLE payments ALTER COLUMN provider SET NOT NULL;

-- Idempotency: a webhook for (provider, external_id) maps to exactly one payment row.
-- Partial index — external_id is briefly NULL between INSERT and provider.create_invoice.
CREATE UNIQUE INDEX payments_provider_external_id_uniq
    ON payments(provider, external_id)
    WHERE external_id IS NOT NULL;

-- Reconciler lookup: recent pending payments by provider.
CREATE INDEX payments_pending_reconciler_idx
    ON payments(provider, date_of_initiation)
    WHERE status = 'pending';

COMMIT;
