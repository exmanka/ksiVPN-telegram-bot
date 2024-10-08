#!/bin/bash


echo "Running script for creating scheduler for daily database backups:"
echo "- starting cron service"
service cron start
echo "- adding cron job to schedule database backups"
(echo "55 19 * * * pg_dump -U $POSTGRES_USER --no-password --clean --if-exists --format=plain $POSTGRES_DB | gzip > /var/lib/postgresql/backups/db-backup.gz") | crontab -
echo "- executing something important for postgres container integrity"
exec "$@"