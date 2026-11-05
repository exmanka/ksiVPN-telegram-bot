-- Migration 014: «Telegram-only» grace period state per panel user
--
-- When a paid subscription expires the bot moves the Remnawave user to the
-- Telegram-only internal squad (and optionally to the grace external squad)
-- and extends the panel's expireAt by settings.remnawave.grace.days. A payment
-- or promo code later restores what the user had before.
--
-- The "before" state is captured from the panel at the moment grace starts
-- (an admin may have changed squads by hand), so the bot stores it here:
--
--   * grace_started_at              — NULL = not in grace
--   * pre_grace_internal_squads     — activeInternalSquads before grace
--   * pre_grace_external_squad_uuid — externalSquadUuid before grace (NULL = had none)
--
-- No backfill: every existing user is outside grace.

BEGIN;

ALTER TABLE clients_remnawave
    ADD COLUMN grace_started_at TIMESTAMP,
    ADD COLUMN pre_grace_internal_squads UUID[],
    ADD COLUMN pre_grace_external_squad_uuid UUID;

COMMIT;
