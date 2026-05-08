"""
briner_agent/monitor.py

Standalone monitoring window for Briner.
Reads from the shared SQLite database and shows real-time activity.
Minimizing hides the window to the system tray; force-scan button signals
BrinerBackground via a sentinel file to run a classification cycle immediately.
"""

import json
import os
import sqlite3
import sys
import threading
import tkinter as tk
import tkinter.messagebox
from pathlib import Path
from tkinter import ttk

import pystray
from PIL import Image, ImageDraw

# --- Path resolution (mirrors main.py logic) ---
IS_FROZEN = getattr(sys, "frozen", False)
if IS_FROZEN:
    _appdata = os.environ.get("APPDATA", "")
    _briner_dir = (
        Path(_appdata) / "Briner"
        if _appdata
        else Path.home() / "AppData" / "Roaming" / "Briner"
    )
else:
    # Dev mode: APPDATA_DIR == CODE_DIR == briner_agent/ (mirrors main.py)
    _briner_dir = Path(__file__).resolve().parent

DB_PATH = _briner_dir / "briner.db" if IS_FROZEN else _briner_dir / "db" / "briner.db"
SETTINGS_PATH = _briner_dir / "user_settings.json"
LOGS_DIR = _briner_dir / "logs"

_SENTINEL = _briner_dir / ".force_scan"  # inter-process signal file


def _make_tray_image() -> Image.Image:
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([4, 4, 60, 60], fill=(59, 130, 246, 255))  # blue circle
    return img


_QUERY_EVENTS = """
SELECT
    strftime('%H:%M:%S', ce.timestamp)  AS hora,
    COALESCE(f.filename, ce.old_path)   AS archivo,
    COALESCE(ce.category, ce.action)    AS categoria,
    COALESCE(ce.decision_source, '')    AS fuente,
    ce.action                           AS accion,
    COALESCE(ce.reason, '')             AS razon
FROM classification_events ce
LEFT JOIN files f ON f.id = ce.file_id
WHERE ce.file_id IS NOT NULL
ORDER BY ce.timestamp DESC
LIMIT 100
"""

_QUERY_SYSTEM_EVENT = """
SELECT action, reason, timestamp
FROM classification_events
WHERE action IN ('circuit_open', 'circuit_recovered')
  AND file_id IS NULL
ORDER BY timestamp DESC
LIMIT 1
"""

_QUERY_COUNTS = "SELECT status, COUNT(*) FROM files GROUP BY status"

_REFRESH_MS = 3000


def _read_workspace() -> str:
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        return data.get("monitoring", {}).get("workspace_dir", "")
    except Exception:
        return ""


def _fetch_data():
    if not DB_PATH.exists():
        return None, None, None
    try:
        con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=5)
        con.row_factory = sqlite3.Row
        try:
            rows = con.execute(_QUERY_EVENTS).fetchall()
            counts_raw = con.execute(_QUERY_COUNTS).fetchall()
            sys_event = con.execute(_QUERY_SYSTEM_EVENT).fetchone()
        finally:
            con.close()
        counts = {r[0]: r[1] for r in counts_raw}
        return rows, counts, sys_event
    except Exception:
        return None, None, None


class BrinerMonitorApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        workspace = _read_workspace()
        title = f"Briner Monitor — {workspace}" if workspace else "Briner Monitor"
        root.title(title)
        root.minsize(640, 400)
        root.geometry("940x540")
        self._tray: pystray.Icon | None = None
        root.bind('<Unmap>', self._on_minimize)
        root.protocol('WM_DELETE_WINDOW', self._on_close)
        self._build_ui()
        self._refresh()

    def _build_ui(self):
        top = tk.Frame(self.root, pady=6, padx=10)
        top.pack(fill=tk.X)

        self._status_dot = tk.Label(top, text="●", font=("Segoe UI", 14), fg="gray")
        self._status_dot.pack(side=tk.LEFT)

        self._status_label = tk.Label(top, text="Conectando...", font=("Segoe UI", 10))
        self._status_label.pack(side=tk.LEFT, padx=6)

        self._counters_label = tk.Label(top, text="", font=("Segoe UI", 10))
        self._counters_label.pack(side=tk.LEFT, padx=14)

        btn_frame = tk.Frame(top)
        btn_frame.pack(side=tk.RIGHT)
        tk.Button(btn_frame, text="⚡ Forzar escaneo", command=self._force_scan).pack(side=tk.LEFT, padx=4)
        tk.Button(btn_frame, text="↺ Actualizar ahora", command=self._refresh).pack(side=tk.LEFT, padx=4)
        tk.Button(btn_frame, text="Abrir logs", command=self._open_logs).pack(side=tk.LEFT, padx=4)
        tk.Button(btn_frame, text="🔑 Cambiar API key", command=self._change_api_key).pack(side=tk.LEFT, padx=4)

        ttk.Separator(self.root, orient=tk.HORIZONTAL).pack(fill=tk.X)

        frame = tk.Frame(self.root)
        frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        cols = ("hora", "archivo", "categoria", "fuente", "accion", "razon")
        headings = ("Hora", "Archivo", "Categoría", "Fuente", "Acción", "Razón")
        widths = (70, 230, 190, 80, 70, 180)

        self._tree = ttk.Treeview(frame, columns=cols, show="headings", selectmode="browse")
        for col, heading, width in zip(cols, headings, widths):
            self._tree.heading(col, text=heading)
            self._tree.column(col, width=width, minwidth=40, anchor=tk.W)

        vsb = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._tree.pack(fill=tk.BOTH, expand=True)

        self._info_label = tk.Label(
            self.root,
            text=f"DB: {DB_PATH}   |   actualización cada {_REFRESH_MS // 1000}s",
            font=("Segoe UI", 8),
            fg="gray",
            anchor=tk.W,
            padx=6,
            pady=2,
        )
        self._info_label.pack(fill=tk.X, side=tk.BOTTOM)

    def _refresh(self):
        rows, counts, sys_event = _fetch_data()
        self._update_ui(rows, counts, sys_event)
        self.root.after(_REFRESH_MS, self._refresh)

    def _update_ui(self, rows, counts, sys_event):
        import json as _json
        import datetime as _dt

        for item in self._tree.get_children():
            self._tree.delete(item)

        if rows is None:
            self._status_dot.config(fg="gray")
            if not DB_PATH.exists():
                self._status_label.config(text="Briner no está configurado todavía")
            else:
                self._status_label.config(text="Error leyendo la base de datos")
            self._counters_label.config(text="")
            return

        has_errors = False
        for row in rows:
            values = (
                row["hora"] or "",
                row["archivo"] or "",
                row["categoria"] or "",
                row["fuente"] or "",
                row["accion"] or "",
                row["razon"] or "",
            )
            tag = "error_row" if row["accion"] == "error" else ""
            self._tree.insert("", tk.END, values=values, tags=(tag,))
            if row["accion"] == "error":
                has_errors = True

        self._tree.tag_configure("error_row", foreground="#dc2626")

        pending = counts.get("pending", 0)
        processed = counts.get("processed", 0)
        errors = counts.get("error", 0)
        self._counters_label.config(
            text=f"Pendientes: {pending}   Procesados: {processed}   Errores: {errors}"
        )

        # --- Circuit breaker state (from system events in DB) ---
        circuit_active = False
        circuit_msg = ""
        circuit_is_ratelimit = False
        if sys_event and sys_event["action"] == "circuit_open":
            try:
                payload = _json.loads(sys_event["reason"])
                etype = payload.get("type", "unknown")
                recovery_s = float(payload.get("recovery_seconds", 60))
                event_ts = _dt.datetime.fromisoformat(sys_event["timestamp"])
                elapsed = (_dt.datetime.now() - event_ts).total_seconds()
                remaining = max(0, recovery_s - elapsed)
                if remaining > 0:
                    circuit_active = True
                    if etype == "rate_limit":
                        circuit_is_ratelimit = True
                        circuit_msg = f"Cuota de Gemini excedida — reintentando en ~{int(remaining)}s automáticamente"
                    else:
                        circuit_msg = "API key inválida — ve a Bandeja del sistema → Cambiar API key"
            except Exception:
                pass

        # --- Specific error reason from file events ---
        error_reasons = [row["razon"] for row in rows if row["accion"] == "error" and row["razon"]]

        if circuit_active and circuit_is_ratelimit:
            self._status_dot.config(fg="#f59e0b")  # yellow = rate limit, recovering
            self._status_label.config(text=circuit_msg)
        elif circuit_active:
            self._status_dot.config(fg="#dc2626")
            self._status_label.config(text=circuit_msg)
        elif has_errors or errors > 0:
            self._status_dot.config(fg="#dc2626")
            detail = f": {error_reasons[0][:80]}" if error_reasons else ""
            self._status_label.config(text=f"Hay errores{detail}")
        elif rows:
            self._status_dot.config(fg="#22c55e")
            self._status_label.config(text="Activo")
        else:
            self._status_dot.config(fg="gray")
            self._status_label.config(text="Sin actividad reciente")

    def _force_scan(self):
        try:
            _SENTINEL.touch()
            self._status_label.config(text="Escaneo solicitado — Briner procesará en breve")
        except Exception as exc:
            tkinter.messagebox.showerror("Briner Monitor", f"No se pudo solicitar escaneo:\n{exc}")

    def _change_api_key(self):
        import subprocess
        ps_script = (
            "Add-Type -AssemblyName Microsoft.VisualBasic; "
            "$key = [Microsoft.VisualBasic.Interaction]::InputBox("
            "'Pega tu nueva API key de Google Gemini:', "
            "'Briner Monitor - Cambiar API key', ''); "
            "Write-Output $key"
        )
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
                capture_output=True, text=True, timeout=60,
            )
            new_key = result.stdout.strip()
        except Exception as exc:
            tkinter.messagebox.showerror("Briner Monitor", f"No se pudo mostrar el dialogo:\n{exc}")
            return
        if not new_key:
            return
        env_path = _briner_dir / ".env"
        try:
            env_path.write_text(f"GOOGLE_API_KEY={new_key}\n", encoding="utf-8")
            self._status_label.config(
                text="API key guardada. Se aplicara en el proximo ciclo o usa bandeja -> Cambiar API key."
            )
        except Exception as exc:
            tkinter.messagebox.showerror("Briner Monitor", f"No se pudo guardar la API key:\n{exc}")

    def _open_logs(self):
        if LOGS_DIR.exists():
            os.startfile(str(LOGS_DIR))
        else:
            tkinter.messagebox.showinfo(
                "Briner Monitor", f"Carpeta de logs no encontrada:\n{LOGS_DIR}"
            )

    # --- System tray on minimize ---

    def _on_minimize(self, event: tk.Event):
        if event.widget is self.root:
            self.root.after(1, self._hide_to_tray)

    def _hide_to_tray(self):
        self.root.withdraw()
        if self._tray is None:
            menu = pystray.Menu(
                pystray.MenuItem("Mostrar Briner Monitor", self._restore, default=True),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Cerrar", self._on_close),
            )
            self._tray = pystray.Icon("BrinerMonitor", _make_tray_image(), "Briner Monitor", menu)
            threading.Thread(target=self._tray.run, daemon=True, name="MonitorTray").start()

    def _restore(self, icon=None, item=None):
        if self._tray:
            self._tray.stop()
            self._tray = None
        self.root.after_idle(self._do_restore)

    def _do_restore(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def _on_close(self, icon=None, item=None):
        if self._tray:
            self._tray.stop()
            self._tray = None
        self.root.after_idle(self.root.destroy)


def main():
    root = tk.Tk()
    BrinerMonitorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
