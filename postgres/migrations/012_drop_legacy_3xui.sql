-- Migration 012: drop legacy 3X-UI per-configuration schema
--
-- The bot has fully migrated to Remnawave Panel (one subscription_url per user,
-- VPN apps pull their own inbound set from the panel). The pre-Remnawave tables
-- that stored individual configurations, 3X-UI server credentials and
-- protocol/inbound mappings are no longer touched by any Python code:
-- corresponding handlers, services, DB helpers and localization keys are
-- removed in the same change.
--
-- ``subscriptions.max_configurations`` stays — it's still shown in the
-- "Моя подписка" UI as the per-tier device cap.
--
-- Drop order respects FK dependencies (CASCADE would handle it anyway, but
-- explicit order matches the dependency tree):
--   configurations         → references configurations_protocols, servers
--   server_inbounds        → references configurations_protocols, servers
--   servers                → no remaining incoming FKs
--   configurations_protocols
--   fileTypeEnum / osEnum  → used only by ``configurations``

BEGIN;

DROP TABLE IF EXISTS configurations;
DROP TABLE IF EXISTS server_inbounds;
DROP TABLE IF EXISTS servers;
DROP TABLE IF EXISTS configurations_protocols;

DROP TYPE IF EXISTS fileTypeEnum;
DROP TYPE IF EXISTS osEnum;

COMMIT;
