#!/bin/bash

set -euo pipefail

ROOT_DIR=$(cd "$(dirname "$0")" && pwd)
HOST=${HOST:-0.0.0.0}
PORT=${PORT:-8000}

if [[ -n "${PYTHON_BIN:-}" ]]; then
  PYTHON="$PYTHON_BIN"
elif [[ -x "$ROOT_DIR/.venv/Scripts/python.exe" ]]; then
  PYTHON="$ROOT_DIR/.venv/Scripts/python.exe"
elif [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
  PYTHON="$ROOT_DIR/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON=python3
elif command -v python >/dev/null 2>&1; then
  PYTHON=python
else
  echo "错误: 未找到可用的 Python 解释器。"
  exit 1
fi

cd "$ROOT_DIR/app"
npm run build

cd "$ROOT_DIR/backend"
exec "$PYTHON" -m uvicorn main:app --host "$HOST" --port "$PORT"
