#!/usr/bin/env python3
"""Read the firmware version out of sensor_node.bin itself.

ESP-IDF stamps an `esp_app_desc_t` into every app image, and the version field in it
comes from the project's version.txt. So the image carries its own version, and the
flasher does not need to be told what it is bundling — which is the whole point: a
hand-maintained label beside the binary drifts the first time someone forgets to update
it, and we had three such labels disagreeing before this existed.

Layout (esp_app_format/include/esp_app_desc.h), from the start of the .bin:

    0x20  magic_word   u32   0xABCD5432
    0x24  secure_version
    0x28  reserv1[2]
    0x30  version[32]        <- this
    0x50  project_name[32]
    0x70  time[16] / 0x80 date[16] / 0x90 idf_ver[32]

Usage:  python3 fw_version.py [path/to/sensor_node.bin]
"""
import struct
import sys
from pathlib import Path

APP_DESC_OFF = 0x20
APP_DESC_MAGIC = 0xABCD5432
VERSION_OFF = APP_DESC_OFF + 0x10
VERSION_LEN = 32


def firmware_version(bin_path: Path) -> str:
    raw = bin_path.read_bytes()
    if len(raw) < VERSION_OFF + VERSION_LEN:
        raise ValueError(f"{bin_path} is too small to be an ESP-IDF app image")
    (magic,) = struct.unpack("<I", raw[APP_DESC_OFF:APP_DESC_OFF + 4])
    if magic != APP_DESC_MAGIC:
        raise ValueError(
            f"{bin_path} has no app descriptor (magic 0x{magic:08X}, expected "
            f"0x{APP_DESC_MAGIC:08X}) — not an ESP-IDF app image?"
        )
    v = raw[VERSION_OFF:VERSION_OFF + VERSION_LEN].split(b"\0")[0].decode("ascii", "replace")
    if not v:
        raise ValueError(f"{bin_path} carries an empty version — is version.txt set?")
    return v


if __name__ == "__main__":
    p = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name("firmware") / "sensor_node.bin"
    try:
        print(firmware_version(p))
    except Exception as e:  # noqa: BLE001
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
