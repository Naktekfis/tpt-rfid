# Target platform: NVIDIA Jetson Nano 4GB

Confirmed by the user (2026-10-15): **Jetson Nano 4GB, model P3450 (2019), ARM64/aarch64, official JetPack 4.6.1 image, Ubuntu 18.04 LTS.** This is not the Jetson Orin Nano. About 20–30 GB of free disk is expected.

Lines marked *(verify on device)* come from general knowledge of JetPack 4.6.x and have not been checked on the actual board yet. Run the checks below and update this file with the real output.

## Constraints that shape the code
- **Python**: Ubuntu 18.04 ships Python 3.6 *(verify on device: `python3 --version`)*. The current pins need **≥ 3.8** (Flask 3.0, Flask-SQLAlchemy 3.1, Pillow 10.1). Plan: install `python3.8` + `python3.8-venv` from the Ubuntu 18.04 apt repos and run the app in a 3.8 venv *(verify package availability)*. Keep application code **Python 3.8-compatible**: no `X | Y` unions or `list[str]` evaluated at runtime without `from __future__ import annotations`, no `match`, no `dict | dict`. Current offenders: `utils/cv_handler.py:63` and `utils/cv_handler.py:165`. Lint with `ruff check --target-version py38`.
- **RAM**: 4 GB shared between CPU and GPU. The browser/kiosk shell, Flask, and any CV pipeline all compete for it. Keep one process, avoid heavy frameworks, and measure with `tegrastats`.
- **glibc 2.27 / old GTK/WebKit** *(verify)*: prebuilt binaries that target newer distros may not run. Prefer `manylinux2014_aarch64` Python wheels. Expect to build some packages from source.
- **Database**: SQLite file on local disk (user decision, 2026-10-15). No PostgreSQL on the device.
- **CV** (later, optional): JetPack's OpenCV is built for the system Python 3.6, not for a 3.8 venv *(verify)*. `face_recognition`/dlib must be compiled on the device (slow, uses a lot of memory). Leave CV out of the default install until the core app works.

## App shell (desktop wrapper)
The user wants something light: a web app, possibly wrapped. Recommendation for this board: **run Flask locally and open it in a browser in kiosk mode** (`chromium-browser --kiosk http://127.0.0.1:5000` or Firefox kiosk). It adds no extra runtime. Electron bundles its own Chromium (hundreds of MB of RAM), and recent releases may not support glibc 2.27 *(verify)*. Tauri v2 needs webkit2gtk-4.1, which Ubuntu 18.04 does not ship *(verify)*. Revisit a wrapper only if kiosk mode lacks something concrete.

## Device checks to run first
```bash
cat /etc/nv_tegra_release; uname -a; lsb_release -a
python3 --version; apt-cache policy python3.8 python3.8-venv
free -h; df -h /
lsusb; dmesg | grep -iE 'cp210|ch34|ttyUSB'; ls -l /dev/ttyUSB*
groups   # needs dialout for the reader
which chromium-browser firefox
```
