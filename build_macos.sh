#!/usr/bin/env bash
# One-shot macOS build for the EigenVib flasher GUI → dist/EigenVib-Flasher.app
# Mirrors build_windows.bat. Run from the repo root: ./build_macos.sh
set -euo pipefail
cd "$(dirname "$0")"

# Pick a python WITH tkinter (the GUI needs it). Homebrew python often lacks _tkinter.
PYL=""
for p in python3.12 python3 /usr/bin/python3; do
  if command -v "$p" >/dev/null 2>&1 && "$p" -c 'import tkinter' >/dev/null 2>&1; then PYL="$p"; break; fi
done
[ -n "$PYL" ] || { echo "!! no python with tkinter found (try: brew install python-tk)"; exit 1; }
echo "== [1/4] build venv ($PYL) =="
rm -rf build_venv build dist
"$PYL" -m venv build_venv
VPY="build_venv/bin/python"

echo "== [2/4] deps =="
# esptool PINNED to 4.x — the flasher builds 4.x-style argv (write_flash, --flash_mode);
# esptool 5.x renamed those to hyphens and would break flashing.
"$VPY" -m pip install --quiet --upgrade pip
"$VPY" -m pip install --quiet "esptool==4.12.0" "pyserial>=3.5" "segno>=1.5" "pillow>=10.2" pyinstaller

echo "== [3/4] build EigenVib-Flasher.app =="
# --collect-data esptool is REQUIRED: bundles the ESP32-S3 flasher-stub JSONs, else the
# frozen app dies with "Flasher stub data is missing for ESP32-S3".
"$VPY" -m PyInstaller --onefile --windowed --clean --noconfirm \
  --name "EigenVib-Flasher" \
  --collect-data esptool \
  --add-data "firmware:firmware" \
  eigenvib_flasher_gui.py

echo "== [4/4] done =="
xattr -dr com.apple.quarantine "dist/EigenVib-Flasher.app" 2>/dev/null || true
codesign --force --deep --sign - "dist/EigenVib-Flasher.app" 2>/dev/null || true
echo "   built: dist/EigenVib-Flasher.app"
echo "   (firmware bundled from ./firmware — run ./refresh_firmware.sh first if the .bin changed)"
