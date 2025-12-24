#!/usr/bin/env bash
set -euo pipefail

alembic upgrade head
exec gunicorn -k uvicorn.workers.UvicornWorker -w "${GUNICORN_WORKERS:-3}" -b 0.0.0.0:8000 app.main:app

