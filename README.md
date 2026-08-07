# EigenVib production flasher

Flash a sensor node and capture its **QR secret** into `<code>.png` for printing —
cross-platform (Windows / macOS / Linux), self-contained. One tool per node:

```
erase → flash bundled firmware → node first-boot mints PSK+code, prints once over serial
      → capture it → write  qr_codes/<code>.png  + append registry.csv
```

The QR encodes `{"v":1,"nid":<node_id>,"psk":<base64url(PSK)>}`. Print it, stick it on the
enclosure — that's the operator's key to provision the node securely (ADR-FW-0003).

## A. Run as a Python script (dev / your machine)

```bash
pip install -r requirements.txt
python eigenvib_flasher.py                 # auto-detect the node's USB port
python eigenvib_flasher.py --port COM7      # Windows
python eigenvib_flasher.py --qr-dir /path/to/qr_codes
python eigenvib_flasher.py --no-erase       # firmware UPDATE only — keep identity/PSK, no new QR
```
Needs the node on USB. `firmware/` (the 3 `.bin` images) must sit next to the script.

## A2. Run the GUI (one window, no terminal)

`eigenvib_flasher_gui.py` wraps the same flow in a window: auto-detect the port,
press **FLASH**, watch the log, get the QR + 6-char code (saved to the QR folder).

```bash
pip install -r requirements.txt
python eigenvib_flasher_gui.py
```
Same firmware requirement as the CLI. On macOS with the old system Tk 8.5 the inline
QR preview is skipped (the PNG is still saved — use **Open folder**); Tk 8.6+ shows it.

## B. Build ONE self-contained executable (production station)

PyInstaller bundles Python + esptool + segno + the `.bin` images into a single file —
the operator needs nothing installed. **PyInstaller can't cross-compile**: build the
Windows `.exe` on Windows and the macOS binary on macOS (same script).

```bash
pip install -r requirements.txt pyinstaller

# macOS / Linux  (note the ':' in --add-data)
pyinstaller --onefile --name EigenVib-Flasher --add-data "firmware:firmware" eigenvib_flasher.py

# Windows        (note the ';' in --add-data)
pyinstaller --onefile --name EigenVib-Flasher --add-data "firmware;firmware" eigenvib_flasher.py
```

**GUI build** — same, add `--windowed` and point at the GUI script (→ `.app` on macOS,
a console-less `.exe` on Windows):

```bash
# macOS   -> dist/EigenVib-Flasher.app
pyinstaller --onefile --windowed --name EigenVib-Flasher \
    --add-data "firmware:firmware" eigenvib_flasher_gui.py
# Windows -> dist\EigenVib-Flasher.exe
pyinstaller --onefile --windowed --name EigenVib-Flasher ^
    --add-data "firmware;firmware" eigenvib_flasher_gui.py
```
Result: `dist/EigenVib-Flasher` (macOS) / `dist\EigenVib-Flasher.exe` (Windows) — copy it to
the flashing station and run it. QR files land in `qr_codes/` next to where it's run
(override with `--qr-dir`).

> macOS Gatekeeper: an unsigned binary needs a right-click → Open the first time (or
> `xattr -dr com.apple.quarantine EigenVib-Flasher`). For wider distribution, codesign +
> notarize. Windows SmartScreen: "More info → Run anyway" (or sign the exe).

## Refreshing the firmware

After rebuilding the firmware, refresh the bundled images before packaging:

```bash
cp ../../build/sensor_node.bin ../../build/bootloader/bootloader.bin \
   ../../build/partition_table/partition-table.bin firmware/
```
(Or run `./refresh_firmware.sh`.) Then rebuild the executable (section B).

## Output

- `qr_codes/<code>.png` — the QR to print (e.g. `108XTT.png`).
- `qr_codes/registry.csv` — `timestamp,node_id,code` per flashed node (production log).
