-- Migration 008: add ref_provided_sub_id to subscriptions
-- Defines which subscription type invitees receive when a user with this
-- subscription invites someone via a referral promo code.
--
-- Default = 1 (Standard subscription) — safe fallback for any future rows.
-- Run this script on production before deploying the corresponding bot update.

ALTER TABLE subscriptions
    ADD COLUMN ref_provided_sub_id SMALLINT NOT NULL DEFAULT 1
        REFERENCES subscriptions(id) ON DELETE RESTRICT;

-- Populate existing rows (prod data as of 2026-04).
-- id=1  Standard subscription      → invitees get 1 (same)
-- id=2  Oldskull subscription       → invitees get 2 (same discounted tier)
-- id=3  "For the beloved" (free)    → invitees get only 1 (standard, not free)
-- id=4  Oldskull duo                → invitees get 2
-- id=5  Standard duo                → invitees get 2
-- id=6  Oldskull fivesome           → invitees get 2
-- id=7  Oldskull threesome          → invitees get 2
UPDATE subscriptions SET ref_provided_sub_id = 1 WHERE id = 1;
UPDATE subscriptions SET ref_provided_sub_id = 2 WHERE id = 2;
UPDATE subscriptions SET ref_provided_sub_id = 1 WHERE id = 3;
UPDATE subscriptions SET ref_provided_sub_id = 2 WHERE id = 4;
UPDATE subscriptions SET ref_provided_sub_id = 2 WHERE id = 5;
UPDATE subscriptions SET ref_provided_sub_id = 2 WHERE id = 6;
UPDATE subscriptions SET ref_provided_sub_id = 2 WHERE id = 7;
