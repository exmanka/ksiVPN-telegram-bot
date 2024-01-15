FROM postgres:14.9

ARG ADDITIONAL_LANGUAGE
RUN localedef -i $ADDITIONAL_LANGUAGE -c -f UTF-8 -A /usr/share/locale/locale.alias $ADDITIONAL_LANGUAGE.UTF-8
ENV LANG en_US.utf8

RUN apt-get update && apt-get install cron -y
COPY ./init-database-backup-cron.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/init-database-backup-cron.sh

ENTRYPOINT [ "init-database-backup-cron.sh" ]
CMD ["docker-entrypoint.sh", "postgres"]