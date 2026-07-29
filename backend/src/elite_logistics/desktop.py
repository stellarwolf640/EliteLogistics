from __future__ import annotations

import ctypes
import os
import socket
import sys
import threading
import time
from dataclasses import dataclass
from urllib.error import URLError
from urllib.request import urlopen

import uvicorn

from .config import get_settings
from .main import create_app


APP_TITLE = "ION — IntraStellar Operations Network"
MUTEX_NAME = "Local\\EliteLogisticsDesktop"
ERROR_ALREADY_EXISTS = 183
DEFAULT_DESKTOP_PORT = 8766


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
        )
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(
            target=self.server.run,
            name="elite-logistics-api",
            daemon=True,
        )
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


def run_smoke_test() -> int:
    server = LocalApiServer(startup_timeout_seconds=10)
    try:
        server.start()
        print(f"Desktop service ready at {server.url}")
        return 0
    finally:
        server.stop()


def run_desktop() -> int:
    instance = SingleInstance()
    try:
        if not instance.acquire():
            focus_existing_window()
            return 0
    except Exception as exc:
        show_error_dialog(str(exc))
        return 1

    server = LocalApiServer(
        port=int(os.getenv("ELITE_LOGISTICS_DESKTOP_PORT", str(DEFAULT_DESKTOP_PORT)))
    )
    try:
        server.start()
        try:
            import webview
        except ImportError as exc:
            raise RuntimeError(
                "The desktop window component is not installed. Run start.ps1 again."
            ) from exc

        window = webview.create_window(
            APP_TITLE,
            server.url,
            width=1500,
            height=950,
            min_size=(1050, 700),
            background_color="#030404",
            text_select=True,
        )
        smoke_seconds = float(os.getenv("ELITE_LOGISTICS_DESKTOP_SMOKE_SECONDS", "0"))

        def close_smoke_window() -> None:
            time.sleep(smoke_seconds)
            window.destroy()

        storage_path = get_settings().data_dir / "webview"
        storage_path.mkdir(parents=True, exist_ok=True)
        webview.start(
            close_smoke_window if smoke_seconds > 0 else None,
            gui="edgechromium",
            debug=os.getenv("ELITE_LOGISTICS_DESKTOP_DEBUG") == "1",
            private_mode=False,
            storage_path=str(storage_path),
        )
        return 0
    except Exception as exc:
        show_error_dialog(
            f"ION could not start.\n\n{exc}\n\n"
            "If this continues, run start.ps1 once from PowerShell to see installation details."
        )
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
