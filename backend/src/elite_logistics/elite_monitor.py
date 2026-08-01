from __future__ import annotations

import threading
from typing import Any

from .api import _elite_settings
from .database import SessionLocal
from .elite_data import EliteDataReader, sync_current_market
from .events import event_bus
from .schemas import ComputerPreferences


class EliteMonitor:
    """Background journal monitor that translates file changes into app events."""

    def __init__(self, interval_seconds: float = 1.0):
        self.interval_seconds = interval_seconds
        self._stop = threading.Event()
        self._paused = threading.Event()
        self._thread: threading.Thread | None = None
        self._previous: dict[str, Any] | None = None

    @property
    def paused(self) -> bool:
        return self._paused.is_set()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="ion-elite-monitor", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)

    def pause(self) -> None:
        self._paused.set()
        event_bus.publish("elite.disconnected", {"paused": True})

    def resume(self) -> None:
        self._paused.clear()
        event_bus.publish("elite.connected", {"paused": False})

    def _run(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            try:
                from .elite_bindings import elite_bindings_monitor

                elite_bindings_monitor.scan_once()
            except Exception as exc:
                event_bus.publish(
                    "computer.bindings.changed", {"available": False, "error": str(exc)}
                )
            if self.paused:
                continue
            try:
                self._tick()
            except Exception as exc:
                event_bus.publish("elite.disconnected", {"error": str(exc)})

    def _tick(self) -> None:
        with SessionLocal() as session:
            values, directory = _elite_settings(session)
            if not values["elite_enabled"]:
                self._previous = None
                return
            state = EliteDataReader(directory).read()
            current = state.to_dict()
            previous = self._previous
            computer_preferences = ComputerPreferences.model_validate(
                values.get("computer") or {}
            )
            if previous is None:
                event_bus.publish("elite.connected", current)
                event_bus.publish("elite.state.changed", current)
            elif current != previous:
                event_bus.publish("elite.state.changed", current)
                if (
                    current.get("system_id64"),
                    current.get("station_market_id"),
                    current.get("docked"),
                ) != (
                    previous.get("system_id64"),
                    previous.get("station_market_id"),
                    previous.get("docked"),
                ):
                    event_bus.publish("location.changed", current)
                if current.get("cargo") != previous.get("cargo"):
                    event_bus.publish("cargo.changed", current.get("cargo", []))
                if (
                    current.get("nav_route"),
                    current.get("target_system_id64"),
                    current.get("landing_pad"),
                ) != (
                    previous.get("nav_route"),
                    previous.get("target_system_id64"),
                    previous.get("landing_pad"),
                ):
                    event_bus.publish(
                        "navigation.changed",
                        {
                            "nav_route": current.get("nav_route", []),
                            "target_system_id64": current.get("target_system_id64"),
                            "landing_pad": current.get("landing_pad"),
                        },
                    )
            imported = sync_current_market(session, directory, state) if state.available else 0
            if imported:
                event_bus.publish("market.updated", {"records": imported})
            if (
                computer_preferences.enabled
                and computer_preferences.proactivity != "silent"
            ):
                from .computer_alerts import computer_alert_engine

                computer_alert_engine.process(
                    session,
                    current,
                    previous,
                    computer_preferences,
                )
            self._previous = current


elite_monitor = EliteMonitor()
