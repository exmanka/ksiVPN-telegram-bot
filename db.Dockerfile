FROM postgres:14.9

ARG ADDITIONAL_LANGUAGE
RUN localedef -i $ADDITIONAL_LANGUAGE -c -f UTF-8 -A /usr/share/locale/locale.alias $ADDITIONAL_LANGUAGE.UTF-8

ENV LANG en_US.utf8
