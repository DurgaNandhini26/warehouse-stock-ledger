#!/bin/sh
# Run the backend test suite and write the coverage summary to backend/coverage.txt.
set -e
cd "$(dirname "$0")/../backend"
PY="${PYTHON:-python}"
if [ -x .venv/bin/python ]; then PY=.venv/bin/python; fi
if [ -x .venv/Scripts/python.exe ]; then PY=.venv/Scripts/python.exe; fi
"$PY" -m pytest -p no:warnings --cov=app --cov-report=term-missing --cov-report=html | tee coverage.txt
