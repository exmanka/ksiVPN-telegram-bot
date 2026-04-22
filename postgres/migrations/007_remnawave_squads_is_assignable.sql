-- Add is_assignable flag to remnawave_internal_squads.
--
-- Purpose: separate "synced from panel" (is_active) from "eligible for
-- random assignment to new users" (is_assignable).
-- Use-case: test/admin squads exist in the panel and should stay synced,
-- but must NOT be randomly assigned to regular bot clients.
--
-- Default TRUE preserves current behaviour for all existing rows.

ALTER TABLE remnawave_internal_squads
    ADD COLUMN is_assignable BOOLEAN NOT NULL DEFAULT TRUE;
