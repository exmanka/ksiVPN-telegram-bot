-- Migration 009: switch subscription extension from months to fixed days (30/90/365)
-- Aligns subscription extension length: previously make_interval(months => N) gave
-- a calendar-month span (28-31 days, varying by current date). After this migration
-- all renewals use fixed N-day intervals.
--
-- Steps:
--   1. payments: rename months_number → days_number; convert historical values
--      (1→30, 3→90, 12→365; other values ×30 as fallback)
--   2. clients_subscriptions: rename paid_months_counter → paid_days_counter;
--      multiply existing values by 30 (statistical column, ±5 days of imprecision OK)
--   3. promocodes_*: change default INTERVAL '1 month' → '30 days' and update
--      existing rows that hold exactly '1 month' to '30 days'. Custom intervals
--      (e.g. '2 months', '45 days') are NOT touched.
--
-- Run this script on production with the bot stopped (or payment webhooks blocked)
-- to avoid a race during ALTER ... RENAME COLUMN.
-- One-way migration: rollback only via pg_dump taken before this script.

BEGIN;

-- payments: months_number → days_number
ALTER TABLE payments RENAME COLUMN months_number TO days_number;

UPDATE payments
SET days_number = CASE days_number
    WHEN 1 THEN 30
    WHEN 3 THEN 90
    WHEN 12 THEN 365
    ELSE days_number * 30
END;

-- clients_subscriptions: paid_months_counter → paid_days_counter (×30)
ALTER TABLE clients_subscriptions RENAME COLUMN paid_months_counter TO paid_days_counter;

UPDATE clients_subscriptions SET paid_days_counter = paid_days_counter * 30;

-- promocodes: '1 month' DEFAULT → '30 days'; update existing default-valued rows
ALTER TABLE promocodes_ref ALTER COLUMN bonus_time SET DEFAULT INTERVAL '30 days';

UPDATE promocodes_ref    SET bonus_time = INTERVAL '30 days' WHERE bonus_time = INTERVAL '1 month';
UPDATE promocodes_global SET bonus_time = INTERVAL '30 days' WHERE bonus_time = INTERVAL '1 month';
UPDATE promocodes_local  SET bonus_time = INTERVAL '30 days' WHERE bonus_time = INTERVAL '1 month';

COMMIT;
