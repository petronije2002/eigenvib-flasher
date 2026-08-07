# CLAUDE CODE — START HERE: build & fix the EigenVib Windows flasher

> **You are Claude Code running on the user's Windows PC. This single file is
> self‑contained** — the brief, the full spec, the intended build, the known blockers, and
> the **complete source of every file inlined in the Appendix**. The person who wrote this
> tool (on macOS) cannot access this machine; you can. **Your job: produce a working
> `EigenVib-Flasher.exe` on THIS PC and confirm it launches**, diagnosing the real local
> blocker (see §5) rather than guessing.
>
> The actual files are also present in this folder (so `build_windows.bat` works directly);
> the Appendix lets you regenerate any file if it is missing or altered. The only thing not
> inlined is the binary firmware in `firmware/` (three `.bin` images) — those must be
> bundled unchanged.

---

## 1. What this tool is
A **production flasher** for **ESP32‑S3** sensor nodes (project "EigenVib"). An operator
plugs a node into USB, clicks **FLASH**, and the tool:
1. flashes the bundled firmware,
2. captures a one‑time provisioning line the node prints on first boot,
3. writes a **QR PNG** (with a human‑readable 6‑char code printed under it) to
   `%USERPROFILE%\Desktop\EigenVib-QR\`.

It is a **Python** program packaged into a **single Windows `.exe`** with **PyInstaller**,
so the operator needs nothing installed. Two source files:
- `eigenvib_flasher.py` — core/CLI logic (port detection, flashing, capture, QR).
- `eigenvib_flasher_gui.py` — **Tkinter** GUI wrapper; **this is the entry point we package**.

## 2. What the flasher must DO (functional spec)
- **find the port:** enumerate serial ports (pyserial `list_ports`). The node is an
  ESP32‑S3 **USB‑Serial‑JTAG**, USB **VID `0x303A`**, description "USB JTAG/serial debug
  unit" (on Windows it is a `COMx`). Accept VIDs {0x303A, 0x10C4, 0x1A86, 0x0403}.
- **flash** with **esptool**: `erase_flash`, then `write_flash` of three images:
  `0x0 bootloader.bin`, `0x8000 partition-table.bin`, `0x10000 sensor_node.bin`
  (chip `esp32s3`, baud 460800, `--flash_mode dio --flash_size 16MB --flash_freq 40m`,
  `--before default_reset --after no_reset`). **esptool 4.x uses underscore**
  subcommands/options — hyphens are esptool 5.x only. Keep **esptool==4.12.0**.
- **reset & capture:** toggle DTR/RTS to boot the app, read serial for the one‑time line
  `PROV node_id=<uuid> psk=<hex64> code=<XXXXXX>`.
- **make QR:** a `segno` QR of `{"v":1,"nid":<node_id>,"psk":<base64url(psk)>}`, then use
  **Pillow** to print the code (e.g. "896 GFE") under the QR; save `<code>.png`.
- **GUI:** port dropdown (auto‑detect), big FLASH button, live log, a result panel with the
  code + QR image; clears the result on node swap; refuses to guess when >1 node attached.
- On launch it writes `%USERPROFILE%\eigenvib_flasher_debug.log` (first line
  `launch: py=… arch=… tk=… frozen=…`) — use it for diagnosis.

## 3. Dependencies (pinned)
```
esptool==4.12.0
pyserial==3.5
segno==1.6.6
pillow>=10.2      # captions the QR with the human code
pyinstaller       # build tool
```

## 4. How the build was INTENDED to work
- **Python 3.11, 64‑bit**, matching the OS arch (this PC is **x86‑64 / Intel** → python.org
  "Windows installer (64‑bit)"). PyInstaller **cannot cross‑compile**; exe arch = Python arch.
- Build **in a venv**, and **run PyInstaller via the venv's own `python.exe`** — NOT a bare
  `pyinstaller` on PATH (a bare call may run against a different interpreter that lacks our
  deps → it bundles almost nothing → a broken exe).
- Exact commands (cmd), **in this folder**:
  ```cmd
  py -3.11 -m venv build_venv
  build_venv\Scripts\python.exe -m pip install --upgrade pip
  build_venv\Scripts\python.exe -m pip install esptool==4.12.0 pyserial==3.5 segno==1.6.6 "pillow>=10.2" pyinstaller
  build_venv\Scripts\python.exe -m PyInstaller --onefile --windowed --clean --noconfirm --name EigenVib-Flasher --collect-data esptool --add-data "firmware;firmware" eigenvib_flasher_gui.py
  dir dist\EigenVib-Flasher.exe
  ```
- **`--collect-data esptool` is REQUIRED** — else the app fails at flash time with "Flasher
  stub data is missing for ESP32-S3" (esptool's stub JSONs aren't auto‑bundled).
- **`--add-data "firmware;firmware"`** — Windows uses `;` (mac/Linux `:`). Bundles the 3
  `.bin` images; `firmware_dir()` resolves them via `sys._MEIPASS` when frozen.
- **Expected output size ≈ 19 MB** (Pillow + esptool + tkinter). A **KB‑sized** exe means the
  bundle failed OR something removed/replaced the file after build (see §5).

`build_windows.bat` already encodes all of this (venv python, py 3.11, collect‑data, size
print). Double‑clicking it should build everything.

## 5. THE ACTUAL PROBLEM on this machine — diagnose this
**Symptom:** PyInstaller reports success and prints `built: 19996517 bytes` (~19 MB), but the
resulting `dist\EigenVib-Flasher.exe` ends up **~1 KB** ("not a real exe"). So the 19 MB file
**is created and then shrinks/vanishes.** ("BUILD OK" that the user saw is just the batch's
own success banner, not the exe content.)

**Already ruled out:**
- Not architecture (PC is x86‑64 Intel; Python 3.11 x64 → x64 exe, correct).
- **Windows Defender shows no activity** → it is NOT Defender.

**Investigate (you have local access):**
1. **Synced / managed output folder.** The build path was `C:\AMPD Local Projects\…`. If that
   is under **OneDrive Files‑On‑Demand**, corporate **DLP**, or a backup/sync agent, the large
   exe can be **dehydrated to a placeholder** or **locked/replaced** right after creation.
   → **Rebuild in a plain local path** (e.g. copy this folder to `C:\flasher` and build
   there). Check `dir dist\EigenVib-Flasher.exe` **immediately** after build and again ~30 s
   later — if it shrinks, it's a sync/agent.
2. **Corporate / third‑party AV or EDR** (CrowdStrike, SentinelOne, McAfee, Symantec, Carbon
   Black…) — silently quarantines PyInstaller onefile exes and does **not** appear in Windows
   Defender. Identify it:
   ```powershell
   Get-CimInstance -Namespace root/SecurityCenter2 -ClassName AntiVirusProduct | Select displayName,productState
   ```
   Check that product's quarantine/log; add a folder exclusion **if policy allows**.
3. **onefile is the most fragile / most flagged.** Try **onedir** — easier to inspect, less
   likely to be nuked:
   ```cmd
   build_venv\Scripts\python.exe -m PyInstaller --onedir --windowed --clean --noconfirm --name EigenVib-Flasher --collect-data esptool --add-data "firmware;firmware" eigenvib_flasher_gui.py
   ```
   Output: `dist\EigenVib-Flasher\EigenVib-Flasher.exe` + an `_internal\` folder (keep the
   folder together). If `_internal` is full but the exe is tiny → an external agent is
   truncating the exe, not a bundling problem.
4. Confirm the interpreter: `py -0p` and
   `build_venv\Scripts\python.exe -c "import platform,struct;print(platform.machine(),struct.calcsize('P')*8)"`
   → expect `AMD64 64`.
5. If the app builds but crashes at runtime (different from the 1 KB problem), read
   PyInstaller's `build\EigenVib-Flasher\warn-EigenVib-Flasher.txt` for missing modules, and
   the app's own `%USERPROFILE%\eigenvib_flasher_debug.log`.

## 6. How to verify success
- `dir dist\EigenVib-Flasher.exe` stays **~19 MB** (onefile), or `dist\EigenVib-Flasher\`
  exists with a full `_internal\` (onedir).
- Run it → a window titled **"EigenVib Flasher"** opens. (No node needed to prove it
  launches — with no node it just shows "No serial port found".)
- `%USERPROFILE%\eigenvib_flasher_debug.log` first line shows `py=3.11 arch=AMD64 tk=8.6
  frozen=True`. **Paste that back as proof.**
- With a node plugged: status turns green ("Node detected"), the `COMx` appears.
- SmartScreen on first run → "More info" → "Run anyway". Unsigned is expected.

## 7. What you may / may NOT change
May: build in a clean local folder, switch to onedir, add AV exclusions (if allowed),
otherwise adapt the **build** to this machine. Must NOT change: the flasher's **behaviour**
or the **esptool flash parameters** in §2 (correct, matched to the hardware), and the
firmware `.bin` files (bundle unchanged). Goal = a launching, node‑flashing `EigenVib-Flasher`.

## 8. Files in this folder
```
CLAUDE-CODE-START-HERE.md  <- this file (self-contained brief + full source appendix)
PROCITAJ-OVO.txt           <- short human instructions (Serbian)
build_windows.bat          <- one-click build (encodes §4)
eigenvib_flasher_gui.py    <- GUI entry point (packaged)
eigenvib_flasher.py        <- core logic
requirements.txt           <- pinned deps
README.md                  <- original tool README (mac/win/linux)
firmware/                  <- bootloader.bin, partition-table.bin, sensor_node.bin (bundle as-is)
```

---

# Appendix — full source (inlined)
The exact contents of every text file follow, so this document is complete on its own. If a
file in the folder is missing or was altered by the machine, regenerate it from here verbatim.

### eigenvib_flasher_gui.py  (GUI entry point — packaged)
```python
#!/usr/bin/env python3
"""EigenVib Flasher — a one-window GUI over eigenvib_flasher.py.

Pick (or auto-detect) the node's USB port, press FLASH, watch the live log, and
see the resulting QR + 6-char code — saved automatically to the QR folder. It
reuses the exact CLI logic (same flash/capture/QR functions), so behaviour is
identical to the terminal tool. Cross-platform (macOS / Windows / Linux); packs
into ONE file with PyInstaller just like the CLI — add ``--windowed``:

  # macOS  -> dist/EigenVib-Flasher.app
  pyinstaller --onefile --windowed --name EigenVib-Flasher \
      --add-data "firmware:firmware" eigenvib_flasher_gui.py
  # Windows -> dist\\EigenVib-Flasher.exe
  pyinstaller --onefile --windowed --name EigenVib-Flasher ^
      --add-data "firmware;firmware" eigenvib_flasher_gui.py
"""
import os
import queue
import subprocess
import sys
import threading
import time
import traceback

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import serial.tools.list_ports

from eigenvib_flasher import (
    KNOWN_VIDS,
    IMAGES,
    firmware_dir,
    find_port,
    flash,
    reset_and_capture,
    make_qr,
    append_registry,
)

APP = "EigenVib Flasher"
AUTO = "Auto-detect"
DEBUG_LOG = os.path.expanduser("~/eigenvib_flasher_debug.log")


def dbg(msg):
    """Append a line to a debug log next to the user's home — for remote support."""
    try:
        with open(DEBUG_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")
    except Exception:
        pass


def list_ports():
    """(device, human label, is_known) for every serial port; likely nodes first."""
    out = []
    for p in serial.tools.list_ports.comports():
        dev, desc = (p.device or ""), (p.description or "")
        known = (
            p.vid in KNOWN_VIDS
            or "usbmodem" in dev
            or "USB" in desc
            or "CP210" in desc
            or "CH34" in desc
        )
        out.append((dev, f"{dev}  —  {desc}".strip(), known))
    out.sort(key=lambda t: (not t[2], t[0]))
    return out


class _Tee:
    """Fan stdout/stderr from the worker thread into the GUI log queue."""

    def __init__(self, q):
        self.q = q

    def write(self, s):
        if s:
            self.q.put(("log", s))

    def flush(self):
        pass


class FlasherGUI:
    def __init__(self, root):
        self.root = root
        self.q = queue.Queue()
        self.busy = False
        self._qr_img = None  # keep a ref so Tk doesn't GC the image
        dbg("init: start building UI")

        root.title(APP)
        root.minsize(660, 560)

        outer = ttk.Frame(root, padding=14)
        outer.pack(fill="both", expand=True)

        ttk.Label(outer, text=APP, font=("Helvetica", 18, "bold")).pack(anchor="w")
        ttk.Label(
            outer,
            text="Plug a node in over USB, then press FLASH. The QR is saved for you.",
            foreground="#666",
        ).pack(anchor="w", pady=(0, 10))

        # --- controls row -------------------------------------------------
        ctrl = ttk.Frame(outer)
        ctrl.pack(fill="x")

        ttk.Label(ctrl, text="Port:").grid(row=0, column=0, sticky="w")
        self.port_var = tk.StringVar(value=AUTO)
        self.port_cb = ttk.Combobox(ctrl, textvariable=self.port_var, width=42, state="readonly")
        self.port_cb.grid(row=0, column=1, sticky="w", padx=6)
        ttk.Button(ctrl, text="⟳", width=3, command=self.refresh_ports).grid(row=0, column=2)

        self.erase_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            ctrl,
            text="Erase — new identity + QR (uncheck = firmware update only)",
            variable=self.erase_var,
        ).grid(row=1, column=1, sticky="w", padx=6, pady=(8, 0))

        # --- QR folder ----------------------------------------------------
        qrow = ttk.Frame(outer)
        qrow.pack(fill="x", pady=(10, 0))
        ttk.Label(qrow, text="QR folder:").pack(side="left")
        self.qrdir_var = tk.StringVar(value=os.path.expanduser("~/Desktop/EigenVib-QR"))
        ttk.Entry(qrow, textvariable=self.qrdir_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(qrow, text="Choose…", command=self.choose_dir).pack(side="left")

        # --- flash button -------------------------------------------------
        # A Label styled as a button: on macOS a real tk.Button ignores bg and
        # renders a small native control (only that is clickable). A Label honours
        # bg and, with a click binding, the WHOLE bar is clickable.
        self.flash_btn = tk.Label(
            outer,
            text="⚡  FLASH NODE",
            font=("Helvetica", 17, "bold"),
            bg="#2b7de9",
            fg="white",
            cursor="hand2",
            padx=10,
            pady=16,
        )
        self.flash_btn.pack(fill="x", pady=12)
        self.flash_btn.bind("<Button-1>", self._flash_click)
        self.flash_btn.bind("<Enter>", self._flash_hover_on)
        self.flash_btn.bind("<Leave>", self._flash_hover_off)

        # --- body: log + result ------------------------------------------
        body = ttk.Frame(outer)
        body.pack(fill="both", expand=True)

        logf = ttk.LabelFrame(body, text="Log")
        logf.pack(side="left", fill="both", expand=True)
        self.log = tk.Text(logf, height=14, width=48, wrap="word", state="disabled",
                           bg="#111", fg="#d6d6d6", font=("Menlo", 10))
        self.log.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(logf, command=self.log.yview)
        sb.pack(side="right", fill="y")
        self.log["yscrollcommand"] = sb.set

        self.resultf = ttk.LabelFrame(body, text="Result")
        self.resultf.pack(side="left", fill="both", expand=False, padx=(10, 0))
        self.code_lbl = ttk.Label(self.resultf, text="—", font=("Helvetica", 22, "bold"))
        self.code_lbl.pack(pady=(8, 4))
        self.qr_lbl = ttk.Label(self.resultf)
        self.qr_lbl.pack(padx=8)
        self.nid_lbl = ttk.Label(self.resultf, text="", foreground="#666", wraplength=220, justify="center")
        self.nid_lbl.pack(pady=(4, 6))
        self.open_btn = ttk.Button(self.resultf, text="Open folder", command=self.open_folder, state="disabled")
        self.open_btn.pack(pady=(0, 8))

        self.status = ttk.Label(outer, text="Ready.", foreground="#666")
        self.status.pack(anchor="w", pady=(8, 0))

        self._last_ports = None
        self._known_devs = set()   # devices of node-like ports last seen
        self._have_result = False  # a QR/result is currently shown
        self._grace = 0            # refresh cycles to ignore port churn after a flash
        self.refresh_ports()
        try:
            dbg(f"startup ports: {list_ports()}")
        except Exception as e:
            dbg(f"startup list_ports FAILED: {e!r}")
        self.root.after(80, self._pump)
        self.root.after(1500, self._auto_refresh)

    # ---- UI helpers -----------------------------------------------------
    def refresh_ports(self):
        try:
            t0 = time.time()
            dbg("refresh_ports: calling list_ports() …")
            ports = list_ports()
            dbg(f"refresh_ports: got {len(ports)} in {time.time()-t0:.2f}s")
        except Exception as e:  # noqa: BLE001
            dbg(f"list_ports error: {e!r}")
            ports = []
        vals = [AUTO] + [lbl for _, lbl, _ in ports]
        self.port_cb["values"] = vals
        self._port_map = {lbl: dev for dev, lbl, _ in ports}
        known_labels = [lbl for _, lbl, k in ports if k]
        known_devs = {dev for dev, _, k in ports if k}
        cur = self.port_var.get()
        if cur not in vals:
            cur = AUTO
        # Auto-select ONLY when exactly one node exists. With several, force a
        # deliberate choice (never guess which node to flash).
        if cur == AUTO and len(known_labels) == 1:
            self.port_var.set(known_labels[0])
        else:
            self.port_var.set(cur)
        # Node set changed (swap / plug / unplug) → wipe any stale result so the
        # panel never shows a QR belonging to a node that's no longer connected.
        # A freshly-flashed node re-enumerates (its port name changes) — the grace
        # window absorbs that so we don't clear the QR we just produced.
        changed = known_devs != self._known_devs
        self._known_devs = known_devs
        if self._grace > 0:
            self._grace -= 1
        elif changed and self._have_result:
            self._clear_result()
            dbg("node swap → cleared previous result")
        # status line
        if not self.busy:
            n = len(known_labels)
            if n == 0:
                self.status.configure(text="No node detected — plug it in over USB.",
                                      foreground="#b00020")
            elif n == 1:
                self.status.configure(text=f"✓ Node detected: {next(iter(known_devs))} — ready to FLASH.",
                                      foreground="#1a7f37")
            else:
                self.status.configure(text=f"⚠ {n} nodes detected — pick ONE in Port (or connect just one).",
                                      foreground="#b06f00")

    def _auto_refresh(self):
        if not self.busy:
            snap = tuple(self.port_cb["values"])
            self.refresh_ports()
            if tuple(self.port_cb["values"]) != snap:
                dbg(f"ports changed -> {self.port_cb['values']}")
        self.root.after(1500, self._auto_refresh)

    def choose_dir(self):
        d = filedialog.askdirectory(initialdir=self.qrdir_var.get() or os.getcwd())
        if d:
            self.qrdir_var.set(d)

    def _clear_result(self):
        self._have_result = False
        self._qr_img = None
        self.code_lbl.configure(text="—")
        self.qr_lbl.configure(image="", text="")
        self.nid_lbl.configure(text="")
        self.open_btn.configure(state="disabled")

    def open_folder(self):
        d = self.qrdir_var.get()
        if not os.path.isdir(d):
            return
        if sys.platform == "darwin":
            subprocess.run(["open", d])
        elif os.name == "nt":
            os.startfile(d)  # noqa: type
        else:
            subprocess.run(["xdg-open", d])

    def _emit(self, s):
        self.log["state"] = "normal"
        self.log.insert("end", s)
        self.log.see("end")
        self.log["state"] = "disabled"

    def _flash_click(self, _e=None):
        if not self.busy:
            self.on_flash()

    def _flash_hover_on(self, _e=None):
        if not self.busy:
            self.flash_btn.configure(bg="#1f5fc0")

    def _flash_hover_off(self, _e=None):
        if not self.busy:
            self.flash_btn.configure(bg="#2b7de9")

    def _set_busy(self, busy, status=None):
        self.busy = busy
        if busy:
            self.flash_btn.configure(text="⏳  Flashing…  (do not unplug the node)",
                                     bg="#9aa0a6", cursor="watch")
        else:
            self.flash_btn.configure(text="⚡  FLASH NODE", bg="#2b7de9", cursor="hand2")
        if status:
            self.status["text"] = status

    # ---- flash flow -----------------------------------------------------
    def on_flash(self):
        if self.busy:
            return
        fw = firmware_dir()
        missing = [n for _, n in IMAGES if not os.path.exists(os.path.join(fw, n))]
        if missing:
            messagebox.showerror(APP, f"Missing firmware images {missing} in {fw}")
            return
        sel = self.port_var.get()
        # Never guess with several nodes attached — make the operator choose one.
        if sel == AUTO and len(self._known_devs) > 1:
            messagebox.showwarning(
                APP,
                f"{len(self._known_devs)} nodes are connected.\n\n"
                "Pick ONE node in the Port dropdown, or unplug the others so only "
                "one node is connected, then press FLASH again.")
            return
        port = None if sel == AUTO else self._port_map.get(sel, sel)
        erase = self.erase_var.get()
        qrdir = self.qrdir_var.get()

        self._emit("\n" + "=" * 52 + "\n")
        self._set_busy(True, "Flashing… do not unplug the node.")
        self._have_result = False
        self.code_lbl["text"] = "…"
        self.qr_lbl["image"] = ""
        self.nid_lbl["text"] = ""
        self.open_btn["state"] = "disabled"

        threading.Thread(target=self._worker, args=(port, fw, erase, qrdir), daemon=True).start()

    def _worker(self, port, fw, erase, qrdir):
        old_out, old_err = sys.stdout, sys.stderr
        sys.stdout = sys.stderr = _Tee(self.q)
        try:
            port = find_port(port)
            print(f"Node on {port}\n")
            flash(port, fw, erase=erase)
            print("• booting + capturing the QR secret …")
            got = reset_and_capture(port, 30)
            if not got:
                if not erase:
                    self.q.put(("updated", None))
                else:
                    self.q.put(("error", "No PROV line captured. Tap the RESET/EN button and retry."))
                return
            node_id, psk_hex, code = got
            png, _ = make_qr(node_id, psk_hex, code, qrdir)
            append_registry(qrdir, node_id, code)
            print(f"\n✓ DONE  code={code}  node_id={node_id}\n  QR: {png}")
            self.q.put(("done", (code, node_id, png)))
        except SystemExit as e:
            self.q.put(("error", str(e)))
        except Exception as e:  # noqa: BLE001
            self.q.put(("error", f"{type(e).__name__}: {e}"))
        finally:
            sys.stdout, sys.stderr = old_out, old_err

    def _pump(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "log":
                    self._emit(payload)
                elif kind == "done":
                    code, node_id, png = payload
                    self.code_lbl["text"] = code
                    self.nid_lbl["text"] = f"advertises as SNSR-{code}\n{node_id}"
                    try:
                        self._qr_img = tk.PhotoImage(file=png)
                        self.qr_lbl["image"] = self._qr_img
                    except Exception:
                        self.qr_lbl["text"] = "(QR saved — preview unavailable)"
                    self.open_btn["state"] = "normal"
                    self._have_result = True
                    self._grace = 4  # ignore the node's post-flash re-enumeration
                    self._set_busy(False, f"Done — code {code}. QR saved. Print & stick it on the box.")
                elif kind == "updated":
                    self.code_lbl["text"] = "—"
                    self._set_busy(False, "Firmware updated. Identity + PSK preserved (existing QR still applies).")
                elif kind == "error":
                    self._set_busy(False, "Failed — see log.")
                    messagebox.showerror(APP, payload)
        except queue.Empty:
            pass
        self.root.after(80, self._pump)


def main():
    import platform
    dbg("=" * 40)
    dbg(f"launch: py={sys.version.split()[0]} arch={platform.machine()} "
        f"tk={tk.TkVersion} frozen={getattr(sys, 'frozen', False)} fw={firmware_dir()}")
    try:
        root = tk.Tk()
        try:
            ttk.Style().theme_use("clam")
        except Exception:
            pass
        FlasherGUI(root)
        root.mainloop()
        dbg("clean exit")
    except Exception:
        dbg("FATAL:\n" + traceback.format_exc())
        try:
            r = tk.Tk(); r.withdraw()
            messagebox.showerror(APP, "Startup error — see ~/eigenvib_flasher_debug.log\n\n"
                                 + traceback.format_exc())
        except Exception:
            pass
        raise


if __name__ == "__main__":
    main()

```

### eigenvib_flasher.py  (core logic)
```python
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


def make_qr(node_id, psk_hex, code, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    psk = bytes.fromhex(psk_hex)
    if len(psk) != 32:
        raise SystemExit("captured PSK is not 32 bytes")
    payload = json.dumps({"v": 1, "nid": node_id,
                          "psk": base64.urlsafe_b64encode(psk).decode().rstrip("=")},
                         separators=(",", ":"))
    png = os.path.join(out_dir, f"{code}.png")
    # Render the QR, then caption it with the human-readable code so the printed /
    # engraved sticker shows BOTH the machine QR and the 6-char code (e.g. "896 GFE").
    try:
        import segno
        from io import BytesIO
        buf = BytesIO()
        segno.make(payload, error="m").save(buf, kind="png", scale=8, border=2)
        buf.seek(0)
        _caption_png(buf, code, png)
    except ImportError:
        import subprocess
        subprocess.run(["qrencode", "-o", png, "-m", "2", "-s", "8", payload], check=True)
    return png, payload


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

```

### build_windows.bat
```bat
@echo off
REM ===================================================================
REM  One-shot Windows build for the EigenVib flasher GUI.
REM  Output: dist\EigenVib-Flasher.exe  (one self-contained file)
REM
REM  Prerequisites on this Windows PC (once):
REM    * Python 3.11 (or 3.12) from python.org  -- during install TICK
REM      "Add python.exe to PATH".
REM    * This folder must contain: eigenvib_flasher_gui.py,
REM      eigenvib_flasher.py, and firmware\ with the 3 .bin files.
REM
REM  Then just double-click this file.
REM ===================================================================
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
  echo.
  echo ERROR: Python launcher "py" not found.
  echo        Install Python 3.11 from https://www.python.org/downloads/windows/
  echo        and TICK "Add python.exe to PATH" during setup, then re-run this.
  echo.
  pause
  exit /b 1
)

if not exist firmware\sensor_node.bin (
  echo.
  echo ERROR: firmware\sensor_node.bin is missing.
  echo        Copy the whole firmware\ folder ^(bootloader.bin, partition-table.bin,
  echo        sensor_node.bin^) next to this script and re-run.
  echo.
  pause
  exit /b 1
)

echo == [1/4] creating build venv (prefer Python 3.11) ==
REM Pick an interpreter: try the 3.11 launcher, then any py 3, then plain python.
set "PYL=py -3.11"
%PYL% -c "import sys" 1>nul 2>nul || set "PYL=py -3"
%PYL% -c "import sys" 1>nul 2>nul || set "PYL=python"
echo    using: %PYL%
%PYL% -m venv build_venv || goto :err
REM IMPORTANT: run everything through the venv's OWN python.exe — never a bare
REM "pyinstaller"/"python" on PATH, or PyInstaller may run against a different
REM interpreter that lacks our deps and bundle almost nothing into the .exe.
set "VPY=build_venv\Scripts\python.exe"

echo == [2/4] installing dependencies (pinned) ==
"%VPY%" -m pip install --upgrade pip || goto :err
"%VPY%" -m pip install esptool==4.12.0 pyserial==3.5 segno==1.6.6 "pillow>=10.2" pyinstaller || goto :err

echo == [3/4] building EigenVib-Flasher.exe ==
REM Windows uses ';' as the --add-data separator (macOS/Linux use ':').
"%VPY%" -m PyInstaller --onefile --windowed --clean --noconfirm ^
  --name EigenVib-Flasher ^
  --collect-data esptool ^
  --add-data "firmware;firmware" ^
  eigenvib_flasher_gui.py || goto :err

echo == [4/4] done ==
for %%A in ("dist\EigenVib-Flasher.exe") do echo    built: %%~zA bytes  (expect ~8-10 MB; if only KB the bundle failed)
echo.
echo ============================================================
echo   BUILD OK  ->  dist\EigenVib-Flasher.exe
echo   Send THAT single .exe to whoever flashes nodes.
echo   (First run: Windows SmartScreen -^> "More info" -^> "Run anyway".)
echo ============================================================
echo.
pause
exit /b 0

:err
echo.
echo *** BUILD FAILED - see the error above. ***
echo.
pause
exit /b 1

```

### requirements.txt
```
esptool>=4.5
pyserial>=3.5
segno>=1.5
pillow>=10.2   # captions the QR PNG with the human-readable code

```

### PROCITAJ-OVO.txt  (human, Serbian)
```
========================================================
  EigenVib Flasher - Windows (PROCITAJ OVO PRVO)
========================================================

Ovaj folder pravi program "EigenVib-Flasher.exe" kojim se flesuju
senzor-nodovi. Nema instalacije - napravis .exe jednom, pa ga
samo pokreces.

--------------------------------------------------------
1) STA TI TREBA (samo jednom)
--------------------------------------------------------
Python 3.11 (64-bit) sa:
  https://www.python.org/downloads/
  -> u instalaciji OBAVEZNO cekiraj "Add python.exe to PATH".
  (racunar je x64 / Intel  ->  uzmi "Windows installer (64-bit)")

--------------------------------------------------------
2) NAJLAKSE: dvoklik na   build_windows.bat
--------------------------------------------------------
Sam napravi sve. Kad zavrsi, exe je:   dist\EigenVib-Flasher.exe

--------------------------------------------------------
3) ILI RUCNO (ako dvoklik ne radi)
--------------------------------------------------------
Otvori Command Prompt (cmd) U OVOM folderu:
  Shift + desni klik u folderu -> "Open in Terminal"
  (ili "Open command window here")
pa ukucaj REDOM ove komande:

  rmdir /s /q build_venv dist build 2>nul
  py -3.11 -m venv build_venv
  build_venv\Scripts\python.exe -m pip install --upgrade pip
  build_venv\Scripts\python.exe -m pip install esptool==4.12.0 pyserial==3.5 segno==1.6.6 "pillow>=10.2" pyinstaller
  build_venv\Scripts\python.exe -m PyInstaller --onefile --windowed --clean --noconfirm --name EigenVib-Flasher --collect-data esptool --add-data "firmware;firmware" eigenvib_flasher_gui.py
  dir dist\EigenVib-Flasher.exe

VAZNO: koristi se  "build_venv\Scripts\python.exe -m PyInstaller"
(a NE golo "pyinstaller") - golo pyinstaller je pravilo prazan exe.

--------------------------------------------------------
4) PROVERA
--------------------------------------------------------
Zadnja linija (dir) treba da pokaze velicinu oko 8-10 MB:
  ~8-10 MB  -> OK. Idi na korak 5.
  KB / malo -> build nije upakovao. Javi + posalji ispis iz cmd-a.

--------------------------------------------------------
5) POKRETANJE
--------------------------------------------------------
Pokreni:  dist\EigenVib-Flasher.exe
  - prvi put SmartScreen -> "More info" -> "Run anyway"
  - ako Windows Defender obrise .exe: dodaj ovaj folder u
    izuzetke (Windows Security -> Virus & threat protection
    -> Manage settings -> Exclusions -> Add -> Folder), pa
    ponovi build.

FLESOVANJE NODA:
  1. Ubodi node u USB.
  2. U prozoru se sam pojavi port -> klikni  FLASH  NODE.
  3. QR se snimi u:  %USERPROFILE%\Desktop\EigenVib-QR\

--------------------------------------------------------
6) AKO NESTO PUKNE
--------------------------------------------------------
Posalji sadrzaj log fajla (kopiraj u poruku):
  type %USERPROFILE%\eigenvib_flasher_debug.log
i napisi na kom koraku je stalo.
========================================================

```
