#!/usr/bin/env bash
# Development-only walk through the /kiosk states with the mock reader.
#
# Needs a dev server with the debug routes (FLASK_ENV=development,
# RFID_READER_ENABLED=false) and the seed data from seed_database.py.
# Open http://localhost:5000/kiosk in a browser, then run:
#
#   scripts/kiosk_demo.sh            # full walk: present -> session -> borrow -> end -> alarm
#   scripts/kiosk_demo.sh present    # all seeded tags in the field
#   scripts/kiosk_demo.sh session 1  # start a session for student 1
#   scripts/kiosk_demo.sh borrow     # drop Bor Listrik #1 from the field
#   scripts/kiosk_demo.sh end        # POST /api/kiosk/end (with CSRF token)
#   scripts/kiosk_demo.sh alarm      # drop Multimeter Digital #1 while idle
#
# BASE overrides the server URL (default http://localhost:5000).
set -euo pipefail

BASE="${BASE:-http://localhost:5000}"
JAR="$(mktemp)"
trap 'rm -f "$JAR"' EXIT

# Same EPC scheme as seed_database.make_epc(type_index, unit_no).
epc() { printf 'E2000017221101%02X%02X000000' "$1" "$2"; }

# (type index, units) as in seed_database.TOOL_TYPES
UNITS=(0 4 5 3 5 3)

all_epcs() {
    local skip="${1:-}" out=() t u e
    for t in 1 2 3 4 5; do
        for ((u = 1; u <= UNITS[t]; u++)); do
            e="$(epc "$t" "$u")"
            [[ " $skip " == *" $e "* ]] && continue
            out+=("$e")
        done
    done
    local IFS=,
    echo "${out[*]}"
}

BOR1="$(epc 1 1)"
MULTI1="$(epc 2 1)"

get() { curl -fsS "$BASE$1"; echo; }

present() { get "/debug/presence?epcs=$(all_epcs "${1:-}")" >/dev/null; echo "field: all tags${1:+ except $1}"; }

session() { get "/debug/kiosk/identify?student_id=${1:-1}"; }

end_session() {
    local token
    token="$(curl -fsS -c "$JAR" "$BASE/kiosk" | sed -n 's/.*name="csrf-token" content="\([^"]*\)".*/\1/p')"
    curl -sS -b "$JAR" -X POST -H "X-CSRFToken: $token" "$BASE/api/kiosk/end"; echo
}

pause() { echo "... $1"; sleep "$2"; }

case "${1:-walk}" in
    present) present ;;
    session) session "${2:-1}" ;;
    borrow) present "$BOR1" ;;
    end) end_session ;;
    alarm) present "$MULTI1 ${2:-}" ;;
    walk)
        present
        pause "board: everything present (presence needs one round)" 6
        session 1
        pause "session for student 1" 4
        present "$BOR1"
        pause "Bor Listrik #1 leaves the field -> borrowed after the missing delay (~5 s)" 8
        end_session
        pause "summary, then idle" 10
        present "$BOR1 $MULTI1"
        echo "Multimeter Digital #1 leaves while idle -> alarm in ~5 s (30 s grace)."
        echo "Put it back: scripts/kiosk_demo.sh present $BOR1"
        ;;
    *) sed -n '2,15p' "$0"; exit 1 ;;
esac
