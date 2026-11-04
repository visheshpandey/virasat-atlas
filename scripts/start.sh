#!/bin/sh
# Container start: seed demo data if the database is empty, then serve on $PORT (Render sets it).
set -e
python scripts/seed.py --if-empty
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
