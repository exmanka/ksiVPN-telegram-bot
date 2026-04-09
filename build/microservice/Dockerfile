FROM python:3.12.13-alpine3.23 AS builder

ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=true \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_CACHE_DIR=/var/cache/pypoetry

# Build-time toolchain needed for packages that fall back to sdist (e.g. g4f
# transitive deps, asyncpg, pydantic-core on unsupported wheel platforms)
RUN apk add --no-cache build-base libffi-dev openssl-dev

# Install Poetry via pip (no curl script needed)
RUN pip install --no-cache-dir poetry

WORKDIR /app

# Install dependencies into an in-project venv at /app/.venv
COPY build/microservice/pyproject.toml build/microservice/poetry.lock ./
RUN poetry install --no-ansi


FROM python:3.12.13-alpine3.23

# User settings
ARG TGBOT_UID=1666
ARG TGBOT_GID=1666
ARG TGBOT_HOME="/home/ksivpn-tgbot"

# Create user and group (Alpine uses busybox addgroup/adduser, not useradd)
RUN addgroup -g ${TGBOT_GID} ksivpn-tgbot && \
    adduser -D -u ${TGBOT_UID} -G ksivpn-tgbot -h ${TGBOT_HOME} -s /bin/sh ksivpn-tgbot

# Runtime system dependencies:
#   postgresql17-client — pg_dump used by scheduler.send_database_backup
#   tzdata              — required for TGBOT_TZ / APScheduler zoneinfo lookups
#   ca-certificates     — TLS for Telegram API, YooMoney, Redis TLS
RUN apk add --no-cache \
    curl \
    postgresql17-client \
    tzdata \
    ca-certificates

# Activate the venv built in the builder stage
COPY --from=builder --chown=ksivpn-tgbot:ksivpn-tgbot /app/.venv ${TGBOT_HOME}/.venv
ENV PATH="${TGBOT_HOME}/.venv/bin:$PATH"

# Set working directory
WORKDIR ${TGBOT_HOME}

# Copy source
COPY --chown=ksivpn-tgbot:ksivpn-tgbot . .
RUN rm -rf build/

# Pre-create volume mount points with correct ownership so Docker initialises
# named volumes with the right permissions.
RUN install -d -o ksivpn-tgbot -g ksivpn-tgbot \
    ${TGBOT_HOME}/logs \
    ${TGBOT_HOME}/backups

# Set user
USER ksivpn-tgbot

# Set entrypoint and cmd
ENTRYPOINT ["python"]
CMD ["main.py"]
