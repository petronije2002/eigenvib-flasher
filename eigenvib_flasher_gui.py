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
