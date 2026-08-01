from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


APP_VENDOR = "IntraStellar Logistics"
APP_NAME = "ION"


@dataclass(frozen=True)
class RuntimePaths:
    root: Path
    database: Path
    cache: Path
    downloads: Path
    logs: Path
    updates: Path
    webview: Path
    models: Path

    def create(self) -> "RuntimePaths":
        for path in (
            self.root,
            self.cache,
            self.downloads,
            self.logs,
            self.updates,
            self.webview,
            self.models,
        ):
            path.mkdir(parents=True, exist_ok=True)
        return self


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    database_url: str
    paths: RuntimePaths
    packaged: bool
    spansh_base_url: str = "https://www.spansh.co.uk/api"
    request_timeout_seconds: float = 12.0
    remote_concurrency: int = 6


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resource_path(*parts: str) -> Path:
    """Resolve bundled resources in source and PyInstaller one-folder builds."""
    if is_frozen():
        root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    else:
        root = Path(__file__).resolve().parents[3]
    return root.joinpath(*parts)


def _runtime_root() -> Path:
    override = os.getenv("ELITE_LOGISTICS_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if is_frozen():
        local = os.getenv("LOCALAPPDATA")
        if not local:
            raise RuntimeError("LOCALAPPDATA is unavailable; ION cannot create its profile.")
        return (Path(local) / APP_VENDOR / APP_NAME).resolve()
    return (Path.cwd() / "data").resolve()


def get_settings() -> Settings:
    data_dir = _runtime_root()
    paths = RuntimePaths(
        root=data_dir,
        database=data_dir / "ion.db",
        cache=data_dir / "cache",
        downloads=data_dir / "downloads",
        logs=data_dir / "logs",
        updates=data_dir / "updates",
        webview=data_dir / "webview",
        models=data_dir / "models",
    ).create()
    database_url = os.getenv(
        "ELITE_LOGISTICS_DATABASE_URL",
        f"sqlite:///{paths.database.as_posix()}",
    )
    return Settings(
        data_dir=data_dir,
        database_url=database_url,
        paths=paths,
        packaged=is_frozen(),
        spansh_base_url=os.getenv("SPANSH_BASE_URL", "https://www.spansh.co.uk/api").rstrip("/"),
    )
