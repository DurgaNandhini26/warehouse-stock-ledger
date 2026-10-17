#!/bin/sh
set -e

python -m app.cli migrate
if [ "${SEED_ON_START:-false}" = "true" ]; then
  python -m app.cli seed
fi

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --no-access-log --proxy-headers
