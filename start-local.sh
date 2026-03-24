#!/bin/bash

set -euo pipefail

ROOT_DIR=$(cd "$(dirname "$0")" && pwd)
PORT=${PORT:-8000}

cd "$ROOT_DIR/app"
npm run build

cd "$ROOT_DIR/backend"
exec python3 -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
