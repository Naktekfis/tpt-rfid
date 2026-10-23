#!/bin/bash
# Standalone physical-test wrapper; never installs application source.
set -euo pipefail
run_dir=${1:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)}
if [ ! -f "$run_dir/scripts/vx6336_acquisition_probe.py" ]; then
    run_dir=$(dirname -- "$run_dir")
fi
probe_python=${VX6336_PROBE_PYTHON:-/home/tpt/tpt-rfid/.venv/bin/python}
probe_port=${VX6336_PROBE_PORT:-/dev/rfid-reader}
restore_needed=0
probe_started=0
restore() {
    exit_code=$?
    trap - EXIT INT TERM
    if [ "$probe_started" = 1 ]; then
        echo 'Probe berhenti. Tunggu 27 detik untuk respons reader yang mungkin tertunda.'
        sleep 27
    fi
    if [ "$restore_needed" = 1 ]; then
        if sudo systemctl start tpt-rfid.service; then
            echo 'Layanan dinyalakan kembali; tunggu startup perangkat selesai.'
            systemctl is-active tpt-rfid.service || exit_code=2
        else
            echo 'PEMULIHAN GAGAL: jalankan sudo systemctl start tpt-rfid.service dan periksa status.' >&2
            exit_code=2
        fi
    elif [ "$probe_started" = 1 ]; then
        echo 'Layanan semula tidak aktif, jadi tetap tidak aktif.'
        echo 'Untuk memakai kiosk lagi: sudo systemctl start tpt-rfid.service'
    fi
    exit "$exit_code"
}
trap restore EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

test -x "$probe_python" || { echo 'Python probe tidak ditemukan.' >&2; exit 2; }
test -f "$run_dir/scripts/vx6336_acquisition_probe.py" || { echo 'Berkas probe tidak ditemukan.' >&2; exit 2; }
test -e "$probe_port" || { echo 'Port reader tidak ditemukan.' >&2; exit 2; }
command -v fuser >/dev/null || { echo 'fuser tidak tersedia; kepemilikan port belum dapat diperiksa.' >&2; exit 2; }
if ! initial_state=$(systemctl show tpt-rfid.service -p ActiveState --value); then
    echo 'Status layanan tidak dapat dibaca; probe dibatalkan.' >&2
    exit 2
fi
case "$initial_state" in
    active|inactive) ;;
    *) echo "Status layanan $initial_state; periksa sebelum uji." >&2; exit 2 ;;
esac
sudo -v
if [ "$initial_state" = active ]; then
    restore_needed=1
    sudo systemctl stop tpt-rfid.service
else
    echo 'Layanan sudah tidak aktif. Lanjut setelah memastikan port bebas.'
fi
if ! current_state=$(systemctl show tpt-rfid.service -p ActiveState --value); then
    echo 'Status setelah persiapan tidak dapat dibaca; probe dibatalkan.' >&2
    exit 2
fi
if [ "$current_state" != inactive ]; then
    echo "Layanan belum berhenti (status $current_state); probe dibatalkan." >&2
    exit 2
fi
if sudo fuser "$probe_port" >/dev/null 2>&1; then
    echo 'Port masih dimiliki proses lain; probe dibatalkan.' >&2
    exit 2
else
    owner_check=$?
    if [ "$owner_check" -ne 1 ]; then
        echo 'Pemeriksaan port gagal; probe dibatalkan.' >&2
        exit 2
    fi
fi
result_file=$(mktemp "$run_dir/results.XXXXXX")
echo "Hasil agregat: $result_file"
probe_started=1
"$probe_python" "$run_dir/scripts/vx6336_acquisition_probe.py" --port "$probe_port" --trials 5 --window 10 | tee "$result_file"
