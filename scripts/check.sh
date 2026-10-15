#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

# Lint only the new test files for now: the rest of the repo has known
# pre-existing ruff issues that are fixed in a later step.
ruff check --target-version py38 tests
.venv/bin/python -m pytest -q
