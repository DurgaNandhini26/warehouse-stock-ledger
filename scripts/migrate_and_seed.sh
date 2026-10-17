#!/bin/sh
# Apply migrations and load sample data into the database named by DATABASE_URL.
# Seeding is skipped when products already exist. Pass --reset to wipe and re-seed.
set -e
cd "$(dirname "$0")/../backend"
PY="${PYTHON:-python}"
if [ -x .venv/bin/python ]; then PY=.venv/bin/python; fi
if [ -x .venv/Scripts/python.exe ]; then PY=.venv/Scripts/python.exe; fi

if [ "$1" = "--reset" ]; then
  "$PY" -m app.cli reset
else
  "$PY" -m app.cli seed
fi
