#!/bin/bash
# Deploy a pushed release tag to the Jetson kiosk.
#
#   scripts/deploy_jetson.sh <tag>      e.g. v2026.10.24.1
#
# Checks that the tag exists locally, is pushed to origin with the same commit and
# is on origin/main, then runs that tag's own deploy/jetson/update.sh on the device
# (staging tests, backup, checkout, HUP, health check, rollback on failure).
# Tagging and pushing are separate steps on purpose: this script never pushes.
set -euo pipefail

TAG="${1:-}"
HOST="${JETSON_HOST:-tpt@10.42.0.14}"
APP_DIR="${JETSON_APP_DIR:-tpt-rfid}"

die() { printf 'deploy_jetson.sh: %s\n' "$*" >&2; exit 1; }

[[ "$TAG" =~ ^v[0-9]{4}\.[0-9]{2}\.[0-9]{2}(\.[0-9]+)?$ ]] || die "usage: $0 vYYYY.MM.DD[.N]"
cd "$(dirname "$0")/.."

LOCAL="$(git rev-parse --verify -q "refs/tags/$TAG^{commit}")" || die "no local tag $TAG"
REMOTE="$(git ls-remote origin "refs/tags/$TAG^{}" | cut -f1)"
[ -n "$REMOTE" ] || REMOTE="$(git ls-remote origin "refs/tags/$TAG" | cut -f1)"
[ "$REMOTE" = "$LOCAL" ] || die "tag $TAG not pushed or differs on origin (git push origin $TAG)"
git fetch -q origin main
git merge-base --is-ancestor "$LOCAL" origin/main || die "$TAG is not on origin/main (push main first)"

echo "Deploying $TAG ($LOCAL) to $HOST:$APP_DIR"
# The script comes from the tag itself, so each deploy runs the reviewed version.
ssh -o BatchMode=yes -o ConnectTimeout=10 "$HOST" "set -e
cd '$APP_DIR'
git fetch -q --tags origin
f=\$(mktemp)
git show 'refs/tags/$TAG:deploy/jetson/update.sh' > \"\$f\"
rc=0
bash \"\$f\" '$TAG' </dev/null || rc=\$?
rm -f \"\$f\"
exit \$rc"
