#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

ruff check .
.venv/bin/python -m pytest -q
# Optional: also run tests on another interpreter, e.g. PY38=/path/to/venv38/bin/python
if [ -n "${PY38:-}" ]; then
  "$PY38" -m pytest -q
fi
