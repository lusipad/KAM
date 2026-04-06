#!/bin/bash

set -euo pipefail

ROOT_DIR=$(cd "$(dirname "$0")" && pwd)

exec "$ROOT_DIR/start-local.sh" --skip-build "$@"
