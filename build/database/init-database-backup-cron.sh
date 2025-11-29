#!/usr/bin/env bash

# Set strict mode for script
set -euo pipefail

# Set colors for logging
LOG_COLOR="\e[95m"
LOG_COLOR_CLEAR="\e[0m"

# Start cron service
echo -e "${LOG_COLOR}[init-database-backup-cron.sh] Running script for creating scheduler for daily database backups${LOG_COLOR_CLEAR}"
echo -e "${LOG_COLOR}[init-database-backup-cron.sh] Starting cron service${LOG_COLOR_CLEAR}"
service cron start

# Add cron job for daily database backups at 19:55
echo -e "${LOG_COLOR}[init-database-backup-cron.sh] Adding cron job to schedule database backups${LOG_COLOR_CLEAR}"
(echo "55 19 * * * pg_dump -U $POSTGRES_USER --no-password --clean --if-exists --format=plain $POSTGRES_DB | gzip > /var/lib/postgresql/backups/db-backup.gz") | crontab -
echo -e "${LOG_COLOR}[init-database-backup-cron.sh] Executing Postgres entrypoint${LOG_COLOR_CLEAR}"
echo
exec docker-entrypoint.sh "$@"