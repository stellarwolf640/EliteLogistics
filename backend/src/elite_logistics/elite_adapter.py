from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .schemas import EliteCargoItem, EliteGameState


SHIP_PAD_SIZES: dict[str, str] = {
    "adder": "S", "cobra_mk_iii": "S", "cobramkiv": "S", "cobramkv": "S",
    "diamondback": "S", "diamondbackxl": "S", "dolphin": "S", "eagle": "S",
    "empire_courier": "S", "empire_eagle": "S", "hauler": "S", "sidewinder": "S",
    "viper": "S", "viper_mkiv": "S", "vulture": "S",
    "alliance_challenger": "M", "alliance_chieftain": "M", "alliance_crusader": "M",
    "asp": "M", "asp_scout": "M", "federation_dropship": "M",
    "federation_dropship_mkii": "M", "federation_gunship": "M", "ferdelance": "M",
    "krait_light": "M", "krait_mkii": "M", "mandalay": "M", "mamba": "M",
    "python": "M", "python_nx": "M", "type6": "M", "typex": "M", "typex_2": "M",
    "anaconda": "L", "belugaliner": "L", "cutter": "L", "empire_trader": "L",
    "federal_corvette": "L", "orca": "L", "panthermkii": "L", "type7": "L",
    "type9": "L", "type9_military": "L",
}

DEBIT_FIELDS = {
    "BuyAmmo": "Cost",
    "BuyDrones": "TotalCost",
    "BuyExplorationData": "Cost",
    "BuyTradeData": "Cost",
    "MarketBuy": "TotalCost",
    "ModuleBuy": "BuyPrice",
    "PayBounties": "Amount",
    "PayFines": "Amount",
    "RefuelAll": "Cost",
    "RefuelPartial": "Cost",
    "Repair": "Cost",
    "RepairAll": "Cost",
    "RestockVehicle": "Cost",
}

CREDIT_FIELDS = {
    "MarketSell": "TotalSale",
    "MissionCompleted": "Reward",
    "MultiSellExplorationData": "TotalEarnings",
    "RedeemVoucher": "Amount",
    "SearchAndRescue": "Reward",
    "SellDrones": "TotalSale",
    "SellExplorationData": "TotalEarnings",
    "SellOrganicData": "TotalEarnings",
}

MONEY_FIELD_TOKENS = ("amount", "balance", "cost", "credit", "earnings", "price", "reward", "sale")


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError:
        return None


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        return value if isinstance(value, dict) else None
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None


def _journal_records(path: Path) -> tuple[list[dict[str, Any]], int]:
    records: list[dict[str, Any]] = []
    malformed = 0
    try:
        with path.open("r", encoding="utf-8-sig", errors="replace") as journal:
            for line in journal:
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    malformed += 1
                    continue
                if isinstance(record, dict):
                    records.append(record)
    except OSError:
        return [], 0
    return records, malformed


def _cargo_items(snapshot: dict[str, Any] | None) -> list[EliteCargoItem]:
    if not snapshot:
        return []
    results: list[EliteCargoItem] = []
    for item in snapshot.get("Inventory", []):
        if not isinstance(item, dict):
            continue
        name = item.get("Name_Localised") or item.get("Name")
        if name:
            results.append(
                EliteCargoItem(
                    name=str(name),
                    count=max(0, int(item.get("Count", 0) or 0)),
                    stolen=max(0, int(item.get("Stolen", 0) or 0)),
                )
            )
    return results


def read_elite_state(journal_dir: Path) -> EliteGameState:
    journal_dir = journal_dir.resolve()
    if not journal_dir.is_dir():
        return EliteGameState(
            available=False,
            journal_directory=str(journal_dir),
            warnings=["Elite Dangerous journal directory was not found."],
        )

    journals = sorted(
        journal_dir.glob("Journal.*.log"),
        key=lambda path: (path.stat().st_mtime, path.name),
        reverse=True,
    )
    if not journals:
        return EliteGameState(
            available=False,
            journal_directory=str(journal_dir),
            warnings=["No Elite Dangerous journal logs were found."],
        )

    journal = journals[0]
    records, malformed = _journal_records(journal)
    state = EliteGameState(
        available=True,
        journal_directory=str(journal_dir),
        journal_file=journal.name,
        source_files=[journal.name],
    )
    location_timestamp: datetime | None = None
    credit_baseline_seen = False
    unhandled_credit_events: set[str] = set()
    game_shutdown = False

    for record in records:
        event = str(record.get("event", ""))
        timestamp = _parse_timestamp(record.get("timestamp"))
        if timestamp and (state.last_updated is None or timestamp > state.last_updated):
            state.last_updated = timestamp
        if event and event != "Shutdown":
            game_shutdown = False

        if event in {"Commander", "LoadGame"}:
            state.commander = record.get("Name") or record.get("Commander") or state.commander
        if event == "LoadGame":
            state.ship_type = record.get("Ship_Localised") or record.get("Ship") or state.ship_type
            state.ship_internal_name = record.get("Ship") or state.ship_internal_name
            state.ship_name = record.get("ShipName") or state.ship_name
            state.ship_ident = record.get("ShipIdent") or state.ship_ident
            if record.get("Credits") is not None:
                state.credits = max(0, int(record["Credits"]))
                credit_baseline_seen = True
        elif event == "Loadout":
            state.ship_type = record.get("Ship_Localised") or record.get("Ship") or state.ship_type
            state.ship_internal_name = record.get("Ship") or state.ship_internal_name
            state.ship_name = record.get("ShipName") or state.ship_name
            state.ship_ident = record.get("ShipIdent") or state.ship_ident
            if record.get("CargoCapacity") is not None:
                state.cargo_capacity = max(0, int(record["CargoCapacity"]))
            if record.get("MaxJumpRange") is not None:
                state.max_jump_range = max(0, float(record["MaxJumpRange"]))
            if record.get("Rebuy") is not None:
                state.rebuy = max(0, int(record["Rebuy"]))
        elif event in {"Location", "FSDJump", "CarrierJump"}:
            state.system_name = record.get("StarSystem") or state.system_name
            if record.get("SystemAddress") is not None:
                state.system_id64 = int(record["SystemAddress"])
            if event != "Location" or not record.get("Docked"):
                state.station_name = None
                state.station_market_id = None
            if event == "Location" and record.get("Docked"):
                state.station_name = record.get("StationName")
                if record.get("MarketID") is not None:
                    state.station_market_id = int(record["MarketID"])
            location_timestamp = timestamp or location_timestamp
        elif event == "Docked":
            state.system_name = record.get("StarSystem") or state.system_name
            if record.get("SystemAddress") is not None:
                state.system_id64 = int(record["SystemAddress"])
            state.station_name = record.get("StationName")
            if record.get("MarketID") is not None:
                state.station_market_id = int(record["MarketID"])
            location_timestamp = timestamp or location_timestamp
        elif event == "Undocked":
            state.station_name = None
            state.station_market_id = None
            location_timestamp = timestamp or location_timestamp
        elif event == "Cargo" and record.get("Count") is not None:
            state.cargo_count = max(0, int(record["Count"]))
        elif event == "Shutdown":
            game_shutdown = True

        if credit_baseline_seen and state.credits is not None:
            if event in DEBIT_FIELDS and record.get(DEBIT_FIELDS[event]) is not None:
                state.credits = max(0, state.credits - int(record[DEBIT_FIELDS[event]]))
            elif event in CREDIT_FIELDS and record.get(CREDIT_FIELDS[event]) is not None:
                state.credits += int(record[CREDIT_FIELDS[event]])
            elif event != "LoadGame":
                money_fields = [
                    key for key in record
                    if any(token in key.casefold() for token in MONEY_FIELD_TOKENS)
                ]
                if money_fields:
                    unhandled_credit_events.add(event)

    state.pad_size = SHIP_PAD_SIZES.get((state.ship_internal_name or "").casefold())

    cargo_path = journal_dir / "Cargo.json"
    cargo = _read_json(cargo_path)
    if cargo:
        state.source_files.append(cargo_path.name)
        if cargo.get("Count") is not None:
            state.cargo_count = max(0, int(cargo["Count"]))
        state.cargo = _cargo_items(cargo)
        cargo_timestamp = _parse_timestamp(cargo.get("timestamp"))
        if cargo_timestamp and (state.last_updated is None or cargo_timestamp > state.last_updated):
            state.last_updated = cargo_timestamp

    market_path = journal_dir / "Market.json"
    market = _read_json(market_path)
    if market:
        state.source_files.append(market_path.name)
        market_timestamp = _parse_timestamp(market.get("timestamp"))
        same_system = not state.system_name or market.get("StarSystem") == state.system_name
        current_enough = location_timestamp is None or market_timestamp is None or market_timestamp >= location_timestamp
        if same_system and current_enough:
            state.system_name = market.get("StarSystem") or state.system_name
            state.station_name = market.get("StationName") or state.station_name
            if market.get("MarketID") is not None:
                state.station_market_id = int(market["MarketID"])

    status_path = journal_dir / "Status.json"
    status = _read_json(status_path)
    if status:
        state.source_files.append(status_path.name)
        status_timestamp = _parse_timestamp(status.get("timestamp"))
        if status_timestamp and (state.last_updated is None or status_timestamp > state.last_updated):
            state.last_updated = status_timestamp

    state.game_running = not game_shutdown and bool(records)
    if state.last_updated:
        age_seconds = (datetime.now(UTC) - state.last_updated.astimezone(UTC)).total_seconds()
        if age_seconds > 300:
            state.game_running = False
    if malformed:
        state.warnings.append(f"Skipped {malformed} incomplete journal record(s).")
    if unhandled_credit_events:
        state.warnings.append(
            "Detected credit-affecting events that are not yet reconciled: "
            + ", ".join(sorted(unhandled_credit_events))
            + ". Verify the displayed balance before applying it."
        )
    if state.credits is not None:
        state.warnings.append(
            "Balance is reconstructed from the session journal; manual values remain authoritative."
        )
    if state.max_jump_range is not None:
        state.warnings.append(
            "The journal jump range is a live game estimate; confirm it matches your intended laden build."
        )
    return state
