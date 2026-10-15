#!/usr/bin/env bash
# PostToolUse hook: format the file Claude Code just edited/wrote, by extension.
# Each formatter is optional: if it is not installed the file is left as is.
set -uo pipefail

command -v jq >/dev/null 2>&1 || exit 0
file=$(jq -r '.tool_input.file_path // empty')
[[ -n "$file" && -f "$file" ]] || exit 0

has() { command -v "$1" >/dev/null 2>&1; }

case "$file" in
  *.py) has ruff && ruff format --quiet "$file" ;;
  *.go) has gofmt && gofmt -w "$file" ;;
  *.rs) has rustfmt && rustfmt --quiet "$file" ;;
  *.c|*.cc|*.cpp|*.h|*.hpp) has clang-format && clang-format -i "$file" ;;
  *.sh) has shfmt && shfmt -w "$file" ;;
  *.js|*.jsx|*.ts|*.tsx|*.css|*.scss|*.json|*.vue|*.svelte)
    if [[ -x "$CLAUDE_PROJECT_DIR/node_modules/.bin/prettier" ]]; then
      "$CLAUDE_PROJECT_DIR/node_modules/.bin/prettier" --write --log-level warn "$file"
    fi ;;
esac
exit 0
