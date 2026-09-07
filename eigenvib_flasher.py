#!/usr/bin/env python3
"""EigenVib production flasher — flash a sensor node, capture its QR secret, save <code>.png.

Cross-platform (Windows / macOS / Linux). It bundles the firmware images, so a flashing
station needs neither ESP-IDF nor the project checkout. Packaged with PyInstaller it
becomes ONE self-contained executable (Python + esptool + the .bin images inside) that an
operator just double-clicks / runs — see README.md.

Flow (ADR-FW-0003, Model A):
  erase → flash the bundled images → reset → capture the one-time
      PROV node_id=<uuid> psk=<hex> code=<XXXXXX>
  line the firmware prints on first boot → write  <QR_DIR>/<code>.png  (a QR of
  {"v":1,"nid":<node_id>,"psk":<base64url(PSK)>}) + append it to registry.csv.

Deps: esptool, pyserial, segno  (see requirements.txt). segno is optional if `qrencode`
is on PATH (dev fallback); the bundled build always includes segno.
"""
import argparse
import base64
import datetime
import json
import os
import re
import sys
import time

import serial
import serial.tools.list_ports

CHIP = "esp32s3"
# Flash layout (from the project's build/flasher_args.json — stable for this project).
IMAGES = [("0x0", "bootloader.bin"), ("0x8000", "partition-table.bin"), ("0x10000", "sensor_node.bin")]
QR_SVG_MM = 20.0  # physical size (mm) of the vector QR for the enclosure sticker
PROV_RE = re.compile(r"PROV node_id=(\S+)\s+psk=([0-9a-fA-F]{64})\s+code=(\S+)")
# USB vendor ids we accept: Espressif native USB-JTAG, CP210x, CH34x, FTDI.
KNOWN_VIDS = {0x303A, 0x10C4, 0x1A86, 0x0403}


def firmware_dir():
    """Where the .bin images live — bundled by PyInstaller, else next to this script."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "firmware")


def find_port(explicit):
    if explicit:
        return explicit
    cands = []
    for p in serial.tools.list_ports.comports():
        dev, desc = (p.device or ""), (p.description or "")
        if p.vid in KNOWN_VIDS or "usbmodem" in dev or "USB" in desc or "CP210" in desc or "CH34" in desc:
            cands.append(dev)
    if not cands:
        raise SystemExit("No serial port found — plug the node in via USB (or pass --port COMx / /dev/...).")
    if len(cands) > 1:
        print(f"  ! multiple ports {cands} — using {cands[0]} (override with --port)")
    return cands[0]


def _esptool(argv):
    import esptool
    esptool.main(argv)


def flash(port, fw, erase):
    # esptool 4.x uses underscore subcommands/options (erase_flash, write_flash,
    # --flash_mode, default_reset …). Hyphenated aliases only exist in esptool 5.x.
    if erase:
        print("• erasing flash …")
        _esptool(["--chip", CHIP, "--port", port, "erase_flash"])
    argv = ["--chip", CHIP, "--port", port, "--baud", "460800",
            "--before", "default_reset", "--after", "no_reset",
            "write_flash", "--flash_mode", "dio", "--flash_size", "16MB", "--flash_freq", "40m"]
    for off, name in IMAGES:
        argv += [off, os.path.join(fw, name)]
    print("• flashing firmware …")
    _esptool(argv)


def reset_and_capture(port, timeout):
    """Reset the node into the app and read serial for the one-time PROV line."""
    s = serial.Serial(port, 115200, timeout=0.5)
    s.dtr = False          # IO0 high → normal boot (not download)
    s.rts = True           # EN low → reset
    time.sleep(0.15)
    s.rts = False          # EN high → run app
    end = time.time() + timeout
    try:
        while time.time() < end:
            try:
                ln = s.readline().decode("utf-8", "ignore")
            except Exception:
                continue
            m = PROV_RE.search(ln)
            if m:
                return m.group(1), m.group(2), m.group(3)
        return None
    finally:
        s.close()


def reset_node(port):
    """Reset the node into the app (no serial capture). Used after a firmware-only
    update (erase=False): the node reboots into the new app keeping its NVS
    identity/PSK, so there is no new PROV line to wait for."""
    s = serial.Serial(port, 115200, timeout=0.5)
    try:
        s.dtr = False      # IO0 high → normal boot (not download)
        s.rts = True       # EN low → reset
        time.sleep(0.15)
        s.rts = False      # EN high → run app
    finally:
        s.close()


def make_qr(node_id, psk_hex, code, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    psk = bytes.fromhex(psk_hex)
    if len(psk) != 32:
        raise SystemExit("captured PSK is not 32 bytes")
    # The 6-char code goes INTO the QR payload so the wizard reads it from the scanned
    # QR (always correct) instead of the OS-cached BLE advertised name.
    payload = json.dumps({"v": 1, "nid": node_id,
                          "psk": base64.urlsafe_b64encode(psk).decode().rstrip("="),
                          "code": code},
                         separators=(",", ":"))
    png = os.path.join(out_dir, f"{code}.png")
    svg = os.path.join(out_dir, f"{code}.svg")
    # Render the QR, then caption the PNG with the human-readable code so the printed /
    # engraved sticker shows BOTH the machine QR and the 6-char code (e.g. "896 GFE").
    # Also emit a VECTOR SVG sized for the 20x20 mm enclosure sticker (crisp at any size).
    try:
        import segno
        from io import BytesIO
        qr = segno.make(payload, error="m")
        buf = BytesIO()
        qr.save(buf, kind="png", scale=8, border=2)
        buf.seek(0)
        _caption_png(buf, code, png)
        # Composite: QR + the human-readable 3+3 code below it, all within QR_SVG_MM.
        _qr_svg_captioned(qr, code, svg, QR_SVG_MM)
    except ImportError:
        import subprocess
        subprocess.run(["qrencode", "-o", png, "-m", "2", "-s", "8", payload], check=True)
        subprocess.run(["qrencode", "-t", "SVG", "-o", svg, "-m", "2", payload], check=True)
    return png, payload


def _qr_svg_captioned(qr, code, out_path, mm):
    """Write a vector SVG of `mm`×`mm` (for the enclosure sticker): the QR on top and the
    human-readable 3+3 code (e.g. '971 KKJ') centred underneath, so a person can identify
    the node by eye. `qr` is a segno QRCode. Dark modules are emitted as one path; the QR
    fills the square minus a thin strip reserved for the code line."""
    matrix = [list(row) for row in qr.matrix]  # data modules (no quiet zone)
    n = len(matrix)
    border = 2
    total = n + 2 * border
    text_h = 3.0                    # mm reserved for the code line
    unit = (mm - text_h) / total    # mm per module (incl. quiet zone)
    parts = []
    for r, row in enumerate(matrix):
        for c, dark in enumerate(row):
            if dark:
                x = (c + border) * unit
                y = (r + border) * unit
                parts.append(f"M{x:.3f} {y:.3f}h{unit:.3f}v{unit:.3f}h{-unit:.3f}z")
    code_fmt = f"{code[:3]} {code[3:]}" if len(code) == 6 else code
    svg = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{mm}mm" height="{mm}mm" '
        f'viewBox="0 0 {mm} {mm}">'
        f'<rect width="{mm}" height="{mm}" fill="#ffffff"/>'
        f'<path fill="#000000" d="{"".join(parts)}"/>'
        f'<text x="{mm / 2:.2f}" y="{mm - 0.7:.2f}" text-anchor="middle" '
        f'font-family="monospace" font-weight="bold" font-size="2.6" '
        f'letter-spacing="0.2" fill="#000000">{code_fmt}</text>'
        '</svg>'
    )
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(svg)


def _caption_png(qr_buf, code, out_path):
    """Write the QR (from a PNG byte buffer) with the code printed large underneath.
    Falls back to the bare QR PNG if Pillow is not installed."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        with open(out_path, "wb") as f:
            f.write(qr_buf.getvalue())
        return
    qr = Image.open(qr_buf).convert("RGB")
    W, H = qr.size
    try:
        font = ImageFont.load_default(size=max(30, W // 8))  # scalable default (Pillow ≥10.1)
    except TypeError:
        font = ImageFont.load_default()
    text = f"{code[:3]} {code[3:]}" if len(code) == 6 else code  # "896 GFE"
    d0 = ImageDraw.Draw(qr)
    bbox = d0.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    pad = max(10, W // 22)
    out = Image.new("RGB", (W, H + th + 2 * pad), "white")
    out.paste(qr, (0, 0))
    ImageDraw.Draw(out).text(((W - tw) // 2 - bbox[0], H + pad - bbox[1]), text,
                             fill="black", font=font)
    out.save(out_path)


def append_registry(out_dir, node_id, code):
    reg = os.path.join(out_dir, "registry.csv")
    new = not os.path.exists(reg)
    with open(reg, "a", encoding="utf-8") as f:
        if new:
            f.write("timestamp,node_id,code\n")
        f.write(f"{datetime.datetime.now().isoformat(timespec='seconds')},{node_id},{code}\n")


def main():
    ap = argparse.ArgumentParser(description="EigenVib flasher — flash a node + capture its QR.")
    ap.add_argument("--port", help="serial port (auto-detected if omitted)")
    ap.add_argument("--qr-dir", default=os.path.join(os.getcwd(), "qr_codes"),
                    help="where to write <code>.png + registry.csv (default ./qr_codes)")
    ap.add_argument("--no-erase", action="store_true",
                    help="firmware update only: keep the node's identity + PSK (no new QR)")
    ap.add_argument("--timeout", type=int, default=30, help="seconds to wait for the PROV line")
    a = ap.parse_args()

    fw = firmware_dir()
    missing = [n for _, n in IMAGES if not os.path.exists(os.path.join(fw, n))]
    if missing:
        raise SystemExit(f"missing firmware images {missing} in {fw}")

    port = find_port(a.port)
    print(f"Node on {port}\n")
    flash(port, fw, erase=not a.no_erase)

    print("• booting + capturing the QR secret …")
    got = reset_and_capture(port, a.timeout)
    if not got:
        if a.no_erase:
            print("\n✓ Firmware updated. No PROV line (identity/PSK preserved) — the existing QR still applies.")
            return 0
        raise SystemExit("No PROV line captured within timeout. Retry (some boards need the RESET/EN button tapped).")

    node_id, psk_hex, code = got
    png, payload = make_qr(node_id, psk_hex, code, a.qr_dir)
    append_registry(a.qr_dir, node_id, code)

    print("\n" + "=" * 60)
    print(f"✓ DONE   code = {code}   (advertises as SNSR-{code})")
    print(f"  node_id : {node_id}")
    print(f"  QR      : {png}")
    print(f"  print this QR and stick it on the enclosure. registry.csv updated.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
