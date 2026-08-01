"""Windows-local, allowlisted one-shot input bridge for Elite Dangerous."""

from __future__ import annotations

import ctypes
import json
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .computer import CONTROLS_BY_ID
from .elite_bindings import ParsedBinding, binding_report
from .events import event_bus


STATE_BITS = {
    "landing_gear": 4,
    "hardpoints": 64,
    "ship_lights": 256,
    "cargo_scoop": 512,
    "night_vision": 268435456,
}

_NAMED_VIRTUAL_KEYS = {
    "BACKSPACE": 0x08,
    "TAB": 0x09,
    "RETURN": 0x0D,
    "ENTER": 0x0D,
    "SHIFT": 0x10,
    "LEFTSHIFT": 0xA0,
    "RIGHTSHIFT": 0xA1,
    "CONTROL": 0x11,
    "LEFTCONTROL": 0xA2,
    "RIGHTCONTROL": 0xA3,
    "ALT": 0x12,
    "LEFTALT": 0xA4,
    "RIGHTALT": 0xA5,
    "PAUSE": 0x13,
    "CAPSLOCK": 0x14,
    "ESCAPE": 0x1B,
    "SPACE": 0x20,
    "PAGEUP": 0x21,
    "PAGEDOWN": 0x22,
    "END": 0x23,
    "HOME": 0x24,
    "LEFTARROW": 0x25,
    "UPARROW": 0x26,
    "RIGHTARROW": 0x27,
    "DOWNARROW": 0x28,
    "INSERT": 0x2D,
    "DELETE": 0x2E,
    "NUMPAD0": 0x60,
    "NUMPAD1": 0x61,
    "NUMPAD2": 0x62,
    "NUMPAD3": 0x63,
    "NUMPAD4": 0x64,
    "NUMPAD5": 0x65,
    "NUMPAD6": 0x66,
    "NUMPAD7": 0x67,
    "NUMPAD8": 0x68,
    "NUMPAD9": 0x69,
    "MULTIPLY": 0x6A,
    "ADD": 0x6B,
    "SUBTRACT": 0x6D,
    "DECIMAL": 0x6E,
    "DIVIDE": 0x6F,
    "SEMICOLON": 0xBA,
    "EQUALS": 0xBB,
    "COMMA": 0xBC,
    "MINUS": 0xBD,
    "PERIOD": 0xBE,
    "SLASH": 0xBF,
    "GRAVE": 0xC0,
    "LEFTBRACKET": 0xDB,
    "BACKSLASH": 0xDC,
    "RIGHTBRACKET": 0xDD,
    "APOSTROPHE": 0xDE,
}
_NAMED_VIRTUAL_KEYS.update({f"F{number}": 0x6F + number for number in range(1, 25)})


def _virtual_key(elite_key: str) -> int | None:
    value = elite_key.removeprefix("Key_").replace("_", "").upper()
    if len(value) == 1 and value.isalnum():
        return ord(value)
    return _NAMED_VIRTUAL_KEYS.get(value)


def keyboard_binding_supported(binding: ParsedBinding | dict[str, Any]) -> bool:
    key = binding.key if isinstance(binding, ParsedBinding) else str(binding.get("key", ""))
    modifiers = (
        binding.modifiers
        if isinstance(binding, ParsedBinding)
        else tuple(str(value) for value in binding.get("modifiers", []))
    )
    return all(_virtual_key(value) is not None for value in (*modifiers, key))


def _read_status(directory: Path) -> dict[str, Any]:
    try:
        payload = json.loads((directory / "Status.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _foreground_is_elite() -> bool:
    if os.name != "nt":
        return False

    class ProcessEntry32(ctypes.Structure):
        _fields_ = [
            ("dwSize", ctypes.c_uint32),
            ("cntUsage", ctypes.c_uint32),
            ("th32ProcessID", ctypes.c_uint32),
            ("th32DefaultHeapID", ctypes.c_void_p),
            ("th32ModuleID", ctypes.c_uint32),
            ("cntThreads", ctypes.c_uint32),
            ("th32ParentProcessID", ctypes.c_uint32),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", ctypes.c_uint32),
            ("szExeFile", ctypes.c_wchar * 260),
        ]

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32.GetForegroundWindow.restype = ctypes.c_void_p
    user32.GetWindowThreadProcessId.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_uint32),
    ]
    kernel32.CreateToolhelp32Snapshot.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
    kernel32.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
    kernel32.Process32FirstW.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ProcessEntry32),
    ]
    kernel32.Process32NextW.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ProcessEntry32),
    ]
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    foreground = user32.GetForegroundWindow()
    if not foreground:
        return False
    pid = ctypes.c_uint32()
    user32.GetWindowThreadProcessId(foreground, ctypes.byref(pid))
    snapshot = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
    if snapshot == ctypes.c_void_p(-1).value:
        return False
    try:
        entry = ProcessEntry32()
        entry.dwSize = ctypes.sizeof(entry)
        if not kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
            return False
        while True:
            if entry.th32ProcessID == pid.value:
                return entry.szExeFile.casefold().startswith("elitedangerous")
            if not kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                return False
    finally:
        kernel32.CloseHandle(snapshot)


def _send_keyboard_binding(binding: ParsedBinding) -> None:
    if os.name != "nt":
        raise RuntimeError("The Input Bridge is only available on Windows.")
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    keys = [*binding.modifiers, binding.key]
    virtual_keys = [_virtual_key(key) for key in keys]
    if any(key is None for key in virtual_keys):
        unsupported = keys[virtual_keys.index(None)]
        raise ValueError(f"Elite binding key {unsupported!r} is not supported by ION.")
    for key in virtual_keys:
        user32.keybd_event(key, 0, 0, 0)
    time.sleep(0.045)
    for key in reversed(virtual_keys):
        user32.keybd_event(key, 0, 0x0002, 0)


@dataclass(frozen=True)
class BridgeContext:
    bindings_directory: Path
    journal_directory: Path


class InputBridge:
    """Serializes fixed semantic game actions and enforces local preconditions."""

    def __init__(
        self,
        *,
        foreground_checker: Callable[[], bool] = _foreground_is_elite,
        sender: Callable[[ParsedBinding], None] = _send_keyboard_binding,
        status_reader: Callable[[Path], dict[str, Any]] = _read_status,
    ):
        self._foreground_checker = foreground_checker
        self._sender = sender
        self._status_reader = status_reader
        self._command_lock = threading.Lock()
        self._emergency_disabled = threading.Event()
        self._stop = threading.Event()
        self._hotkey_thread: threading.Thread | None = None
        self._last_action_at = 0.0
        self._active_action: str | None = None
        self._last_result: dict[str, Any] | None = None

    def start(self) -> None:
        if os.name != "nt" or (self._hotkey_thread and self._hotkey_thread.is_alive()):
            return
        self._stop.clear()
        self._hotkey_thread = threading.Thread(
            target=self._watch_emergency_hotkey,
            name="ion-input-emergency-hotkey",
            daemon=True,
        )
        self._hotkey_thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._emergency_disabled.set()
        if self._hotkey_thread and self._hotkey_thread.is_alive():
            self._hotkey_thread.join(timeout=2)

    def emergency_disable(self, reason: str = "Commander emergency stop") -> dict[str, Any]:
        self._emergency_disabled.set()
        payload = {"disabled": True, "reason": reason, "active_action": self._active_action}
        event_bus.publish("computer.input_bridge.disabled", payload)
        return self.status()

    def reset_emergency(self) -> dict[str, Any]:
        self._emergency_disabled.clear()
        event_bus.publish("computer.input_bridge.enabled", {"disabled": False})
        return self.status()

    def status(self) -> dict[str, Any]:
        return {
            "available": os.name == "nt",
            "platform": "windows" if os.name == "nt" else os.name,
            "emergency_disabled": self._emergency_disabled.is_set(),
            "emergency_hotkey": "Ctrl + Shift + Pause",
            "busy": self._command_lock.locked(),
            "active_action": self._active_action,
            "last_result": self._last_result,
            "minimum_interval_seconds": 0.4,
        }

    def execute(
        self,
        action_id: str,
        desired_state: bool | None,
        context: BridgeContext,
        *,
        verification_timeout: float = 2.0,
    ) -> dict[str, Any]:
        action = CONTROLS_BY_ID.get(action_id)
        if action is None or not action.initial_release:
            raise ValueError("This action is not in the Input Bridge allowlist.")
        if action.desired_state and desired_state is None:
            raise ValueError("This control requires an explicit desired state.")
        if not action.desired_state and desired_state is not None:
            raise ValueError("This one-shot control does not accept a desired state.")
        if self._emergency_disabled.is_set():
            raise RuntimeError("The Input Bridge is emergency-disabled.")
        if not self._command_lock.acquire(blocking=False):
            raise RuntimeError("Another game-control action is already in progress.")
        self._active_action = action_id
        action_started_at = time.monotonic()
        try:
            binding = self._keyboard_binding(action_id, context.bindings_directory)
            current = self._state(action_id, context.journal_directory)
            if current is not None and current == desired_state:
                result = {
                    "action_id": action_id,
                    "outcome": "already_set",
                    "desired_state": desired_state,
                    "input_sent": False,
                    "verified": True,
                    "binding": binding.display,
                    "latency_ms": round(
                        (time.monotonic() - action_started_at) * 1000, 1
                    ),
                }
                self._last_result = result
                return result
            elapsed = time.monotonic() - self._last_action_at
            if elapsed < 0.4:
                raise RuntimeError("Game controls are rate-limited; wait briefly and try again.")
            if not self._foreground_checker():
                raise RuntimeError("Elite Dangerous must be running in the foreground.")
            if self._emergency_disabled.is_set():
                raise RuntimeError("The Input Bridge was emergency-disabled before input.")
            if not self._foreground_checker():
                raise RuntimeError("Elite Dangerous lost foreground focus before input.")
            event_bus.publish("computer.control.started", {"action_id": action_id})
            self._sender(binding)
            self._last_action_at = time.monotonic()
            if current is None:
                result = {
                    "action_id": action_id,
                    "outcome": "sent_unverified",
                    "desired_state": desired_state,
                    "input_sent": True,
                    "verified": False,
                    "binding": binding.display,
                }
            else:
                result = self._wait_for_state(
                    action_id,
                    bool(desired_state),
                    context.journal_directory,
                    verification_timeout,
                    binding,
                )
            self._last_result = result
            result["latency_ms"] = round(
                (time.monotonic() - action_started_at) * 1000, 1
            )
            event_bus.publish("computer.control.completed", result)
            return result
        finally:
            self._active_action = None
            self._command_lock.release()

    def _keyboard_binding(self, action_id: str, directory: Path) -> ParsedBinding:
        report = binding_report(directory)
        if not report["available"]:
            raise RuntimeError(report["warning"] or "Elite bindings are unavailable.")
        capability = next(
            (item for item in report["capabilities"] if item["action_id"] == action_id),
            None,
        )
        if capability is None or capability["status"] == "unbound":
            raise RuntimeError("This Elite action is unbound.")
        if capability["status"] == "conflict":
            raise RuntimeError("This binding conflicts with another ION action.")
        slots = (capability["secondary"], capability["primary"])
        slot = next(
            (
                value
                for value in slots
                if value
                and value["device_kind"] == "keyboard"
                and keyboard_binding_supported(value)
            ),
            None,
        )
        if slot is None:
            has_keyboard = any(
                value and value["device_kind"] == "keyboard" for value in slots
            )
            raise RuntimeError(
                "This Elite keyboard binding uses a key ION does not support."
                if has_keyboard
                else "This action requires a keyboard binding in Elite; HOTAS-only bindings cannot be sent."
            )
        return ParsedBinding(
            device=slot["device"],
            key=slot["key"],
            modifiers=tuple(slot["modifiers"]),
        )

    def _state(self, action_id: str, directory: Path) -> bool | None:
        bit = STATE_BITS.get(action_id)
        if bit is None:
            return None
        payload = self._status_reader(directory)
        if "Flags" not in payload:
            return None
        return bool(int(payload.get("Flags", 0)) & bit)

    def _wait_for_state(
        self,
        action_id: str,
        desired_state: bool,
        directory: Path,
        timeout: float,
        binding: ParsedBinding,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._emergency_disabled.wait(0.08):
                raise RuntimeError("The Input Bridge was emergency-disabled while verifying.")
            if self._state(action_id, directory) == desired_state:
                return {
                    "action_id": action_id,
                    "outcome": "verified",
                    "desired_state": desired_state,
                    "input_sent": True,
                    "verified": True,
                    "binding": binding.display,
                }
        return {
            "action_id": action_id,
            "outcome": "timed_out",
            "desired_state": desired_state,
            "input_sent": True,
            "verified": False,
            "binding": binding.display,
            "warning": "Elite telemetry did not confirm the requested state; ION did not retry.",
        }

    def _watch_emergency_hotkey(self) -> None:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        latched = False
        while not self._stop.wait(0.05):
            pressed = all(
                user32.GetAsyncKeyState(key) & 0x8000
                for key in (0x11, 0x10, 0x13)
            )
            if pressed and not latched:
                self.emergency_disable("Emergency hotkey pressed")
            latched = pressed


input_bridge = InputBridge()
