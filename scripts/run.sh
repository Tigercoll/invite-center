#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

exec granian \
  --interface asgi \
  --host "${AUTH_CENTER_HOST:-0.0.0.0}" \
  --port "${AUTH_CENTER_PORT:-8010}" \
  app.main:app
