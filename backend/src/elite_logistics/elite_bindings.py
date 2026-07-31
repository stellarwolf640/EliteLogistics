"""Read-only Elite Dangerous binding discovery for ION Computer."""

from __future__ import annotations

import os
import threading
import time
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .computer import CONTROL_ACTIONS
from .database import SessionLocal
from .events import event_bus


ELITE_BINDING_NAMES: dict[str, tuple[str, ...]] = {
    "landing_gear": ("LandingGearToggle",),
    "cargo_scoop": ("ToggleCargoScoop",),
    "hardpoints": ("DeployHardpointToggle",),
    "ship_lights": ("ShipSpotLightToggle",),
    "night_vision": ("NightVisionToggle",),
    "silent_running": ("ToggleButtonUpInput", "SilentRunning"),
    "rotational_correction": (
        "DisableRotationCorrectToggle",
        "ToggleRotationalCorrection",
    ),
    "orbit_lines": ("OrbitLinesToggle",),
    "galaxy_map": ("GalaxyMapOpen",),
    "system_map": ("SystemMapOpen",),
    "navigation_panel": ("FocusLeftPanel", "UIFocusLeft"),
    "communications_panel": ("FocusCommsPanel", "UIFocusUp"),
    "role_panel": ("FocusRadarPanel", "UIFocusDown"),
    "internal_panel": ("FocusRightPanel", "UIFocusRight"),
    "power_balance": ("ResetPowerDistribution",),
    "power_engines": ("IncreaseEnginesPower",),
    "power_systems": ("IncreaseSystemsPower",),
    "power_weapons": ("IncreaseWeaponsPower",),
    "target_ahead": ("SelectTarget",),
    "next_target": ("CycleNextTarget",),
    "next_hostile": ("CycleNextHostileTarget",),
    "next_route_system": ("TargetNextRouteSystem",),
    "fsd_engage": ("HyperSuperCombination", "Hyperspace", "Supercruise"),
    "fsd_cancel": ("HyperSuperCombination", "Hyperspace", "Supercruise"),
    "throttle_zero": ("SetSpeedZero",),
    "throttle_75": ("SetSpeed75",),
    "chaff": ("FireChaffLauncher",),
    "heat_sink": ("DeployHeatSink",),
    "shield_cell": ("UseShieldCell",),
    "ecm": ("ChargeECM",),
}


def default_bindings_directory() -> Path:
    configured = os.getenv("ELITE_LOGISTICS_BINDINGS_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    local = Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return (
        local
        / "Frontier Developments"
        / "Elite Dangerous"
        / "Options"
        / "Bindings"
    )


@dataclass(frozen=True)
class ParsedBinding:
    device: str
    key: str
    modifiers: tuple[str, ...] = ()

    @property
    def device_kind(self) -> str:
        value = self.device.casefold()
        if "keyboard" in value:
            return "keyboard"
        if "mouse" in value:
            return "mouse"
        if any(name in value for name in ("xbox", "gamepad", "controller")):
            return "controller"
        if value and value not in {"none", "{no device}"}:
            return "hotas"
        return "unknown"

    @property
    def display(self) -> str:
        parts = [*self.modifiers, self.key]
        binding = " + ".join(part.replace("Key_", "") for part in parts if part)
        return f"{self.device}: {binding}" if binding else self.device

    @property
    def signature(self) -> str:
        return "|".join(
            (
                self.device.casefold(),
                self.key.casefold(),
                *(value.casefold() for value in self.modifiers),
            )
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "device": self.device,
            "device_kind": self.device_kind,
            "key": self.key,
            "modifiers": list(self.modifiers),
            "display": self.display,
        }


@dataclass
class BindingCapability:
    action_id: str
    label: str
    elite_binding: str | None = None
    primary: ParsedBinding | None = None
    secondary: ParsedBinding | None = None
    status: str = "unbound"
    conflicts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "label": self.label,
            "elite_binding": self.elite_binding,
            "primary": self.primary.to_dict() if self.primary else None,
            "secondary": self.secondary.to_dict() if self.secondary else None,
            "status": self.status,
            "conflicts": self.conflicts,
        }


def _parse_slot(element: ET.Element | None) -> ParsedBinding | None:
    if element is None:
        return None
    device = str(element.attrib.get("Device", "")).strip()
    key = str(element.attrib.get("Key", "")).strip()
    if not device or not key or device.casefold() in {"none", "{no device}"}:
        return None
    modifiers = tuple(
        str(modifier.attrib.get("Key", "")).strip()
        for modifier in element.findall("./Modifier")
        if modifier.attrib.get("Key")
    )
    return ParsedBinding(device=device, key=key, modifiers=modifiers)


def _selected_presets(directory: Path) -> list[str]:
    marker = directory / "StartPreset.start"
    try:
        value = marker.read_text(encoding="utf-8-sig").strip()
    except OSError:
        return []
    return list(dict.fromkeys(line.strip() for line in value.splitlines() if line.strip()))


def locate_active_bindings(directory: Path) -> Path | None:
    if not directory.is_dir():
        return None
    candidates = list(directory.glob("*.binds"))
    if not candidates:
        return None
    for preset in _selected_presets(directory):
        exact = [path for path in candidates if path.stem.casefold() == preset.casefold()]
        if exact:
            return max(exact, key=lambda path: path.stat().st_mtime)
        prefix = [
            path
            for path in candidates
            if path.name.casefold().startswith(f"{preset.casefold()}.")
        ]
        if prefix:
            return max(prefix, key=lambda path: path.stat().st_mtime)
    return max(candidates, key=lambda path: path.stat().st_mtime)


def parse_bindings_file(path: Path) -> dict[str, Any]:
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as exc:
        return {
            "available": False,
            "file_name": path.name,
            "preset": None,
            "capabilities": [],
            "device_kinds": [],
            "conflict_count": 0,
            "warning": f"The active bindings file could not be read: {exc}",
        }

    controls = {control.action_id: control for control in CONTROL_ACTIONS}
    capabilities: list[BindingCapability] = []
    for action_id, control in controls.items():
        element = None
        elite_name = None
        for candidate in ELITE_BINDING_NAMES.get(action_id, ()):
            element = root.find(f"./{candidate}")
            if element is not None:
                elite_name = candidate
                break
        primary = _parse_slot(element.find("./Primary")) if element is not None else None
        secondary = (
            _parse_slot(element.find("./Secondary")) if element is not None else None
        )
        capabilities.append(
            BindingCapability(
                action_id=action_id,
                label=control.label,
                elite_binding=elite_name,
                primary=primary,
                secondary=secondary,
                status="ready" if primary or secondary else "unbound",
            )
        )

    signatures: dict[str, list[BindingCapability]] = {}
    for capability in capabilities:
        for binding in (capability.primary, capability.secondary):
            if binding:
                signatures.setdefault(binding.signature, []).append(capability)
    for matching in signatures.values():
        if len(matching) < 2:
            continue
        action_ids = {capability.action_id for capability in matching}
        # Engage/cancel are two desired outcomes of Elite's single FSD toggle
        # binding, so sharing this binding is expected rather than a conflict.
        if action_ids == {"fsd_engage", "fsd_cancel"}:
            continue
        for capability in matching:
            capability.status = "conflict"
            capability.conflicts = [
                other.action_id
                for other in matching
                if other.action_id != capability.action_id
            ]

    device_kinds = sorted(
        {
            binding.device_kind
            for capability in capabilities
            for binding in (capability.primary, capability.secondary)
            if binding
        }
    )
    return {
        "available": True,
        "file_name": path.name,
        "preset": root.attrib.get("PresetName") or path.stem,
        "major_version": root.attrib.get("MajorVersion"),
        "minor_version": root.attrib.get("MinorVersion"),
        "capabilities": [capability.to_dict() for capability in capabilities],
        "device_kinds": device_kinds,
        "conflict_count": sum(
            capability.status == "conflict" for capability in capabilities
        ),
        "warning": None,
    }


def binding_report(directory: Path) -> dict[str, Any]:
    resolved = directory.expanduser().resolve()
    active = locate_active_bindings(resolved)
    if not resolved.is_dir():
        return {
            "available": False,
            "configured_directory": str(resolved),
            "file_name": None,
            "preset": None,
            "capabilities": [],
            "device_kinds": [],
            "conflict_count": 0,
            "warning": "Elite bindings directory was not found.",
        }
    if active is None:
        return {
            "available": False,
            "configured_directory": str(resolved),
            "file_name": None,
            "preset": None,
            "capabilities": [],
            "device_kinds": [],
            "conflict_count": 0,
            "warning": "No Elite .binds files were found in this directory.",
        }
    return {"configured_directory": str(resolved), **parse_bindings_file(active)}


class EliteBindingsMonitor:
    """Watch the selected bindings file and publish capability changes."""

    def __init__(self, interval_seconds: float = 2.0):
        self.interval_seconds = interval_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._fingerprint: tuple[str, int, int] | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="ion-bindings-monitor", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)

    def _directory(self) -> Path:
        from .api import _load_preferences

        with SessionLocal() as session:
            configured = _load_preferences(session).computer.bindings_directory.strip()
        return (
            Path(configured).expanduser().resolve()
            if configured
            else default_bindings_directory()
        )

    def _run(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            self.scan_once()

    def scan_once(self) -> dict[str, Any] | None:
        directory = self._directory()
        active = locate_active_bindings(directory)
        if active is None:
            fingerprint = (str(directory), 0, 0)
        else:
            try:
                stat = active.stat()
                fingerprint = (str(active), stat.st_mtime_ns, stat.st_size)
            except OSError:
                fingerprint = (str(active), 0, 0)
        if self._fingerprint is None:
            self._fingerprint = fingerprint
            return None
        if fingerprint == self._fingerprint:
            return None
        self._fingerprint = fingerprint
        report = binding_report(directory)
        event_bus.publish(
            "computer.bindings.changed",
            {
                "available": report["available"],
                "file_name": report["file_name"],
                "preset": report["preset"],
                "conflict_count": report["conflict_count"],
            },
        )
        return report


elite_bindings_monitor = EliteBindingsMonitor()
