FROM postgres:17.7

# Add new language locale
ARG ADDITIONAL_LANGUAGE="ru_RU"
RUN localedef -i "$ADDITIONAL_LANGUAGE" -c -f UTF-8 -A /usr/share/locale/locale.alias "$ADDITIONAL_LANGUAGE".UTF-8

ENV LANG="en_US.utf8"

# Install cron
RUN apt-get update && \
    apt-get install --no-install-recommends -y cron && \
    rm -rf /var/lib/apt/lists/*

# Add initialization SQL script and backup cron script
COPY init-database.sql /docker-entrypoint-initdb.d/init-database.sql
COPY init-database-backup-cron.sh /usr/local/bin/init-database-backup-cron.sh
RUN chmod +x /usr/local/bin/init-database-backup-cron.sh

# Set entrypoint and cmd
ENTRYPOINT [ "init-database-backup-cron.sh" ]
CMD [ "docker-entrypoint.sh", "postgres" ]
