FROM python:3.12.13-slim-trixie

# User settings
ARG TGBOT_UID=1666
ARG TGBOT_GID=1666
ARG TGBOT_HOME="/home/ksivpn-tgbot"

# Create user, group and home directory
RUN groupadd --gid ${TGBOT_UID} ksivpn-tgbot && \
    useradd --uid ${TGBOT_UID} -g ksivpn-tgbot --home-dir ${TGBOT_HOME} --create-home --shell /bin/bash ksivpn-tgbot

# Poetry environment variables
ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_CACHE_DIR=/var/cache/pypoetry \
    POETRY_HOME=/opt/poetry
ENV PATH="$POETRY_HOME/bin:$PATH"

# Install curl and postgresql-client-17. Debian Trixie ships pg17 in its
# default repos, so no PGDG apt source is needed. pg_dump is used by
# src/services/scheduler.py:send_database_backup to produce nightly DB backups
# delivered to the admin via Telegram.
RUN apt-get update && \
    apt-get install --no-install-recommends -y curl postgresql-client-17 && \
    rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN curl -sSL https://install.python-poetry.org | python3 -

# Set working directory
WORKDIR ${TGBOT_HOME}

# Copy and install dependencies
COPY --chown=ksivpn-tgbot:ksivpn-tgbot build/microservice/pyproject.toml build/microservice/poetry.lock ./
RUN poetry install --no-ansi

# Copy source
COPY --chown=ksivpn-tgbot:ksivpn-tgbot . .

# Set user
USER ksivpn-tgbot

# Set entrypoint and cmd
ENTRYPOINT ["python"]
CMD ["main.py"]
