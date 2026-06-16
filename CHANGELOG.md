# Change Log
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2026-06-16
Aiogram 3.27, Python 3.12 and Remnawave Panel migration 🎉

### Added
#### Remnawave Panel
- [`95669d6`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/95669d6), [`7ae1513`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/7ae1513), [`6eba0d1`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/6eba0d1), [`196dbe1`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/196dbe1), [`56355c0`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/56355c0) — add Remnawave Panel SDK client, service layer, `clients_remnawave` and `remnawave_internal_squads` DB tables
- [`b20ffe5`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/b20ffe5), [`20e4458`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/20e4458), [`95147bc`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/95147bc) — add migration scripts to transfer existing clients to Remnawave and sync internal squads
- [`6e088a1`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/6e088a1) — sync `expire_at` to Remnawave Panel on subscription extension
- [`2d5a09b`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/2d5a09b) — add inbound torrent-blocker webhook receiver from Remnawave Panel
- [`386039a`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/386039a) — add HTTP retries for Remnawave SDK calls
- [`c986228`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/c986228) — add max available devices count to subscription account view

#### Payments
- [`7ee8728`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/7ee8728), [`de064f5`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/de064f5), [`a773038`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/a773038) — add multi-provider payments module with YooMoney and YooKassa providers, inbound webhook listener and APScheduler reconciler
- [`fb07edf`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/fb07edf) — add DB schema migrations for multi-provider payments
- [`7afd1c4`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/7afd1c4), [`3c81425`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/3c81425) — add payment fiscalization via «Мой налог» (`nalogo` SDK) with per-provider toggles and optional receipt URL in user notification
- [`6340ca5`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/6340ca5) — move from months-based to 30-days-based subscription pricing
- [`0f2dedc`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/0f2dedc) — add minimal-price payment option for test users

#### Infrastructure
- [`9b01f81`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/9b01f81) — add Dynaconf + Pydantic config layer with typed `Settings` and `TGBOT_` env prefix
- [`d84f48e`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/d84f48e), [`cb206c8`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/cb206c8) — add Redis `RedisStorage` FSM backend and Redis container
- [`f24347a`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/f24347a) — add asyncpg connection pool (min=1, max=10)
- [`35dabf8`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/35dabf8) — add safe message delivery factory (`safe_deliver` + `safe_delete_message`)
- [`f8db23f`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/f8db23f) — add GFS backup rotation and `RotatingFileHandler` for logs
- [`44f816d`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/44f816d) — add SOCKS5 proxy support for Telegram API
- [`79575fc`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/79575fc) — add GitLab CI/CD pipelines, migrate from Jenkins

#### Admin
- [`80a90c9`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/80a90c9) — add admin broadcast command with FSM reset and keyboard
- [`496e04c`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/496e04c) — add payment provider info to admin successful-payment notification

#### Other
- [`9d2f63a`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/9d2f63a), [`56ae7ed`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/56ae7ed) — add soft-migration messages for users transitioning from 3X-UI to Remnawave
- [`7595202`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/7595202), [`f9b2874`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/f9b2874) — add DB migrations directory structure and one-off supportive scripts

### Changed
#### Dependencies
- [`550a8f6`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/550a8f6), [`c104b73`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/c104b73) — upgrade aiogram to 3.27.0
- [`340d3b0`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/340d3b0) — upgrade Python to 3.12

#### Registration & account
- [`7b1c9b6`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/7b1c9b6) — drop platform/OS/ChatGPT steps from registration, provision user in Remnawave Panel on sign-up
- [`f30f57a`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/f30f57a) — replace inline skip button with reply keyboard in registration flow
- [`a60efc5`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/a60efc5) — replace configs distribution menu with «My subscription» subscription view

#### Payments & scheduler
- [`f073b52`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/f073b52) — drop config rebroadcast from scheduler, keep subscription notifications only
- [`185079f`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/185079f) — refactor promocodes validation and usage
- [`0a47acc`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/0a47acc) — spread env variables across multiple `.env` files

#### Infrastructure
- [`ea27a37`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/ea27a37) — move PostgreSQL to vanilla official image without custom build
- [`8c40f99`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/8c40f99) — move bot to alpine-based Python Docker image
- [`497bbe3`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/497bbe3) — move localization from JSON to YAML format (`ru.yaml` / `en.yaml`)
- numerous `feat(loc)` and `chore(loc)` commits — update UX messages across `ru.yaml` / `en.yaml`

### Fixed
#### Payments & bot
- [`2e73130`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/2e73130) — fix and unify successful payment transaction logic
- [`903ae80`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/903ae80) — fix issues with users on free subscription
- [`5a585f1`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/5a585f1) — add try/except for expiring-subscription notification messages
- [`21d1c18`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/21d1c18) — fix SIGTERM signal handling
- [`362372b`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/362372b) — fix `allowed_updates` registration

#### Admin
- [`44a1770`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/44a1770), [`aff7312`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/aff7312), [`6b317a2`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/6b317a2) — fix admin send-message callback and broadcast function
- [`5d5bb58`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/5d5bb58), [`f2f9371`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/f2f9371) — fix admin callback message split and paddings
- [`3958f84`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/3958f84) — add missing HTML escape in admin output
- [`3aabd42`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/3aabd42) — fix crash on `None` referral promo in admin
- [`3cfc419`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/3cfc419) — fix admin command output overflow by adding pagination

#### Promocodes & other
- [`0e4e356`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/0e4e356) — fix client unable to enter own referral promo code
- [`5d17596`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/5d17596) — fix invalid promocode usage for unauthorized users
- [`78e73e2`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/78e73e2) — disable `parse_mode` for g4f LLM answers

### Removed
- [`4765c74`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/4765c74) — remove legacy 3X-UI features: handlers, services, UI; drop DB tables (`configurations`, `server_inbounds`, `servers`, `configurations_protocols`) and enums (`fileTypeEnum`, `osEnum`)
- [`8c6560d`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/8c6560d), [`ac534a9`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/ac534a9) — remove legacy config-request keyboards and orphaned localization keys
- [`fcd95e0`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/fcd95e0) — remove unused `sync_internal_squads_from_panel` (YAGNI)
- [`9f54061`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/9f54061) — remove stale admin commands
- [`8206e6e`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/8206e6e) — remove stale dependencies from pyproject.toml
- [`d8bfe62`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/d8bfe62) — remove one-off scripts
- [`bb2cc2d`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/bb2cc2d), [`c2019cb`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/c2019cb) — remove old promocodes

## [1.0.3] - 2025-11-29
Fix annoying bugs

### Added
- [`469f3bc`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/469f3bc) — add Poetry package manager

### Changed
- [`5e9244f`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/5e9244f) — update PostgreSQL version to 17.7
- [`5e9244f`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/5e9244f) — update PostgreSQL Dockerfile
- [`469f3bc`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/469f3bc) — update telegram-bot Dockerfile

### Fixed
- [`9e94475`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/9e94475) — fix telegram_file_id VARCHAR size
- [`9e94475`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/9e94475) — fix expired subscription renew bug
- [`9e94475`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/9e94475) — fix sending message to everyone error

## [1.0.2] - 2024-02-07

### Added
- [`ced7b04`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/ced7b04) - add to logs information about clients with expiring subscription
- [`f111d62`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/f111d62) - add /clients [-h] command

### Changed
- [`6cf3249`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/6cf3249) - update manual for XTLS IOS configuration. Now using Streisand instead of FoXray
- [`50feb95`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/50feb95) - update notification messages for clients with expiring subscription
- [`f08c7b3`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/f08c7b3) - update message during bot restart by /start command

### Fixed
- [`ce1723f`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/ce1723f) - fix desperate situation during registration when users enter /start command


## [1.0.1] - 2024-01-31

### Added
- [`33f67e3`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/33f67e3) - add middleware for clients with not activated subscription
- [`2243709`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/2243709) - add deletion of successful payment message after checking payments

### Changed
- [`3d828f1`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/3d828f1) - add GIFs to README
- [`29c9b84`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/29c9b84), [`a20bcf7`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/a20bcf7) - update messages in bot

### Fixed
- [`ac66fcc`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/ac66fcc) - fix showing user configs via username in bot
- [`e410535`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/e410535) - fix showing logs parse_mode in bot
- [`26f6c2f`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/26f6c2f) - fix throwing exception during referral reward checking
- [`eee65f5`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/eee65f5) - update incorrect messages in bot


## [1.0.0] - 2024-01-23
Release! 🥂

### Added
- [`5cf7909`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/5cf7909) - add feature to execute SQL-queries inside the bot
- [`ec2dee9`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/ec2dee9) - add feature to show logs inside the bot

### Changed
- [`d0b07e9`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/d0b07e9) - add more unobtrusive reminders about the need to renew subscription
- [`9b780cc`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/9b780cc) - clear database structure

### Fixed
- [`68e1c0a`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/68e1c0a) - fix inability send photos with default bot settings
- [`1e5c58c`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/1e5c58c) - make logging more pure
- [`723fdb0`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/723fdb0) - remove content protection for configurations


## [1.0.0-rc] - 2024-01-19
Go into production! 🎊

### Added
- [`c091170`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/c091170), [`e65ca2a`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/e65ca2a), [`2d0b003`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/2d0b003) - add example config files
- [`c9611b7`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/c9611b7) - add middleware texts

### Changed
- [`72c43bf`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/72c43bf) - add more information to README

### Fixed
- [`99d3676`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/99d3676) - fix unparsed HTML-tags in localization

## [0.2.1] - 2024-01-18
Make project readable for people!

### Changed
- [`fb07d33`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/fb07d33), [`ea1ac6d`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/ea1ac6d), [`84f41c6`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/84f41c6), [`e3e853e`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/e3e853e), [`f512a3e`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/f512a3e), [`4f335b9`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/4f335b9), [`a0ed273`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/a0ed273), [`3136bc5`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/3136bc5), [`cde47d0`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/cde47d0) - add instructions to README

## [0.2.0] - 2024-01-17

### Added
- [`379c9db`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/379c9db) - add lacking texts
- [`93b574f`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/93b574f) - add configuration instructions
- add link to telegram channel

### Changed
- [`f1d1f2a`](https://github.com/exmanka/ksiVPN-telegram-bot/commit/f1d1f2a) - add new images

## [0.1.0] - 2024-01-16
Initial public release! 🎉
