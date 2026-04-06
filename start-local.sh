#!/bin/bash

set -euo pipefail

ROOT_DIR=$(cd "$(dirname "$0")" && pwd)
HOST=${HOST:-0.0.0.0}
PORT=${PORT:-8000}
SKIP_BUILD=${SKIP_BUILD:-0}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-build)
      SKIP_BUILD=1
      shift
      ;;
    --host)
      HOST="$2"
      shift 2
      ;;
    --port)
      PORT="$2"
      shift 2
      ;;
    --python-bin)
      PYTHON_BIN="$2"
      shift 2
      ;;
    *)
      echo "错误: 未知参数 $1"
      exit 1
      ;;
  esac
done

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

case "${SKIP_BUILD,,}" in
  1|true|yes)
    if [[ ! -f "$ROOT_DIR/app/dist/index.html" ]]; then
      echo "错误: 已跳过前端构建，但未找到预构建的 app/dist/index.html。"
      exit 1
    fi
    ;;
  *)
    cd "$ROOT_DIR/app"
    npm run build
    ;;
esac

cd "$ROOT_DIR/backend"
exec "$PYTHON" -m uvicorn main:app --host "$HOST" --port "$PORT"
