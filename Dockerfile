FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    git libopus0 libsodium23 fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml README.md ./
COPY bot ./bot
COPY alembic ./alembic
COPY alembic.ini ./
RUN pip install . && useradd --create-home --uid 10001 meyaya \
    && mkdir -p /app/logs /app/bot/private \
    && chown -R meyaya:meyaya /app
USER meyaya
CMD ["python", "-m", "bot.main"]
