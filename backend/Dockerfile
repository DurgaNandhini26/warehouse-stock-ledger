FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app
COPY docker-entrypoint.sh ./
RUN chmod +x docker-entrypoint.sh && useradd --create-home appuser
USER appuser

EXPOSE 8000
# Migrates, seeds an empty database (if SEED_ON_START=true), then starts the API on $PORT.
ENTRYPOINT ["./docker-entrypoint.sh"]
