"""
briner_agent/monitor.py

Standalone monitoring window for Briner.
Reads from the shared SQLite database and shows real-time activity.
No external dependencies — only stdlib (tkinter, sqlite3).
"""

import json
import os
import sqlite3
import sys
import tkinter as tk
import tkinter.messagebox
from pathlib import Path
from tkinter import ttk

# --- Path resolution (mirrors main.py logic) ---
IS_FROZEN = getattr(sys, "frozen", False)
if IS_FROZEN:
    _appdata = os.environ.get("APPDATA", "")
    _briner_dir = (
        Path(_appdata) / "Briner"
        if _appdata
        else Path.home() / "AppData" / "Roaming" / "Briner"
    )
    DB_PATH = _briner_dir / "briner.db"
    SETTINGS_PATH = _briner_dir / "user_settings.json"
    LOGS_DIR = _briner_dir / "logs"
else:
    _code_dir = Path(__file__).resolve().parent
    DB_PATH = _code_dir / "db" / "briner.db"
    SETTINGS_PATH = _code_dir / "user_settings.json"
    LOGS_DIR = _code_dir / "logs"

_QUERY_EVENTS = """
SELECT
    strftime('%H:%M:%S', ce.timestamp)  AS hora,
    COALESCE(f.filename, ce.old_path)   AS archivo,
    COALESCE(ce.category, ce.action)    AS categoria,
    COALESCE(ce.decision_source, '')    AS fuente,
    ce.action                           AS accion,
    CASE ce.dry_run WHEN 1 THEN '(dry-run)' ELSE '' END AS modo
FROM classification_events ce
LEFT JOIN files f ON f.id = ce.file_id
ORDER BY ce.timestamp DESC
LIMIT 100
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
        return None, None
    try:
        con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=5)
        con.row_factory = sqlite3.Row
        try:
            rows = con.execute(_QUERY_EVENTS).fetchall()
            counts_raw = con.execute(_QUERY_COUNTS).fetchall()
        finally:
            con.close()
        counts = {r[0]: r[1] for r in counts_raw}
        return rows, counts
    except Exception:
        return None, None


class BrinerMonitorApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        workspace = _read_workspace()
        title = f"Briner Monitor — {workspace}" if workspace else "Briner Monitor"
        root.title(title)
        root.minsize(640, 400)
        root.geometry("940x540")
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
        tk.Button(btn_frame, text="↺ Actualizar ahora", command=self._refresh).pack(side=tk.LEFT, padx=4)
        tk.Button(btn_frame, text="Abrir logs", command=self._open_logs).pack(side=tk.LEFT, padx=4)

        ttk.Separator(self.root, orient=tk.HORIZONTAL).pack(fill=tk.X)

        frame = tk.Frame(self.root)
        frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        cols = ("hora", "archivo", "categoria", "fuente", "accion", "modo")
        headings = ("Hora", "Archivo", "Categoría", "Fuente", "Acción", "Modo")
        widths = (70, 250, 220, 90, 80, 68)

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
        rows, counts = _fetch_data()
        self._update_ui(rows, counts)
        self.root.after(_REFRESH_MS, self._refresh)

    def _update_ui(self, rows, counts):
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
                row["modo"] or "",
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

        if has_errors or errors > 0:
            self._status_dot.config(fg="#dc2626")
            self._status_label.config(text="Hay errores")
        elif rows:
            self._status_dot.config(fg="#22c55e")
            self._status_label.config(text="Activo")
        else:
            self._status_dot.config(fg="gray")
            self._status_label.config(text="Sin actividad reciente")

    def _open_logs(self):
        if LOGS_DIR.exists():
            os.startfile(str(LOGS_DIR))
        else:
            tkinter.messagebox.showinfo(
                "Briner Monitor", f"Carpeta de logs no encontrada:\n{LOGS_DIR}"
            )


def main():
    root = tk.Tk()
    BrinerMonitorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
