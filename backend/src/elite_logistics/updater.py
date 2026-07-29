from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import sys
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .config import get_settings, resource_path
from .events import event_bus
from .version import APP_VERSION

REPOSITORY = "stellarwolf640/EliteLogistics"
RELEASE_URL = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
CHECK_INTERVAL = timedelta(hours=24)


def _version_tuple(value: str) -> tuple[int, int, int]:
    clean = value.strip().removeprefix("v")
    parts = clean.split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        raise ValueError(f"Unsupported semantic version: {value}")
    return tuple(int(part) for part in parts)  # type: ignore[return-value]


class UpdateService:
    def __init__(self):
        self._lock = threading.Lock()
        self._state: dict[str, Any] = {
            "status": "idle",
            "installed_version": APP_VERSION,
            "available_version": None,
            "release_notes": "",
            "progress": 0,
            "error": None,
            "installer_path": None,
        }
        self._release: dict[str, Any] | None = None
        self._manifest: dict[str, Any] | None = None

    def status(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._state)

    def _set(self, **changes: Any) -> None:
        with self._lock:
            self._state.update(changes)
            value = dict(self._state)
        event_bus.publish("update.progressed", value)

    def check(self, force: bool = False) -> dict[str, Any]:
        from .api import _load_preferences, _save_preferences
        from .database import SessionLocal

        with SessionLocal() as session:
            preferences = _load_preferences(session)
            last = preferences.update_last_checked_at
            if not force and last and datetime.now(UTC) - last.astimezone(UTC) < CHECK_INTERVAL:
                return self.status()
            preferences.update_last_checked_at = datetime.now(UTC)
            _save_preferences(session, preferences)
        self._set(status="checking", error=None)
        try:
            with httpx.Client(timeout=15, follow_redirects=True, headers={"User-Agent": f"ION/{APP_VERSION}"}) as client:
                release = client.get(RELEASE_URL).raise_for_status().json()
                if release.get("draft") or release.get("prerelease"):
                    self._set(status="current", available_version=None)
                    return self.status()
                version = str(release.get("tag_name", "")).removeprefix("v")
                if _version_tuple(version) <= _version_tuple(APP_VERSION):
                    self._set(status="current", available_version=None)
                    return self.status()
                assets = {asset["name"]: asset for asset in release.get("assets", [])}
                manifest_asset = assets.get("update-manifest.json")
                signature_asset = assets.get("update-manifest.sig")
                if not manifest_asset or not signature_asset:
                    raise ValueError("The release does not include a signed update manifest.")
                manifest_bytes = client.get(manifest_asset["browser_download_url"]).raise_for_status().content
                signature_bytes = client.get(signature_asset["browser_download_url"]).raise_for_status().content
                self._verify_manifest(manifest_bytes, signature_bytes)
                manifest = json.loads(manifest_bytes)
                if manifest.get("version") != version:
                    raise ValueError("Release tag and update manifest version do not match.")
                installer = assets.get(manifest.get("asset"))
                if not installer:
                    raise ValueError("The installer named by the manifest is missing.")
                self._release = release
                self._manifest = {**manifest, "download_url": installer["browser_download_url"]}
                self._set(
                    status="available",
                    available_version=version,
                    release_notes=str(release.get("body") or manifest.get("release_notes") or ""),
                    progress=0,
                )
        except Exception as exc:
            self._set(status="error", error=str(exc))
        return self.status()

    def _verify_manifest(self, content: bytes, signature: bytes) -> None:
        public_path = resource_path("assets", "update-public-key.txt")
        encoded = public_path.read_text(encoding="ascii").strip()
        if not encoded or encoded.startswith("CONFIGURE_"):
            raise ValueError("ION's release verification key has not been configured.")
        public_key = Ed25519PublicKey.from_public_bytes(base64.b64decode(encoded))
        try:
            public_key.verify(base64.b64decode(signature.strip()), content)
        except (InvalidSignature, ValueError) as exc:
            raise ValueError("The update manifest signature is invalid.") from exc

    def begin_download(self) -> None:
        if not self._manifest:
            raise RuntimeError("Check for an update before downloading.")
        if self.status()["status"] == "downloading":
            return
        threading.Thread(target=self._download, name="ion-update-download", daemon=True).start()

    def _download(self) -> None:
        assert self._manifest
        manifest = self._manifest
        destination = get_settings().paths.updates / str(manifest["asset"])
        temporary = destination.with_suffix(destination.suffix + ".part")
        self._set(status="downloading", progress=0, error=None)
        try:
            digest = hashlib.sha256()
            received = 0
            expected = int(manifest["size"])
            with httpx.stream("GET", manifest["download_url"], follow_redirects=True, timeout=None) as response:
                response.raise_for_status()
                with temporary.open("wb") as target:
                    for chunk in response.iter_bytes(1024 * 1024):
                        target.write(chunk)
                        digest.update(chunk)
                        received += len(chunk)
                        self._set(
                            status="downloading",
                            progress=min(1, received / expected) if expected else 0,
                            downloaded_bytes=received,
                            total_bytes=expected,
                        )
            if received != expected:
                raise ValueError(f"Installer size mismatch ({received} received; {expected} expected).")
            if digest.hexdigest().casefold() != str(manifest["sha256"]).casefold():
                raise ValueError("Installer SHA-256 verification failed.")
            temporary.replace(destination)
            self._set(status="ready", progress=1, installer_path=str(destination))
        except Exception as exc:
            temporary.unlink(missing_ok=True)
            self._set(status="error", error=str(exc))


update_service = UpdateService()


def schedule_startup_check(delay_seconds: float = 8) -> None:
    def run() -> None:
        threading.Event().wait(delay_seconds)
        update_service.check(force=False)

    threading.Thread(target=run, name="ion-update-check", daemon=True).start()


def install_downloaded_update(exit_callback: Callable[[], None]) -> None:
    state = update_service.status()
    path = Path(str(state.get("installer_path") or ""))
    if state.get("status") != "ready" or not path.is_file():
        raise RuntimeError("No verified ION update is ready to install.")
    subprocess.Popen(
        [
            str(path),
            "/VERYSILENT",
            "/SUPPRESSMSGBOXES",
            "/CLOSEAPPLICATIONS",
            "/RESTARTAPPLICATIONS",
            "/RELAUNCH=1",
        ],
        close_fds=True,
    )
    threading.Timer(0.25, exit_callback).start()
