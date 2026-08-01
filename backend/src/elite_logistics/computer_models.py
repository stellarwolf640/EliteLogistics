"""Optional constrained local-model providers for Computer Lite and Enhanced."""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import socket
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from .computer import EXECUTABLE_TOOL_NAMES, TOOLS_BY_NAME
from .schemas import ComputerPreferences


MODEL_MANIFEST_SCHEMA = 1
MODEL_EVALUATION_CASES = (
    ("Give me a status report", "get_operational_snapshot"),
    ("Where am I right now?", "get_operational_snapshot"),
    ("What cargo is aboard?", "get_cargo_manifest"),
    ("Show my next operation instruction", "get_next_instruction"),
    ("Open the route console", "open_route_console"),
)
MODEL_ALLOWED_TOOLS = frozenset(
    name
    for name in EXECUTABLE_TOOL_NAMES
    if TOOLS_BY_NAME[name].category not in {"game_control", "preferences"}
)


def _total_memory_mb() -> int:
    if os.name == "nt":
        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("length", ctypes.c_uint32),
                ("memory_load", ctypes.c_uint32),
                ("total_physical", ctypes.c_uint64),
                ("available_physical", ctypes.c_uint64),
                ("total_page_file", ctypes.c_uint64),
                ("available_page_file", ctypes.c_uint64),
                ("total_virtual", ctypes.c_uint64),
                ("available_virtual", ctypes.c_uint64),
                ("available_extended_virtual", ctypes.c_uint64),
            ]

        status = MemoryStatus()
        status.length = ctypes.sizeof(status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return int(status.total_physical // (1024 * 1024))
    return 0


def hardware_profile() -> dict[str, Any]:
    return {
        "cpu_threads": os.cpu_count() or 1,
        "total_ram_mb": _total_memory_mb(),
        "gpu_detection": "configured_layers_only",
        "platform": os.name,
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass(frozen=True)
class VerifiedModel:
    tier: str
    version: str
    manifest_path: Path
    model_path: Path
    sha256: str
    estimated_memory_mb: int


def verify_model_manifest(path_value: str, expected_tier: str) -> tuple[VerifiedModel | None, str | None]:
    if not path_value.strip():
        return None, "not_configured"
    path = Path(path_value).expanduser().resolve()
    if not path.is_file():
        return None, "manifest_missing"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, "manifest_corrupt"
    if (
        payload.get("schema_version") != MODEL_MANIFEST_SCHEMA
        or payload.get("tier") != expected_tier
    ):
        return None, "manifest_incompatible"
    model_name = str(payload.get("model_file") or "")
    model_path = (path.parent / model_name).resolve()
    if path.parent not in model_path.parents or not model_path.is_file():
        return None, "model_missing"
    expected_hash = str(payload.get("sha256") or "").casefold()
    if len(expected_hash) != 64:
        return None, "checksum_missing"
    try:
        actual_hash = _sha256(model_path)
    except OSError:
        return None, "model_unreadable"
    if actual_hash.casefold() != expected_hash:
        return None, "checksum_failed"
    return (
        VerifiedModel(
            tier=expected_tier,
            version=str(payload.get("version") or "unknown")[:80],
            manifest_path=path,
            model_path=model_path,
            sha256=actual_hash,
            estimated_memory_mb=max(0, int(payload.get("estimated_memory_mb") or 0)),
        ),
        None,
    )


class LocalModelManager:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._process: subprocess.Popen[str] | None = None
        self._port: int | None = None
        self._active: VerifiedModel | None = None
        self._last_error: str | None = None
        self._last_latency_ms: float | None = None
        self._evaluation_score: float | None = None

    def _configured_models(
        self, preferences: ComputerPreferences
    ) -> dict[str, tuple[VerifiedModel | None, str | None]]:
        return {
            "lite": verify_model_manifest(
                preferences.lite_model_manifest, "lite"
            ),
            "enhanced": verify_model_manifest(
                preferences.enhanced_model_manifest, "enhanced"
            ),
        }

    def status(self, preferences: ComputerPreferences) -> dict[str, Any]:
        models = self._configured_models(preferences)
        executable = (
            Path(preferences.model_server_path).expanduser().resolve()
            if preferences.model_server_path.strip()
            else None
        )
        with self._lock:
            running = self._process is not None and self._process.poll() is None
            active = self._active
        requested = preferences.mode
        if requested == "automatic":
            requested = (
                "enhanced"
                if models["enhanced"][0] is not None and _total_memory_mb() >= 16384
                else "lite"
            )
        selected = models.get(requested, (None, None))[0]
        if selected is None and requested == "enhanced":
            selected = models["lite"][0]
        evaluation_current = bool(
            selected is not None
            and preferences.model_evaluated_sha256 == selected.sha256
            and preferences.model_evaluation_score is not None
            and preferences.model_evaluation_score
            >= preferences.model_evaluation_threshold
        )
        return {
            "enabled": preferences.model_runtime_enabled,
            "server_available": bool(executable and executable.is_file()),
            "server_path": str(executable) if executable else None,
            "running": running,
            "active_tier": active.tier if active and running else None,
            "active_version": active.version if active and running else None,
            "active_sha256": active.sha256 if active and running else None,
            "lite": {
                "verified": models["lite"][0] is not None,
                "version": models["lite"][0].version if models["lite"][0] else None,
                "status": models["lite"][1] or "ready",
            },
            "enhanced": {
                "verified": models["enhanced"][0] is not None,
                "version": models["enhanced"][0].version if models["enhanced"][0] else None,
                "status": models["enhanced"][1] or "ready",
            },
            "hardware": hardware_profile(),
            "context_tokens": preferences.model_context_tokens,
            "memory_limit_mb": preferences.model_memory_limit_mb,
            "gpu_layers": preferences.model_gpu_layers,
            "evaluation_score": (
                preferences.model_evaluation_score
            ),
            "evaluation_threshold": preferences.model_evaluation_threshold,
            "evaluation_current": evaluation_current,
            "last_latency_ms": self._last_latency_ms,
            "last_error": self._last_error,
            "safety": {
                "local_loopback_only": True,
                "live_elite_context": False,
                "direct_game_control": False,
                "permission_changes": False,
                "policy_executor_required": True,
                "frontier_public_release_clearance": bool(
                    os.getenv("ION_FRONTIER_AI_CLEARANCE_REFERENCE", "").strip()
                ),
            },
        }

    def _select(
        self, preferences: ComputerPreferences
    ) -> VerifiedModel:
        if not preferences.model_runtime_enabled:
            raise RuntimeError("The optional local-model runtime is disabled.")
        models = self._configured_models(preferences)
        requested = preferences.mode
        if requested == "automatic":
            ram = _total_memory_mb()
            requested = (
                "enhanced"
                if models["enhanced"][0] is not None and ram >= 16384
                else "lite"
            )
        if requested not in {"lite", "enhanced"}:
            raise RuntimeError("Select Lite, Enhanced, or Automatic mode.")
        model, error = models[requested]
        if model is None:
            if requested == "enhanced" and models["lite"][0] is not None:
                model = models["lite"][0]
            else:
                raise RuntimeError(
                    f"The {requested} model component is unavailable: {error}."
                )
        if (
            model.estimated_memory_mb
            and model.estimated_memory_mb > preferences.model_memory_limit_mb
        ):
            if model.tier == "enhanced" and models["lite"][0] is not None:
                model = models["lite"][0]
            else:
                raise RuntimeError(
                    "The configured model exceeds the Computer memory limit."
                )
        return model

    @staticmethod
    def _available_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as candidate:
            candidate.bind(("127.0.0.1", 0))
            return int(candidate.getsockname()[1])

    def _ensure_started(
        self, preferences: ComputerPreferences
    ) -> VerifiedModel:
        model = self._select(preferences)
        executable = Path(preferences.model_server_path).expanduser().resolve()
        if not executable.is_file():
            raise RuntimeError("The configured local llama.cpp server was not found.")
        with self._lock:
            if (
                self._process is not None
                and self._process.poll() is None
                and self._active == model
            ):
                return model
            self.stop()
            port = self._available_port()
            creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            command = [
                str(executable),
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--model",
                str(model.model_path),
                "--ctx-size",
                str(preferences.model_context_tokens),
                "--n-gpu-layers",
                str(preferences.model_gpu_layers),
                "--no-webui",
            ]
            self._process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
                creationflags=creation_flags,
            )
            self._port = port
            self._active = model
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            with self._lock:
                process = self._process
            if process is None or process.poll() is not None:
                self._last_error = "The local model server stopped during startup."
                self.stop()
                raise RuntimeError(self._last_error)
            try:
                response = httpx.get(
                    f"http://127.0.0.1:{port}/health",
                    timeout=0.5,
                )
                if response.status_code == 200:
                    self._last_error = None
                    return model
            except httpx.HTTPError:
                pass
            time.sleep(0.15)
        self._last_error = "The local model server did not become ready."
        self.stop()
        raise RuntimeError(self._last_error)

    def interpret(
        self, text: str, preferences: ComputerPreferences
    ) -> dict[str, Any]:
        model = self._ensure_started(preferences)
        allowed = [
            {
                "name": name,
                "description": TOOLS_BY_NAME[name].description,
            }
            for name in sorted(MODEL_ALLOWED_TOOLS)
        ]
        prompt = (
            "Return JSON only with keys tool_name, arguments, clarification. "
            "Choose exactly one allowlisted tool or set tool_name to null and "
            "ask a concise clarification. Never invent a tool result. "
            f"Allowlisted tools: {json.dumps(allowed)}\n"
            f"Commander request: {text}"
        )
        started = time.monotonic()
        try:
            response = httpx.post(
                f"http://127.0.0.1:{self._port}/v1/chat/completions",
                json={
                    "model": model.version,
                    "temperature": 0,
                    "max_tokens": 300,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You are ION's constrained local intent parser. "
                                "You have no game, database, filesystem, or control access."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "response_format": {"type": "json_object"},
                },
                timeout=30,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            decision = json.loads(content)
        except (httpx.HTTPError, KeyError, IndexError, json.JSONDecodeError) as exc:
            self._last_error = f"Local model interpretation failed: {exc}"
            raise RuntimeError(self._last_error) from exc
        finally:
            self._last_latency_ms = round(
                (time.monotonic() - started) * 1000, 1
            )
        tool_name = decision.get("tool_name")
        if tool_name is not None and tool_name not in MODEL_ALLOWED_TOOLS:
            raise RuntimeError("The local model selected a prohibited tool.")
        arguments = decision.get("arguments") or {}
        if not isinstance(arguments, dict):
            raise RuntimeError("The local model returned invalid tool arguments.")
        clarification = decision.get("clarification")
        return {
            "tier": model.tier,
            "version": model.version,
            "tool_name": tool_name,
            "arguments": arguments,
            "clarification": str(clarification)[:500] if clarification else None,
            "latency_ms": self._last_latency_ms,
        }

    def evaluate(self, preferences: ComputerPreferences) -> dict[str, Any]:
        passed = 0
        results = []
        for text, expected in MODEL_EVALUATION_CASES:
            try:
                decision = self.interpret(text, preferences)
                actual = decision.get("tool_name")
                success = actual == expected
            except RuntimeError as exc:
                actual = None
                success = False
                decision = {"error": str(exc)}
            passed += int(success)
            results.append(
                {
                    "text": text,
                    "expected": expected,
                    "actual": actual,
                    "passed": success,
                    "error": decision.get("error"),
                }
            )
        score = passed / len(MODEL_EVALUATION_CASES)
        self._evaluation_score = score
        return {
            "score": score,
            "threshold": preferences.model_evaluation_threshold,
            "passed": score >= preferences.model_evaluation_threshold,
            "cases": results,
            "model_sha256": self._active.sha256 if self._active else None,
        }

    def stop(self) -> None:
        with self._lock:
            process = self._process
            self._process = None
            self._port = None
            self._active = None
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)


local_model_manager = LocalModelManager()
