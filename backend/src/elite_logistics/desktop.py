from __future__ import annotations

import ctypes
import logging
import os
import socket
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import uvicorn

from .config import get_settings, resource_path
from .main import create_app
from .version import APP_VERSION


APP_TITLE = "ION — IntraStellar Operations Network"
MUTEX_NAME = "Local\\IntraStellarLogistics.ION"
ERROR_ALREADY_EXISTS = 183
DEFAULT_DESKTOP_PORT = 8766


def configure_logging() -> None:
    path = get_settings().paths.logs / "ion.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[logging.FileHandler(path, encoding="utf-8")],
        force=True,
    )


def find_available_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as candidate:
        candidate.bind(("127.0.0.1", 0))
        return int(candidate.getsockname()[1])


def show_error_dialog(message: str, title: str = f"{APP_TITLE} — Startup Error") -> None:
    if os.name == "nt":
        ctypes.windll.user32.MessageBoxW(None, message, title, 0x10)
    else:
        print(f"{title}: {message}", file=sys.stderr)


def focus_existing_window() -> None:
    if os.name != "nt":
        return
    user32 = ctypes.windll.user32
    window = user32.FindWindowW(None, APP_TITLE)
    if window:
        user32.ShowWindow(window, 9)
        user32.SetForegroundWindow(window)


class SingleInstance:
    def __init__(self, name: str = MUTEX_NAME):
        self.name = name
        self.handle: int | None = None

    def acquire(self) -> bool:
        if os.name != "nt":
            return True
        kernel32 = ctypes.windll.kernel32
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        handle = kernel32.CreateMutexW(None, False, self.name)
        if not handle:
            raise OSError("Windows could not create the single-instance lock.")
        self.handle = int(handle)
        return kernel32.GetLastError() != ERROR_ALREADY_EXISTS

    def close(self) -> None:
        if self.handle and os.name == "nt":
            ctypes.windll.kernel32.CloseHandle(ctypes.c_void_p(self.handle))
            self.handle = None


@dataclass
class LocalApiServer:
    port: int | None = None
    startup_timeout_seconds: float = 20

    def __post_init__(self) -> None:
        self.port = self.port or find_available_port()
        self.server: uvicorn.Server | None = None
        self.thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self) -> None:
        config = uvicorn.Config(
            create_app(),
            host="127.0.0.1",
            port=self.port,
            log_level="warning",
            access_log=False,
            log_config=None if sys.stderr is None else uvicorn.config.LOGGING_CONFIG,
        )
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, name="ion-api", daemon=True)
        self.thread.start()
        self._wait_until_ready()

    def _wait_until_ready(self) -> None:
        deadline = time.monotonic() + self.startup_timeout_seconds
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            if self.thread and not self.thread.is_alive():
                raise RuntimeError("The local service stopped during startup.")
            try:
                with urlopen(f"{self.url}/api/health", timeout=0.5) as response:
                    if response.status == 200:
                        return
            except (OSError, URLError) as exc:
                last_error = exc
            time.sleep(0.1)
        raise TimeoutError(f"The local service did not become ready: {last_error}")

    def stop(self) -> None:
        if self.server:
            self.server.should_exit = True
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=8)
        if self.server and self.thread and self.thread.is_alive():
            self.server.force_exit = True
            self.thread.join(timeout=2)


def _screen_bounds() -> tuple[int, int, int, int]:
    if os.name != "nt":
        return (0, 0, 1920, 1080)
    user32 = ctypes.windll.user32
    return (
        int(user32.GetSystemMetrics(76)),
        int(user32.GetSystemMetrics(77)),
        int(user32.GetSystemMetrics(78)),
        int(user32.GetSystemMetrics(79)),
    )


def _clamp_bounds(bounds: dict, default_width: int, default_height: int) -> dict:
    left, top, screen_width, screen_height = _screen_bounds()
    width = min(max(int(bounds.get("width") or default_width), 640), screen_width)
    height = min(max(int(bounds.get("height") or default_height), 480), screen_height)
    x = bounds.get("x")
    y = bounds.get("y")
    if x is None or y is None or x + 100 < left or y + 60 < top or x >= left + screen_width or y >= top + screen_height:
        x = left + max(0, (screen_width - width) // 2)
        y = top + max(0, (screen_height - height) // 2)
    return {
        "x": min(max(int(x), left), left + screen_width - 100),
        "y": min(max(int(y), top), top + screen_height - 60),
        "width": width,
        "height": height,
        "maximized": bool(bounds.get("maximized", False)),
    }


class DesktopBridge:
    """Native operations exposed to trusted ION web content only."""

    def __init__(self, shell: "DesktopShell"):
        self.shell = shell

    def minimize(self) -> None:
        self.shell.main_window.minimize()

    def toggle_maximize(self) -> None:
        if self.shell.main_maximized:
            self.shell.main_window.restore()
        else:
            self.shell.main_window.maximize()
        self.shell.main_maximized = not self.shell.main_maximized
        self.shell.persist_window("main", maximized=self.shell.main_maximized)

    def close(self) -> None:
        self.shell.handle_main_close()

    def choose_journal_folder(self) -> str | None:
        import webview

        dialog_type = getattr(webview, "FOLDER_DIALOG", None)
        if dialog_type is None and hasattr(webview, "FileDialog"):
            dialog_type = webview.FileDialog.FOLDER
        result = self.shell.main_window.create_file_dialog(dialog_type)
        return str(result[0]) if result else None

    def open_route_console(self) -> None:
        self.shell.open_route_console()

    def close_route_console(self) -> None:
        self.shell.close_route_console()

    def set_route_fullscreen(self, enabled: bool) -> None:
        self.shell.set_route_fullscreen(enabled)

    def set_route_always_on_top(self, enabled: bool) -> None:
        self.shell.set_route_always_on_top(enabled)

    def show_ion(self) -> None:
        self.shell.show_main()

    def exit_ion(self) -> None:
        self.shell.exit()

    def pause_game_link(self, paused: bool) -> None:
        from .elite_monitor import elite_monitor

        elite_monitor.pause() if paused else elite_monitor.resume()

    def begin_update_installation(self) -> None:
        from .updater import install_downloaded_update

        install_downloaded_update(self.shell.exit)


class DesktopShell:
    def __init__(self, server: LocalApiServer):
        self.server = server
        self.main_window = None
        self.route_window = None
        self.main_maximized = False
        self.route_fullscreen = False
        self._exiting = False
        self._tray = None
        self._persist_lock = threading.Lock()
        self._persist_timers: dict[str, threading.Timer] = {}
        self._pending_bounds: dict[str, dict] = {"main": {}, "route": {}}
        self.bridge = DesktopBridge(self)

    def preferences(self):
        from .api import _load_preferences
        from .database import SessionLocal

        with SessionLocal() as session:
            return _load_preferences(session)

    def persist_window(self, kind: str, **changes) -> None:
        from .api import _load_preferences, _save_preferences
        from .database import SessionLocal

        with SessionLocal() as session:
            preferences = _load_preferences(session)
            bounds = preferences.main_window if kind == "main" else preferences.route_window
            for key, value in changes.items():
                setattr(bounds, key, value)
            _save_preferences(session, preferences)

    def queue_window_persist(self, kind: str, **changes) -> None:
        with self._persist_lock:
            self._pending_bounds[kind].update(changes)
            previous = self._persist_timers.get(kind)
            if previous:
                previous.cancel()
            timer = threading.Timer(0.4, self._flush_window_persist, args=(kind,))
            timer.daemon = True
            self._persist_timers[kind] = timer
            timer.start()

    def _flush_window_persist(self, kind: str) -> None:
        with self._persist_lock:
            changes = self._pending_bounds[kind]
            self._pending_bounds[kind] = {}
            self._persist_timers.pop(kind, None)
        if changes:
            self.persist_window(kind, **changes)

    def create_windows(self) -> None:
        import webview

        preferences = self.preferences()
        main = _clamp_bounds(preferences.main_window.model_dump(), 1500, 950)
        self.main_maximized = main["maximized"]
        self.main_window = webview.create_window(
            APP_TITLE,
            self.server.url,
            js_api=self.bridge,
            width=main["width"],
            height=main["height"],
            x=main["x"],
            y=main["y"],
            min_size=(900, 620),
            background_color="#030404",
            text_select=True,
            frameless=True,
            easy_drag=False,
        )
        self.main_window.events.closing += self._main_closing
        self.main_window.events.moved += lambda x, y: self.queue_window_persist("main", x=x, y=y)
        self.main_window.events.resized += lambda width, height: self.queue_window_persist(
            "main", width=width, height=height
        )
        if self.main_maximized:
            def maximize_once() -> None:
                self.main_window.events.shown -= maximize_once
                self.main_window.maximize()

            self.main_window.events.shown += maximize_once

    def _main_closing(self, *_args):
        if self._exiting:
            return True
        self.handle_main_close()
        return False

    def handle_main_close(self) -> None:
        if self.preferences().close_behavior == "tray":
            self.main_window.hide()
            self._ensure_tray()
        else:
            self.exit()

    def show_main(self) -> None:
        self.main_window.show()
        self.main_window.restore()
        self.main_window.on_top = True
        self.main_window.on_top = False

    def open_route_console(self) -> None:
        import webview

        if self.route_window:
            self.route_window.show()
            self.route_window.on_top = True
            self.route_window.on_top = self.preferences().route_always_on_top
            return
        preferences = self.preferences()
        self.route_fullscreen = preferences.route_fullscreen
        route = _clamp_bounds(preferences.route_window.model_dump(), 1400, 900)
        self.route_window = webview.create_window(
            f"Active Route — {APP_TITLE}",
            f"{self.server.url}/flight-board",
            js_api=self.bridge,
            width=route["width"],
            height=route["height"],
            x=route["x"],
            y=route["y"],
            min_size=(780, 560),
            background_color="#030404",
            text_select=True,
            frameless=True,
            easy_drag=False,
            on_top=preferences.route_always_on_top,
        )
        self.route_window.events.closing += self._route_closing
        self.route_window.events.closed += lambda: setattr(self, "route_window", None)
        self.route_window.events.moved += lambda x, y: self.queue_window_persist("route", x=x, y=y)
        self.route_window.events.resized += lambda width, height: self.queue_window_persist(
            "route", width=width, height=height
        )
        if self.route_fullscreen:
            def fullscreen_once() -> None:
                self.route_window.events.shown -= fullscreen_once
                self.route_window.toggle_fullscreen()

            self.route_window.events.shown += fullscreen_once

    def _route_closing(self, *_args):
        self.route_window = None
        return True

    def close_route_console(self) -> None:
        if self.route_window:
            window = self.route_window
            self.route_window = None
            window.destroy()

    def set_route_fullscreen(self, enabled: bool) -> None:
        preferences = self.preferences()
        if self.route_fullscreen != enabled and self.route_window:
            self.route_window.toggle_fullscreen()
        self.route_fullscreen = enabled
        from .api import _save_preferences
        from .database import SessionLocal

        preferences.route_fullscreen = enabled
        with SessionLocal() as session:
            _save_preferences(session, preferences)

    def set_route_always_on_top(self, enabled: bool) -> None:
        preferences = self.preferences()
        preferences.route_always_on_top = enabled
        if self.route_window:
            self.route_window.on_top = enabled
        from .api import _save_preferences
        from .database import SessionLocal

        with SessionLocal() as session:
            _save_preferences(session, preferences)

    def _ensure_tray(self) -> None:
        if self._tray:
            return
        try:
            import pystray
            from PIL import Image

            icon_path = resource_path("assets", "ion.ico")
            image = Image.open(icon_path)
            self._tray = pystray.Icon(
                "ION",
                image,
                APP_TITLE,
                menu=pystray.Menu(
                    pystray.MenuItem("Open ION", lambda _icon, _item: self.show_main(), default=True),
                    pystray.MenuItem("Open Active Route", lambda _icon, _item: self.open_route_console()),
                    pystray.MenuItem(
                        "Pause Game Link",
                        lambda _icon, item: self.bridge.pause_game_link(not item.checked),
                        checked=lambda _item: __import__(
                            "elite_logistics.elite_monitor", fromlist=["elite_monitor"]
                        ).elite_monitor.paused,
                    ),
                    pystray.Menu.SEPARATOR,
                    pystray.MenuItem("Exit", lambda _icon, _item: self.exit()),
                ),
            )
            threading.Thread(target=self._tray.run, name="ion-tray", daemon=True).start()
        except Exception:
            # Full exit remains available from the taskbar if tray startup fails.
            self.main_window.show()

    def exit(self) -> None:
        if self._exiting:
            return
        self._exiting = True
        if self._tray:
            self._tray.stop()
        for kind in ("main", "route"):
            timer = self._persist_timers.get(kind)
            if timer:
                timer.cancel()
            self._flush_window_persist(kind)
        if self.route_window:
            self.route_window.destroy()
        if self.main_window:
            self.main_window.destroy()


def run_smoke_test() -> int:
    server = LocalApiServer(startup_timeout_seconds=10)
    try:
        server.start()
        if sys.stdout is not None:
            print(f"Desktop service ready at {server.url}")
        return 0
    finally:
        server.stop()


def run_desktop() -> int:
    configure_logging()
    instance = SingleInstance()
    try:
        if not instance.acquire():
            focus_existing_window()
            return 0
    except Exception as exc:
        show_error_dialog(str(exc))
        return 1

    server = LocalApiServer(port=int(os.getenv("ELITE_LOGISTICS_DESKTOP_PORT", str(DEFAULT_DESKTOP_PORT))))
    shell: DesktopShell | None = None
    try:
        server.start()
        try:
            import webview
        except ImportError as exc:
            raise RuntimeError("The desktop window component is not installed.") from exc
        os.environ["ION_WEBVIEW2_AVAILABLE"] = "1"
        shell = DesktopShell(server)
        shell.create_windows()
        from .updater import schedule_startup_check

        schedule_startup_check()
        smoke_seconds = float(os.getenv("ELITE_LOGISTICS_DESKTOP_SMOKE_SECONDS", "0"))

        def startup() -> None:
            if smoke_seconds:
                time.sleep(smoke_seconds)
                shell.exit()

        webview.start(
            startup if smoke_seconds else None,
            gui="edgechromium",
            debug=os.getenv("ELITE_LOGISTICS_DESKTOP_DEBUG") == "1",
            private_mode=False,
            storage_path=str(get_settings().paths.webview),
        )
        return 0
    except Exception as exc:
        show_error_dialog(f"ION could not start.\n\n{exc}\n\nVersion {APP_VERSION}")
        return 1
    finally:
        server.stop()
        instance.close()


def main() -> None:
    if "--smoke-test" in sys.argv:
        raise SystemExit(run_smoke_test())
    if "--window-smoke-test" in sys.argv:
        os.environ["ELITE_LOGISTICS_DESKTOP_SMOKE_SECONDS"] = "2"
    raise SystemExit(run_desktop())


if __name__ == "__main__":
    main()
