#!/bin/bash
# Deploy a tagged release on the Jetson. Runs as the app user, no sudo.
#
#   deploy/jetson/update.sh <tag>        (normally via scripts/deploy_jetson.sh)
#
# Steps: fetch the tag -> pytest in a staging worktree -> back up code + DB ->
# check out the tag -> pip install if requirements changed -> HUP gunicorn ->
# health check. Any failure after the checkout restores the backup and HUPs again.
# .env, instance/, uploads/, models/ and .venv/ are git-ignored and never touched.
set -Eeuo pipefail

TAG="${1:-}"
APP_DIR="${APP_DIR:-$HOME/tpt-rfid}"
DEPLOY_ROOT="${DEPLOY_ROOT:-$HOME/tpt-deploys}"
SERVICE=tpt-rfid
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:5000/api/devices/status}"
PY="$APP_DIR/.venv/bin/python"

say() { printf '\n== %s\n' "$*"; }
die() { printf 'update.sh: %s\n' "$*" >&2; exit 1; }

[[ "$TAG" =~ ^v[0-9]{4}\.[0-9]{2}\.[0-9]{2}(\.[0-9]+)?$ ]] || die "bad tag '$TAG' (want vYYYY.MM.DD[.N])"
cd "$APP_DIR"

say "fetch $TAG"
git worktree prune
git fetch -q --tags origin
NEW="$(git rev-parse --verify -q "refs/tags/$TAG^{commit}")" || die "tag $TAG not found on origin"
git merge-base --is-ancestor "$NEW" origin/main || die "$TAG is not on origin/main"
PREV="$(git rev-parse HEAD)"

RUN="$DEPLOY_ROOT/$(date +%Y%m%d-%H%M%S)-$TAG"
mkdir -p "$RUN"
exec > >(tee "$RUN/update.log") 2>&1
echo "prev $PREV, new $NEW, run dir $RUN"

say "tests in staging worktree"
# Jetson git is 2.17: no "worktree add -q", no "worktree remove".
git worktree add --detach "$RUN/stage" "$NEW" >/dev/null 2>&1
(cd "$RUN/stage" && "$PY" -m pytest -q -p no:cacheprovider 2>&1 | tail -5; exit "${PIPESTATUS[0]}") \
    || die "tests failed for $TAG; nothing installed"
rm -rf "$RUN/stage" && git worktree prune

say "backup (code tree + DB)"
tar -czf "$RUN/code-before.tgz" --exclude=.git --exclude=.venv --exclude=instance \
    --exclude=uploads --exclude=models --exclude=__pycache__ .
git status --short > "$RUN/status-before.txt"
TPT_RFID_BACKUP_DIR="$RUN" TPT_RFID_BACKUP_KEEP=1 "$PY" deploy/jetson/backup_db.py

main_pid() { systemctl show -p MainPID --value "$SERVICE"; }
restarts() { systemctl show -p NRestarts --value "$SERVICE"; }

reload_and_check() {
    local pid before
    pid="$(main_pid)"
    [ "$pid" != "0" ] || { echo "service not running"; return 1; }
    before="$(restarts)"
    kill -HUP "$pid"
    for _ in $(seq 1 30); do
        sleep 2
        if curl -fsS -o /dev/null --max-time 5 "$HEALTH_URL"; then
            [ "$(systemctl is-active "$SERVICE")" = active ] || return 1
            [ "$(main_pid)" = "$pid" ] || { echo "master restarted"; return 1; }
            [ "$(restarts)" = "$before" ] || { echo "NRestarts changed"; return 1; }
            echo "healthy: master $pid, workers $(pgrep -P "$pid" | tr '\n' ' ')"
            return 0
        fi
    done
    echo "no healthy response from $HEALTH_URL"
    return 1
}

rollback() {
    trap - ERR
    set +e
    say "ROLLBACK to $PREV + backed-up tree"
    git checkout -q -f --detach "$PREV"
    tar -xzf "$RUN/code-before.tgz"
    if ! git diff --quiet "$NEW" "$PREV" -- 'requirements*.txt'; then
        "$PY" -m pip install -q -r requirements.txt -r requirements-cv.txt -r requirements-nfc.txt || true
    fi
    reload_and_check || echo "ROLLBACK UNHEALTHY: check 'systemctl status $SERVICE'"
    die "deploy of $TAG failed and was rolled back (log: $RUN/update.log)"
}

say "install $TAG"
trap rollback ERR
git checkout -q -f --detach "$NEW"
if ! git diff --quiet "$PREV" "$NEW" -- 'requirements*.txt'; then
    say "requirements changed: pip install"
    "$PY" -m pip install -q -r requirements.txt -r requirements-cv.txt -r requirements-nfc.txt
fi
"$PY" -m py_compile app.py config.py utils/*.py routes/*.py

say "reload"
reload_and_check
trap - ERR

LEFT="$(git status --short)"
if [ -n "$LEFT" ]; then
    echo "untracked/modified files left in the tree (not removed):"
    echo "$LEFT"
fi
say "deployed $TAG ($NEW). Kiosk browser may need Ctrl+Shift+R for new JS/CSS."
