from __future__ import annotations

import json
import os
import ctypes
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import Commodity, MarketObservation, Station, System


RELEVANT_STATUS_FLAGS = {
    1: "Docked",
    2: "Landed",
    4: "Landing gear down",
    16: "Supercruise",
    64: "Hardpoints deployed",
    512: "Cargo scoop deployed",
    2048: "Fuel scooping",
    131072: "FSD charging",
    524288: "Low fuel",
    1048576: "Overheating",
    4194304: "In danger",
    8388608: "Being interdicted",
    1073741824: "FSD jumping",
}


def _elite_game_process_running() -> bool:
    """Return whether the Windows Elite Dangerous client process is active."""
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

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
    kernel32.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
    kernel32.Process32FirstW.argtypes = [ctypes.c_void_p, ctypes.POINTER(ProcessEntry32)]
    kernel32.Process32FirstW.restype = ctypes.c_int
    kernel32.Process32NextW.argtypes = [ctypes.c_void_p, ctypes.POINTER(ProcessEntry32)]
    kernel32.Process32NextW.restype = ctypes.c_int
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = ctypes.c_int

    snapshot = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
    if snapshot == ctypes.c_void_p(-1).value:
        return False
    try:
        entry = ProcessEntry32()
        entry.dwSize = ctypes.sizeof(entry)
        if not kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
            return False
        while True:
            executable = entry.szExeFile.casefold()
            if executable == "elitedangerous64.exe" or executable.startswith("elitedangerous"):
                return True
            if not kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                return False
    finally:
        kernel32.CloseHandle(snapshot)


def default_journal_directory() -> Path:
    configured = os.getenv("ELITE_LOGISTICS_JOURNAL_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    profile = Path(os.getenv("USERPROFILE", Path.home()))
    return profile / "Saved Games" / "Frontier Developments" / "Elite Dangerous"


def _timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
        return value if isinstance(value, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _display_name(item: dict[str, Any]) -> str:
    localized = item.get("Name_Localised") or item.get("Type_Localised")
    if localized:
        return str(localized)
    raw = str(item.get("Name") or item.get("Type") or "Unknown")
    if raw.startswith("$") and raw.endswith("_name;"):
        raw = raw[1:-6]
    return raw.replace("_", " ").strip().title()


def _canonical_name(item: dict[str, Any]) -> str:
    raw = str(item.get("Name") or item.get("Type") or "").strip().casefold()
    if raw.startswith("$"):
        raw = raw[1:]
    if raw.endswith("_name;"):
        raw = raw[:-6]
    return " ".join(raw.replace("_", " ").split())


@dataclass
class ParsedEliteState:
    directory: str
    available: bool = False
    source_kind: str = "unavailable"
    game_running: bool = False
    latest_event_at: datetime | None = None
    journal_file: str | None = None
    commander: str | None = None
    credits: int | None = None
    system_id64: int | None = None
    system_name: str | None = None
    system_position: list[float] | None = None
    station_market_id: int | None = None
    station_name: str | None = None
    station_type: str | None = None
    station_distance_ls: float | None = None
    largest_pad: str | None = None
    docked: bool = False
    phase: str = "unknown"
    ship_model: str | None = None
    ship_name: str | None = None
    ship_ident: str | None = None
    ship_id: int | None = None
    cargo_capacity: int | None = None
    cargo_count: int = 0
    max_jump_range: float | None = None
    rebuy: int | None = None
    cargo: list[dict[str, Any]] = field(default_factory=list)
    target_system_id64: int | None = None
    target_system_name: str | None = None
    target_station_name: str | None = None
    landing_pad: int | None = None
    nav_route: list[dict[str, Any]] = field(default_factory=list)
    status_flags: list[str] = field(default_factory=list)
    transactions: list[dict[str, Any]] = field(default_factory=list)
    files: dict[str, bool] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        result = self.__dict__.copy()
        if self.latest_event_at:
            result["latest_event_at"] = self.latest_event_at.isoformat()
        return result


class EliteDataReader:
    def __init__(self, directory: Path):
        self.directory = directory.expanduser().resolve()

    def read(self) -> ParsedEliteState:
        state = ParsedEliteState(directory=str(self.directory))
        state.files = {
            name: (self.directory / name).exists()
            for name in (
                "Status.json",
                "Cargo.json",
                "Market.json",
                "NavRoute.json",
                "Shipyard.json",
                "Outfitting.json",
            )
        }
        if not self.directory.is_dir():
            state.warnings.append("Elite journal directory was not found.")
            return state

        journals = sorted(self.directory.glob("Journal.*.log"))
        if not journals:
            state.warnings.append("No Elite journal logs were found in this directory.")
            return state

        journal = journals[-1]
        state.available = True
        state.journal_file = journal.name
        state.source_kind = "reference" if self.directory.name.casefold() == "referencedata" else "journal"
        self._read_journal(journal, state)
        self._read_cargo(state)
        self._read_nav_route(state)
        self._read_status(state)

        if state.latest_event_at:
            age = (datetime.now(UTC) - state.latest_event_at.astimezone(UTC)).total_seconds()
            try:
                file_age = datetime.now(UTC).timestamp() - journal.stat().st_mtime
            except OSError:
                file_age = float("inf")
            state.game_running = state.source_kind != "reference" and (
                _elite_game_process_running() or 0 <= age <= 30 or 0 <= file_age <= 30
            )
            if not state.game_running:
                state.warnings.append(
                    "Elite is not currently detected; saved journal data remains linked and available."
                )
        return state

    def _read_journal(self, path: Path, state: ParsedEliteState) -> None:
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(event, dict):
                        self._apply_event(event, state)
        except OSError as exc:
            state.available = False
            state.warnings.append(f"Could not read the current journal: {exc}")

    def _apply_event(self, event: dict[str, Any], state: ParsedEliteState) -> None:
        kind = event.get("event")
        event_at = _timestamp(event.get("timestamp"))
        if event_at and (state.latest_event_at is None or event_at > state.latest_event_at):
            state.latest_event_at = event_at

        if kind in ("Commander", "LoadGame"):
            state.commander = event.get("Name") or event.get("Commander") or state.commander
        if kind == "LoadGame":
            state.credits = int(event.get("Credits", state.credits or 0))
            state.ship_model = event.get("Ship") or state.ship_model
            state.ship_name = event.get("ShipName") or state.ship_name
            state.ship_ident = event.get("ShipIdent") or state.ship_ident
            state.ship_id = event.get("ShipID") or state.ship_id
        elif kind == "Loadout":
            state.ship_model = event.get("Ship") or state.ship_model
            state.ship_name = event.get("ShipName") or state.ship_name
            state.ship_ident = event.get("ShipIdent") or state.ship_ident
            state.ship_id = event.get("ShipID") or state.ship_id
            state.cargo_capacity = int(event.get("CargoCapacity", state.cargo_capacity or 0))
            state.max_jump_range = float(event.get("MaxJumpRange", state.max_jump_range or 0))
            state.rebuy = int(event.get("Rebuy", state.rebuy or 0))
        elif kind == "Location":
            self._set_system(event, state)
            state.docked = bool(event.get("Docked", False))
            if state.docked:
                self._set_station(event, state)
                state.phase = "docked"
            else:
                state.phase = "normal_space"
        elif kind == "Docked":
            self._set_system(event, state)
            self._set_station(event, state)
            state.docked = True
            state.phase = "docked"
        elif kind == "Undocked":
            state.docked = False
            state.station_market_id = None
            state.station_name = None
            state.phase = "normal_space"
        elif kind == "StartJump":
            state.phase = "hyperspace" if event.get("JumpType") == "Hyperspace" else "supercruise"
            if event.get("SystemAddress"):
                state.target_system_id64 = int(event["SystemAddress"])
            state.target_system_name = event.get("StarSystem") or state.target_system_name
        elif kind == "FSDJump":
            self._set_system(event, state)
            state.docked = False
            state.station_market_id = None
            state.station_name = None
            state.phase = "supercruise"
        elif kind == "FSDTarget":
            state.target_system_id64 = int(event["SystemAddress"]) if event.get("SystemAddress") else None
            state.target_system_name = event.get("Name")
        elif kind == "SupercruiseEntry":
            state.phase = "supercruise"
        elif kind in ("SupercruiseExit", "USSDrop"):
            state.phase = "normal_space"
        elif kind == "ApproachBody":
            state.phase = "planetary_approach"
        elif kind == "Disembark":
            state.phase = "on_foot"
        elif kind == "Embark":
            state.phase = "docked" if state.docked else "normal_space"
        elif kind == "DockingGranted":
            state.target_station_name = event.get("StationName")
            state.landing_pad = int(event["LandingPad"]) if event.get("LandingPad") is not None else None
        elif kind in ("MarketBuy", "MarketSell"):
            state.transactions.append(
                {
                    "kind": "buy" if kind == "MarketBuy" else "sell",
                    "market_id": int(event.get("MarketID", 0)),
                    "commodity": _display_name(event),
                    "canonical_commodity": _canonical_name(event),
                    "quantity": int(event.get("Count", 0)),
                    "price": int(event.get("BuyPrice") or event.get("SellPrice") or 0),
                    "timestamp": event_at.isoformat() if event_at else None,
                }
            )
            state.transactions = state.transactions[-100:]

    @staticmethod
    def _set_system(event: dict[str, Any], state: ParsedEliteState) -> None:
        if event.get("SystemAddress"):
            state.system_id64 = int(event["SystemAddress"])
        state.system_name = event.get("StarSystem") or state.system_name
        if event.get("StarPos") and len(event["StarPos"]) == 3:
            state.system_position = [float(value) for value in event["StarPos"]]

    @staticmethod
    def _set_station(event: dict[str, Any], state: ParsedEliteState) -> None:
        if event.get("MarketID"):
            state.station_market_id = int(event["MarketID"])
        state.station_name = event.get("StationName") or state.station_name
        state.station_type = event.get("StationType") or state.station_type
        if event.get("DistFromStarLS") is not None:
            state.station_distance_ls = float(event["DistFromStarLS"])
        pads = event.get("LandingPads") or {}
        if pads.get("Large"):
            state.largest_pad = "L"
        elif pads.get("Medium"):
            state.largest_pad = "M"
        elif pads.get("Small"):
            state.largest_pad = "S"

    def _read_cargo(self, state: ParsedEliteState) -> None:
        payload = _read_json(self.directory / "Cargo.json")
        if not payload:
            return
        state.cargo_count = int(payload.get("Count", 0))
        inventory = []
        for item in payload.get("Inventory", []):
            if not isinstance(item, dict):
                continue
            inventory.append(
                {
                    "commodity": _display_name(item),
                    "canonical_commodity": _canonical_name(item),
                    "count": int(item.get("Count", 0)),
                    "stolen": int(item.get("Stolen", 0)),
                    "mission_id": item.get("MissionID"),
                }
            )
        state.cargo = inventory

    def _read_nav_route(self, state: ParsedEliteState) -> None:
        payload = _read_json(self.directory / "NavRoute.json")
        if not payload:
            return
        state.nav_route = [
            {
                "system_id64": int(item.get("SystemAddress", 0)),
                "system_name": item.get("StarSystem", "Unknown"),
                "star_class": item.get("StarClass"),
                "position": item.get("StarPos"),
            }
            for item in payload.get("Route", [])
            if isinstance(item, dict)
        ]

    def _read_status(self, state: ParsedEliteState) -> None:
        payload = _read_json(self.directory / "Status.json")
        if not payload:
            return
        flags = int(payload.get("Flags", 0))
        state.status_flags = [label for bit, label in RELEVANT_STATUS_FLAGS.items() if flags & bit]
        if flags & 1:
            state.docked = True
            state.phase = "docked"
        elif flags & 1073741824:
            state.phase = "hyperspace"
        elif flags & 16:
            state.phase = "supercruise"
        elif flags & 2:
            state.phase = "landed"


def sync_current_market(session: Session, directory: Path, state: ParsedEliteState) -> int:
    payload = _read_json(directory / "Market.json")
    if (
        not payload
        or not state.system_id64
        or not state.system_name
        or not payload.get("MarketID")
        or not state.system_position
    ):
        return 0

    observed_at = _timestamp(payload.get("timestamp")) or datetime.now(UTC)
    system = session.get(System, state.system_id64)
    if system is None:
        system = System(
            id64=state.system_id64,
            name=state.system_name,
            normalized_name=" ".join(state.system_name.casefold().split()),
            x=state.system_position[0],
            y=state.system_position[1],
            z=state.system_position[2],
            permit_required=False,
            updated_at=observed_at,
        )
        session.add(system)

    market_id = int(payload["MarketID"])
    station = session.get(Station, market_id)
    station_type = str(payload.get("StationType") or state.station_type or "Unknown")
    if station is None:
        station = Station(
            market_id=market_id,
            system_id64=state.system_id64,
            name=str(payload.get("StationName") or state.station_name or "Unknown"),
            normalized_name=" ".join(str(payload.get("StationName") or state.station_name or "Unknown").casefold().split()),
            station_type=station_type,
            distance_to_arrival_ls=state.station_distance_ls or 0,
            largest_pad=state.largest_pad or "L",
            planetary="surface" in station_type.casefold(),
            fleet_carrier=station_type.casefold() == "fleetcarrier",
            odyssey=False,
            restricted=False,
            updated_at=observed_at,
        )
        session.add(station)

    imported = 0
    for item in payload.get("Items", []):
        if not isinstance(item, dict) or item.get("id") is None:
            continue
        commodity_id = int(item["id"])
        commodity = session.get(Commodity, commodity_id)
        canonical_name = _canonical_name(item) or f"commodity-{commodity_id}"
        if commodity is None:
            commodity = session.scalar(
                select(Commodity).where(Commodity.canonical_name == canonical_name)
            )
        if commodity is None:
            commodity = Commodity(
                id=commodity_id,
                canonical_name=canonical_name,
                display_name=_display_name(item),
                category=str(item.get("Category_Localised") or item.get("Category") or "Unknown"),
            )
            session.add(commodity)
            session.flush()
        commodity_id = commodity.id
        observation = session.scalar(
            select(MarketObservation).where(
                MarketObservation.market_id == market_id,
                MarketObservation.commodity_id == commodity_id,
            )
        )
        if observation is None:
            observation = MarketObservation(market_id=market_id, commodity_id=commodity_id)
            session.add(observation)
        existing_at = observation.observed_at
        if existing_at is not None and existing_at.tzinfo is None:
            existing_at = existing_at.replace(tzinfo=UTC)
        if existing_at is None or observed_at > existing_at:
            observation.buy_price = int(item.get("BuyPrice", 0))
            observation.sell_price = int(item.get("SellPrice", 0))
            observation.supply = int(item.get("Stock", 0))
            observation.demand = int(item.get("Demand", 0))
            observation.observed_at = observed_at
            observation.provider = "EliteJournal"
            imported += 1
    session.commit()
    return imported
