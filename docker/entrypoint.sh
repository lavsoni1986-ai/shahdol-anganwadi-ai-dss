#!/bin/sh
# docker/entrypoint.sh — Expands $PORT for exec-form CMD compatibility
set -e
PORT="${PORT:-8080}"
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT}"