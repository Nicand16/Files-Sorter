import logging
import os
import threading
from pathlib import Path

logger = logging.getLogger(__name__)


def _make_icon(color: tuple):
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([4, 4, 60, 60], fill=(*color, 255))
    return img


class BrinerTrayIcon:
    _GREEN = (34, 197, 94)
    _BLUE = (59, 130, 246)
    _RED = (239, 68, 68)

    def __init__(self, workspace_dir: Path, appdata_dir: Path, stop_event: threading.Event, force_scan_event: threading.Event):
        self.workspace_dir = Path(workspace_dir)
        self.appdata_dir = Path(appdata_dir)
        self.stop_event = stop_event
        self.force_scan_event = force_scan_event
        self._icon = None
        self._lock = threading.Lock()
        self._status = "Iniciando..."
        self._color = self._GREEN
        self._pending = 0
        self._processed_total = 0
        self._errors_total = 0
        self._last_cycle = "-"
        self.last_error_message = ""
        self._pending_notifications: list[tuple[str, str]] = []

    def update_stats(
        self,
        status: str,
        pending: int = 0,
        processed_total: int = 0,
        errors_total: int = 0,
        last_cycle: str | None = None,
        error: bool = False,
        error_message: str | None = None,
        clear_error: bool = False,
        processing: bool = False,
    ):
        with self._lock:
            self._status = status
            self._pending = pending
            self._processed_total = processed_total
            self._errors_total = errors_total
            if last_cycle is not None:
                self._last_cycle = last_cycle
            if error_message:
                self.last_error_message = error_message
            elif clear_error:
                self.last_error_message = ""
            elif error and not self.last_error_message:
                self.last_error_message = status

            if error or self.last_error_message:
                self._color = self._RED
            elif processing:
                self._color = self._BLUE
            else:
                self._color = self._GREEN
        self._refresh_icon()

    def set_error(self, message: str, notify: bool = True):
        with self._lock:
            self._status = "Error"
            self.last_error_message = message
            self._color = self._RED
        self._refresh_icon()
        if notify:
            self._notify("Briner - Error", message)

    def clear_error(self):
        with self._lock:
            self.last_error_message = ""
            self._color = self._GREEN
        self._refresh_icon()

    def _title(self, status: str, error_message: str = "") -> str:
        if error_message:
            return f"Briner - ERROR: {error_message[:96]}"
        return f"Briner - {status}"

    def _refresh_icon(self):
        if self._icon:
            try:
                with self._lock:
                    color = self._color
                    status = self._status
                    error_message = self.last_error_message
                self._icon.icon = _make_icon(color)
                self._icon.title = self._title(status, error_message)
                self._icon.menu = self._build_menu()
                self._icon.update_menu()
            except Exception:
                pass

    def _notify(self, title: str, message: str):
        if self._icon:
            try:
                self._icon.notify(message, title)
                return
            except Exception as exc:
                logger.warning("No se pudo mostrar notificacion de tray: %s", exc)
                return
        with self._lock:
            self._pending_notifications.append((title, message))

    def _flush_pending_notifications(self, icon):
        with self._lock:
            notifications = list(self._pending_notifications)
            self._pending_notifications.clear()
        for title, message in notifications:
            try:
                icon.notify(message, title)
            except Exception as exc:
                logger.warning("No se pudo mostrar notificacion pendiente de tray: %s", exc)

    def _build_menu(self):
        import pystray
        with self._lock:
            status = self._status
            pending = self._pending
            processed_total = self._processed_total
            errors_total = self._errors_total
            last_cycle = self._last_cycle
            error_message = self.last_error_message

        items = [
            pystray.MenuItem(f"Briner - {status}", None, enabled=False),
            pystray.Menu.SEPARATOR,
        ]
        if error_message:
            items.extend(
                [
                    pystray.MenuItem(f"Error activo: {error_message[:120]}", None, enabled=False),
                    pystray.Menu.SEPARATOR,
                ]
            )
        items.extend(
            [
                pystray.MenuItem(f"Pendientes: {pending}", None, enabled=False),
                pystray.MenuItem(f"Procesados total: {processed_total}", None, enabled=False),
                pystray.MenuItem(f"Errores total: {errors_total}", None, enabled=False),
                pystray.MenuItem(f"Ultimo ciclo: {last_cycle}", None, enabled=False),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Ver logs", self._open_logs),
                pystray.MenuItem("Abrir carpeta monitoreada", self._open_workspace),
                pystray.MenuItem("Forzar escaneo ahora", self._force_scan),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Detener Briner", self._quit),
            ]
        )
        return pystray.Menu(*items)

    def _open_logs(self, icon, item):
        log_dir = self.appdata_dir / "logs"
        log_file = log_dir / "briner.log"
        target = log_file if log_file.exists() else log_dir
        if target.exists():
            os.startfile(str(target))

    def _open_workspace(self, icon, item):
        if self.workspace_dir.exists():
            os.startfile(str(self.workspace_dir))

    def _force_scan(self, icon, item):
        self.force_scan_event.set()

    def _quit(self, icon, item):
        self.stop_event.set()
        icon.stop()

    def start(self):
        t = threading.Thread(target=self._run, daemon=True, name="BrinerTray")
        t.start()

    def _run(self):
        try:
            import pystray
            with self._lock:
                status = self._status
                color = self._color
                error_message = self.last_error_message
            img = _make_icon(color)
            self._icon = pystray.Icon(
                "Briner",
                img,
                self._title(status, error_message),
                menu=self._build_menu(),
            )
            self._icon.run(setup=self._flush_pending_notifications)
        except Exception as exc:
            logger.warning("No se pudo iniciar el icono de bandeja del sistema: %s", exc)

    def stop(self):
        if self._icon:
            try:
                self._icon.stop()
            except Exception:
                pass
