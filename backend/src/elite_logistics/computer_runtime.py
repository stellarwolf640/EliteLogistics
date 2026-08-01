"""Policy-gated execution runtime for ION Computer read and interface tools."""

from __future__ import annotations

import hashlib
import json
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from queue import Empty, Queue
from typing import Any, Callable
from uuid import uuid4

from sqlalchemy import select

from .computer import (
    CONTROLS_BY_ID,
    AuthorizationResult,
    InvocationSource,
    authorize_control_action,
    authorize_tool,
)
from .database import (
    ActiveOperation,
    Commodity,
    ComputerConfirmation,
    ComputerInvocation,
    MarketObservation,
    SessionLocal,
    Station,
    System,
)
from .engine import (
    confidence,
    distance,
    find_immersive_trade_routes,
    find_round_trips,
    find_trades,
    jump_count,
    plan_transit,
    station_allowed,
)
from .elite_bindings import binding_report, default_bindings_directory
from .elite_data import EliteDataReader, default_journal_directory
from .events import event_bus
from .input_bridge import BridgeContext, input_bridge, keyboard_binding_supported
from .schemas import (
    ActiveOperationInput,
    ComputerPreferences,
    PlayerState,
    SearchFilters,
    TradeSearchRequest,
    TransitRequest,
)


ToolHandler = Callable[[dict[str, Any]], dict[str, Any]]
_execution_slots = threading.BoundedSemaphore(4)

# Once one of these handlers begins, reporting a caller timeout would be
# misleading: the side effect may already have happened and cannot safely be
# canceled. Their timeout therefore applies only while waiting for an execution
# slot. After they start, ION waits for the definitive result and never invites
# a retry against an action that may still be running.
NON_CANCELLABLE_SIDE_EFFECT_TOOLS = frozenset(
    {
        "activate_operation",
        "set_operation_progress",
        "pause_operation",
        "resume_operation",
        "cancel_operation",
        "replace_operation",
        "open_ion_view",
        "open_route_console",
        "populate_planner",
        "change_search_filters",
        "show_information_card",
        "show_diagnostics",
        "set_ship_system",
        "open_game_interface",
        "set_power_distribution",
    }
)

ION_ROUTES = {
    "home": "/",
    "trade_operations": "/operations",
    "best_trades": "/trade",
    "round_trips": "/round-trips",
    "trade_routes": "/trade-routes",
    "navigation": "/navigation",
    "profitable_transit": "/transit",
    "fleet_management": "/fleet",
    "ship_profiles": "/ships",
    "ship_optimizations": "/ship-optimizations",
    "data_network": "/data",
    "settings": "/settings",
    "computer": "/computer",
}
PLANNER_FIELDS = {
    "originSystemId64",
    "originStationMarketId",
    "originLocationLabel",
    "destinationSystemId64",
    "destinationStationMarketId",
    "destinationLocationLabel",
    "cargoCapacity",
    "ladenJumpRange",
    "padSize",
    "credits",
    "rebuyReserve",
    "cashReserve",
}
FILTER_FIELDS = {
    "maxMarketAgeHours",
    "maxStationDistanceLs",
    "maxSystemDistanceLy",
    "includeFleetCarriers",
    "includePlanetary",
    "includeOdyssey",
    "hideLowConfidence",
}


def _now() -> datetime:
    return datetime.now(UTC)


def _json_hash(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _preference_snapshot() -> tuple[ComputerPreferences, Path, Path]:
    from .api import _load_preferences

    with SessionLocal() as session:
        preferences = _load_preferences(session)
    journal = (
        Path(preferences.elite_journal_directory).expanduser().resolve()
        if preferences.elite_journal_directory.strip()
        else default_journal_directory()
    )
    bindings = (
        Path(preferences.computer.bindings_directory).expanduser().resolve()
        if preferences.computer.bindings_directory.strip()
        else default_bindings_directory()
    )
    return preferences.computer, journal, bindings


def _elite_state() -> dict[str, Any]:
    _, journal, _ = _preference_snapshot()
    return EliteDataReader(journal).read().to_dict()


def _active_operation() -> dict[str, Any] | None:
    with SessionLocal() as session:
        operation = session.get(ActiveOperation, 1)
        if operation is None:
            return None
        return {
            "operation_type": operation.operation_type,
            "title": operation.title,
            "route_payload": operation.route_payload,
            "activated_at": operation.activated_at.isoformat(),
            "manual_progress": operation.manual_progress,
            "status": operation.status,
            "updated_at": operation.updated_at.isoformat(),
        }


def _operational_snapshot(_arguments: dict[str, Any]) -> dict[str, Any]:
    state = _elite_state()
    operation = _active_operation()
    return {
        "commander": state.get("commander"),
        "location": {
            "system": state.get("system_name"),
            "station": state.get("station_name"),
            "phase": state.get("phase"),
        },
        "ship": {
            "model": state.get("ship_model"),
            "name": state.get("ship_name"),
            "cargo_count": state.get("cargo_count"),
            "cargo_capacity": state.get("cargo_capacity"),
            "jump_range": state.get("max_jump_range"),
        },
        "navigation": {
            "target_system": state.get("target_system_name"),
            "target_station": state.get("target_station_name"),
            "remaining_route_systems": len(state.get("nav_route") or []),
        },
        "active_operation": (
            {
                "title": operation["title"],
                "progress": operation["manual_progress"],
                "status": operation["status"],
            }
            if operation
            else None
        ),
        "warnings": state.get("warnings") or [],
        "source_available": bool(state.get("available")),
    }


def _ship_state(_arguments: dict[str, Any]) -> dict[str, Any]:
    state = _elite_state()
    keys = (
        "ship_model",
        "ship_name",
        "ship_ident",
        "cargo_capacity",
        "cargo_count",
        "max_jump_range",
        "rebuy",
        "status_flags",
        "phase",
        "game_running",
    )
    return {key: state.get(key) for key in keys}


def _navigation_state(_arguments: dict[str, Any]) -> dict[str, Any]:
    state = _elite_state()
    keys = (
        "system_id64",
        "system_name",
        "station_market_id",
        "station_name",
        "target_system_id64",
        "target_system_name",
        "target_station_name",
        "landing_pad",
        "nav_route",
        "phase",
    )
    return {key: state.get(key) for key in keys}


def _cargo_manifest(_arguments: dict[str, Any]) -> dict[str, Any]:
    state = _elite_state()
    operation = _active_operation()
    return {
        "cargo": state.get("cargo") or [],
        "count": state.get("cargo_count") or 0,
        "capacity": state.get("cargo_capacity"),
        "active_operation": operation,
    }


def _control_capabilities(_arguments: dict[str, Any]) -> dict[str, Any]:
    preferences, _, directory = _preference_snapshot()
    report = binding_report(directory)
    bridge_available = input_bridge.status()["available"]
    for capability in report["capabilities"]:
        action = CONTROLS_BY_ID[capability["action_id"]]
        has_keyboard = any(
            slot and slot.get("device_kind") == "keyboard"
            for slot in (capability.get("secondary"), capability.get("primary"))
        )
        keyboard_ready = any(
            slot
            and slot.get("device_kind") == "keyboard"
            and keyboard_binding_supported(slot)
            for slot in (capability.get("secondary"), capability.get("primary"))
        )
        capability["permission"] = action.permission.value
        capability["permission_enabled"] = (
            preferences.class_b_enabled
            and action.action_id in preferences.enabled_game_actions
        )
        capability["input_bridge_available"] = bridge_available and keyboard_ready
        capability["ion_status"] = (
            "conflict"
            if capability["status"] == "conflict"
            else "ready"
            if keyboard_ready
            else "unsupported_keyboard_binding"
            if has_keyboard
            else "requires_keyboard_binding"
            if capability["status"] != "unbound"
            else "unbound"
        )
    report["class_b_enabled"] = preferences.class_b_enabled
    report["input_bridge_available"] = bridge_available
    return report


def _inspect_current_system(_arguments: dict[str, Any]) -> dict[str, Any]:
    state = _elite_state()
    system_id64 = state.get("system_id64")
    if not system_id64:
        return {
            "available": False,
            "warning": "The current system is unavailable from the game link.",
        }
    with SessionLocal() as session:
        system = session.get(System, int(system_id64))
        if system is None:
            return {
                "available": False,
                "system_id64": system_id64,
                "name": state.get("system_name"),
                "warning": "ION has no local system record for the current location.",
            }
        stations = session.scalars(
            select(Station).where(Station.system_id64 == system.id64)
        ).all()
        market_count = session.scalar(
            select(MarketObservation)
            .join(Station)
            .where(Station.system_id64 == system.id64)
            .limit(1)
        )
        return {
            "available": True,
            "system_id64": system.id64,
            "name": system.name,
            "coordinates": [system.x, system.y, system.z],
            "permit_required": system.permit_required,
            "station_count": len(stations),
            "stations": [
                {
                    "name": station.name,
                    "market_id": station.market_id,
                    "type": station.station_type,
                    "distance_ls": station.distance_to_arrival_ls,
                    "largest_pad": station.largest_pad,
                    "planetary": station.planetary,
                }
                for station in sorted(
                    stations, key=lambda value: value.distance_to_arrival_ls
                )[:20]
            ],
            "market_data_available": market_count is not None,
        }


def _get_active_operation(_arguments: dict[str, Any]) -> dict[str, Any]:
    return {"operation": _active_operation()}


def _next_instruction(_arguments: dict[str, Any]) -> dict[str, Any]:
    operation = _active_operation()
    if operation is None:
        return {"available": False, "instruction": "No operation is active."}
    payload = operation.get("route_payload") or {}
    legs = payload.get("legs") or []
    index = min(operation["manual_progress"], max(0, len(legs) - 1))
    if not legs:
        return {
            "available": True,
            "instruction": operation["title"],
            "step": operation["manual_progress"],
        }
    leg = legs[index]
    commodity = leg.get("commodity") or "assigned cargo"
    quantity = leg.get("quantity")
    destination = ", ".join(
        value
        for value in (
            leg.get("destination_station"),
            leg.get("destination_system"),
        )
        if value
    )
    instruction = (
        f"Deliver {quantity} t of {commodity} to {destination}."
        if quantity
        else f"Deliver {commodity} to {destination}."
    )
    return {
        "available": True,
        "instruction": instruction,
        "step": index,
        "leg": leg,
    }


PLANNER_ASSUMPTIONS = [
    "Jump counts use 85% of laden range as a conservative routing factor.",
    "Travel times are estimates; exact star-by-star routing remains in-game.",
    "Market prices are observations and may change before arrival.",
]


def _trade_request(arguments: dict[str, Any]) -> TradeSearchRequest:
    payload = arguments.get("request", arguments)
    if not isinstance(payload, dict):
        raise ValueError("A structured trade-search request is required.")
    return TradeSearchRequest.model_validate(payload)


def _transit_request(arguments: dict[str, Any]) -> TransitRequest:
    payload = arguments.get("request", arguments)
    if not isinstance(payload, dict):
        raise ValueError("A structured transit request is required.")
    return TransitRequest.model_validate(payload)


def _search_one_way_trades(arguments: dict[str, Any]) -> dict[str, Any]:
    request = _trade_request(arguments)
    with SessionLocal() as session:
        routes = find_trades(session, request)
    return {
        "kind": "one_way_trade",
        "routes": [route.model_dump(mode="json") for route in routes],
        "available_credits": request.state.available_credits,
        "assumptions": PLANNER_ASSUMPTIONS,
    }


def _search_round_trips(arguments: dict[str, Any]) -> dict[str, Any]:
    request = _trade_request(arguments)
    with SessionLocal() as session:
        routes = find_round_trips(session, request)
    return {
        "kind": "round_trip",
        "routes": [route.model_dump(mode="json") for route in routes],
        "available_credits": request.state.available_credits,
        "assumptions": PLANNER_ASSUMPTIONS,
    }


def _plan_trade_route(arguments: dict[str, Any]) -> dict[str, Any]:
    request = _trade_request(arguments)
    with SessionLocal() as session:
        routes = find_immersive_trade_routes(session, request)
    return {
        "kind": "trade_route",
        "routes": [route.model_dump(mode="json") for route in routes],
        "assumptions": PLANNER_ASSUMPTIONS
        + [
            "Trade Routes favor continuity, route length, commodity variety, "
            "and confidence over maximum profit."
        ],
    }


def _plan_profitable_transit(arguments: dict[str, Any]) -> dict[str, Any]:
    request = _transit_request(arguments)
    with SessionLocal() as session:
        result = plan_transit(session, request)
    return {
        "kind": "profitable_transit",
        **result.model_dump(mode="json"),
        "assumptions": PLANNER_ASSUMPTIONS,
    }


def _normalize_commodity_name(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


def _commodity_candidates(
    session: Any,
    name: str,
) -> list[Commodity]:
    normalized = _normalize_commodity_name(name)
    commodities = session.scalars(select(Commodity)).all()
    exact = [
        item
        for item in commodities
        if normalized
        in {
            _normalize_commodity_name(item.canonical_name),
            _normalize_commodity_name(item.display_name),
        }
    ]
    if exact:
        return exact
    return [
        item
        for item in commodities
        if normalized
        and (
            normalized in _normalize_commodity_name(item.canonical_name)
            or normalized in _normalize_commodity_name(item.display_name)
        )
    ]


def _market_destination_rows(
    session: Any,
    *,
    state: PlayerState,
    filters: SearchFilters,
    commodity_ids: list[int],
    quantity: int,
    selling: bool,
    radius: float,
) -> list[dict[str, Any]]:
    origin = session.get(System, state.origin_system_id64)
    if origin is None:
        raise ValueError("The origin system is not in the local dataset.")
    observations = session.scalars(
        select(MarketObservation)
        .where(MarketObservation.commodity_id.in_(commodity_ids))
    ).all()
    rows: list[dict[str, Any]] = []
    now = _now()
    for observation in observations:
        station = observation.station
        system = station.system
        system_distance = distance(origin, system)
        if system_distance > radius or not station_allowed(
            station, system, state, filters
        ):
            continue
        liquidity = observation.demand if selling else observation.supply
        price = observation.sell_price if selling else observation.buy_price
        if price <= 0 or liquidity < quantity:
            continue
        seconds = 60 + jump_count(
            system_distance, state.ship.laden_jump_range
        ) * 55
        score, rating = confidence(
            observed_at=observation.observed_at,
            arrival_seconds=seconds,
            max_age_hours=filters.max_market_age_hours,
            supply=observation.supply,
            demand=observation.demand,
            quantity=quantity,
            fleet_carrier=station.fleet_carrier,
            now=now,
        )
        if filters.hide_low_confidence and rating == "Low":
            continue
        rows.append(
            {
                "commodity_id": observation.commodity_id,
                "commodity": observation.commodity.display_name,
                "market_id": station.market_id,
                "station": station.name,
                "system_id64": system.id64,
                "system": system.name,
                "price": price,
                "quantity": quantity,
                "liquidity": liquidity,
                "estimated_value": price * quantity,
                "distance_ly": round(system_distance, 2),
                "jumps": jump_count(
                    system_distance, state.ship.laden_jump_range
                ),
                "confidence_score": score,
                "confidence": rating,
                "observed_at": observation.observed_at.isoformat(),
                "provider": observation.provider,
            }
        )
    rows.sort(
        key=lambda row: (
            row["price"] if selling else -row["price"],
            row["confidence_score"],
            -row["distance_ly"],
        ),
        reverse=True,
    )
    return rows


def _find_cargo_sale(arguments: dict[str, Any]) -> dict[str, Any]:
    request = _trade_request(arguments)
    manifest = arguments.get("cargo")
    if manifest is None:
        manifest = _elite_state().get("cargo") or []
    if not isinstance(manifest, list) or not manifest:
        return {
            "kind": "cargo_sale",
            "results": [],
            "warning": "No cargo manifest is available.",
            "assumptions": PLANNER_ASSUMPTIONS,
        }
    results: list[dict[str, Any]] = []
    with SessionLocal() as session:
        for item in manifest:
            if not isinstance(item, dict):
                continue
            name = str(
                item.get("name")
                or item.get("Name_Localised")
                or item.get("Name")
                or ""
            )
            quantity = int(item.get("count") or item.get("Count") or 0)
            commodities = _commodity_candidates(session, name)
            if not commodities or quantity <= 0:
                continue
            candidates = _market_destination_rows(
                session,
                state=request.state,
                filters=request.filters,
                commodity_ids=[commodity.id for commodity in commodities],
                quantity=quantity,
                selling=True,
                radius=request.max_system_distance_ly,
            )
            results.extend(candidates[:5])
    return {
        "kind": "cargo_sale",
        "results": results,
        "assumptions": PLANNER_ASSUMPTIONS,
    }


def _source_commodity(arguments: dict[str, Any]) -> dict[str, Any]:
    request = _trade_request(arguments)
    name = str(arguments.get("commodity", "")).strip()
    quantity = int(arguments.get("quantity") or request.state.ship.cargo_capacity)
    if not name:
        raise ValueError("Commodity name is required.")
    if quantity <= 0 or quantity > request.state.ship.cargo_capacity:
        raise ValueError("Quantity must fit within the configured cargo capacity.")
    with SessionLocal() as session:
        commodities = _commodity_candidates(session, name)
        if not commodities:
            return {
                "kind": "commodity_source",
                "commodity": name,
                "quantity": quantity,
                "results": [],
                "warning": "The commodity is not present in the local dataset.",
                "assumptions": PLANNER_ASSUMPTIONS,
            }
        results = _market_destination_rows(
            session,
            state=request.state,
            filters=request.filters,
            commodity_ids=[commodity.id for commodity in commodities],
            quantity=quantity,
            selling=False,
            radius=request.max_system_distance_ly,
        )
    return {
        "kind": "commodity_source",
        "commodity": name,
        "quantity": quantity,
        "results": results[:20],
        "assumptions": PLANNER_ASSUMPTIONS,
    }


def _compare_plans(arguments: dict[str, Any]) -> dict[str, Any]:
    plans = arguments.get("plans")
    if not isinstance(plans, list) or len(plans) < 2:
        raise ValueError("At least two structured plans are required.")
    rows = []
    for index, plan in enumerate(plans[:10]):
        if not isinstance(plan, dict):
            raise ValueError("Each plan must be an object.")
        rows.append(
            {
                "index": index,
                "name": str(
                    plan.get("name")
                    or plan.get("profile")
                    or plan.get("title")
                    or f"Plan {index + 1}"
                )[:120],
                "profit": int(
                    plan.get("total_profit")
                    or plan.get("expected_profit")
                    or plan.get("trip_profit")
                    or 0
                ),
                "estimated_seconds": int(plan.get("estimated_seconds") or 0),
                "distance_ly": float(
                    plan.get("total_distance_ly")
                    or plan.get("system_distance_ly")
                    or 0
                ),
                "confidence": str(plan.get("confidence") or "Unknown"),
                "warnings": list(plan.get("warnings") or []),
            }
        )
    best_profit = max(rows, key=lambda row: row["profit"])["index"]
    fastest = min(
        rows,
        key=lambda row: row["estimated_seconds"]
        if row["estimated_seconds"] > 0
        else float("inf"),
    )["index"]
    return {
        "kind": "plan_comparison",
        "plans": rows,
        "best_profit_index": best_profit,
        "fastest_index": fastest,
    }


def _estimate_reachability(arguments: dict[str, Any]) -> dict[str, Any]:
    state_payload = arguments.get("state")
    if not isinstance(state_payload, dict):
        raise ValueError("Structured commander state is required.")
    state = PlayerState.model_validate(state_payload)
    filters = SearchFilters.model_validate(arguments.get("filters") or {})
    destination_system_id64 = int(arguments.get("destination_system_id64") or 0)
    destination_market_id = arguments.get("destination_station_market_id")
    with SessionLocal() as session:
        origin = session.get(System, state.origin_system_id64)
        destination = session.get(System, destination_system_id64)
        if origin is None or destination is None:
            raise ValueError("Origin or destination is not in the local dataset.")
        system_distance = distance(origin, destination)
        station = (
            session.get(Station, int(destination_market_id))
            if destination_market_id
            else None
        )
        blockers = []
        if destination.permit_required and not filters.include_permit_systems:
            blockers.append("Destination requires a permit.")
        if station and not station_allowed(station, destination, state, filters):
            blockers.append("Destination station conflicts with the current access filters.")
    return {
        "reachable": not blockers,
        "distance_ly": round(system_distance, 2),
        "estimated_jumps": jump_count(
            system_distance, state.ship.laden_jump_range
        ),
        "blockers": blockers,
        "assumptions": [
            "Fuel-star availability and exact star-by-star routing must be verified in-game."
        ],
    }


def _replan_from_current_state(arguments: dict[str, Any]) -> dict[str, Any]:
    kind = str(arguments.get("kind", "one_way")).casefold()
    handlers = {
        "one_way": _search_one_way_trades,
        "round_trip": _search_round_trips,
        "trade_route": _plan_trade_route,
        "transit": _plan_profitable_transit,
    }
    handler = handlers.get(kind)
    if handler is None:
        raise ValueError("Replan kind must be one_way, round_trip, trade_route, or transit.")
    result = handler(arguments)
    result["replanned"] = True
    return result


def _operation_payload(arguments: dict[str, Any]) -> ActiveOperationInput:
    payload = arguments.get("operation", arguments)
    if not isinstance(payload, dict):
        raise ValueError("A structured operation is required.")
    return ActiveOperationInput.model_validate(payload)


def _write_operation(payload: ActiveOperationInput, *, replaced: bool) -> dict[str, Any]:
    now = _now()
    with SessionLocal() as session:
        record = session.get(ActiveOperation, 1)
        values = payload.model_dump()
        if record is None:
            record = ActiveOperation(id=1, updated_at=now, **values)
            session.add(record)
        else:
            for key, value in values.items():
                setattr(record, key, value)
            record.updated_at = now
        session.commit()
    result = _active_operation()
    event_bus.publish(
        "operation.replaced" if replaced else "operation.changed", result
    )
    return {"operation": result}


def _activate_operation(arguments: dict[str, Any]) -> dict[str, Any]:
    return _write_operation(_operation_payload(arguments), replaced=False)


def _replace_operation(arguments: dict[str, Any]) -> dict[str, Any]:
    return _write_operation(_operation_payload(arguments), replaced=True)


def _set_operation_progress(arguments: dict[str, Any]) -> dict[str, Any]:
    action = str(arguments.get("action", "advance")).casefold()
    delta_by_action = {
        "advance": 1,
        "arrive": 1,
        "load": 1,
        "sell": 1,
        "skip": 1,
        "back": -1,
        "reverse": -1,
    }
    if action not in delta_by_action:
        raise ValueError("Unknown operation progress action.")
    with SessionLocal() as session:
        record = session.get(ActiveOperation, 1)
        if record is None:
            raise ValueError("No operation is active.")
        if record.status == "paused":
            raise ValueError("Resume the operation before changing progress.")
        legs = (record.route_payload or {}).get("legs") or []
        maximum = len(legs) if legs else 10000
        record.manual_progress = max(
            0, min(maximum, record.manual_progress + delta_by_action[action])
        )
        if legs and record.manual_progress >= len(legs):
            record.status = "completed"
        record.updated_at = _now()
        session.commit()
    result = _active_operation()
    event_bus.publish("operation.progressed", result)
    return {"action": action, "operation": result}


def _set_operation_status(status: str) -> dict[str, Any]:
    with SessionLocal() as session:
        record = session.get(ActiveOperation, 1)
        if record is None:
            raise ValueError("No operation is active.")
        if record.status == "completed":
            raise ValueError("A completed operation cannot be paused or resumed.")
        record.status = status
        record.updated_at = _now()
        session.commit()
    result = _active_operation()
    event_bus.publish("operation.changed", result)
    return {"operation": result}


def _pause_operation(_arguments: dict[str, Any]) -> dict[str, Any]:
    return _set_operation_status("paused")


def _resume_operation(_arguments: dict[str, Any]) -> dict[str, Any]:
    return _set_operation_status("active")


def _cancel_operation(_arguments: dict[str, Any]) -> dict[str, Any]:
    with SessionLocal() as session:
        record = session.get(ActiveOperation, 1)
        if record is None:
            return {"canceled": False, "operation": None}
        previous = {
            "title": record.title,
            "manual_progress": record.manual_progress,
        }
        session.delete(record)
        session.commit()
    event_bus.publish("operation.changed", None)
    return {"canceled": True, "previous_operation": previous}


def _open_ion_view(arguments: dict[str, Any]) -> dict[str, Any]:
    target = str(arguments.get("view", "")).strip().casefold().replace(" ", "_")
    path = ION_ROUTES.get(target)
    if path is None:
        raise ValueError(f"Unknown ION view: {target or '(empty)'}")
    payload = {"action": "navigate", "path": path, "view": target}
    event_bus.publish("computer.interface.requested", payload)
    return payload


def _open_route_console(_arguments: dict[str, Any]) -> dict[str, Any]:
    payload = {"action": "open_route_console"}
    event_bus.publish("computer.interface.requested", payload)
    return payload


def _populate_planner(arguments: dict[str, Any]) -> dict[str, Any]:
    fields = arguments.get("fields")
    if not isinstance(fields, dict):
        raise ValueError("Planner fields must be an object.")
    safe = {key: value for key, value in fields.items() if key in PLANNER_FIELDS}
    if len(safe) != len(fields):
        raise ValueError("One or more planner fields are not allowlisted.")
    payload = {"action": "populate_planner", "fields": safe}
    event_bus.publish("computer.interface.requested", payload)
    return payload


def _change_search_filters(arguments: dict[str, Any]) -> dict[str, Any]:
    fields = arguments.get("filters")
    if not isinstance(fields, dict):
        raise ValueError("Search filters must be an object.")
    safe = {key: value for key, value in fields.items() if key in FILTER_FIELDS}
    if len(safe) != len(fields):
        raise ValueError("One or more search filters are not allowlisted.")
    payload = {"action": "change_filters", "filters": safe}
    event_bus.publish("computer.interface.requested", payload)
    return payload


def _show_information_card(arguments: dict[str, Any]) -> dict[str, Any]:
    title = str(arguments.get("title", "Computer")).strip()[:120]
    body = str(arguments.get("body", "")).strip()[:4000]
    tone = str(arguments.get("tone", "information"))
    if tone not in {"information", "warning", "critical", "success"}:
        tone = "information"
    if not body:
        raise ValueError("Information-card body is required.")
    payload = {"action": "show_information_card", "title": title, "body": body, "tone": tone}
    event_bus.publish("computer.interface.requested", payload)
    return payload


def _show_diagnostics(_arguments: dict[str, Any]) -> dict[str, Any]:
    payload = {"action": "navigate", "path": "/settings", "view": "settings"}
    event_bus.publish("computer.interface.requested", payload)
    return payload


GAME_TOOL_GROUPS = {
    "set_ship_system": "ship_system",
    "open_game_interface": "game_interface",
    "set_power_distribution": "power",
}


def _game_control(arguments: dict[str, Any], expected_group: str) -> dict[str, Any]:
    action_id = str(arguments.get("action_id", "")).strip()
    action = CONTROLS_BY_ID.get(action_id)
    if action is None or action.group != expected_group or not action.initial_release:
        raise ValueError("The requested action is not allowlisted for this game-control tool.")
    desired_state = arguments.get("desired_state")
    if desired_state is not None and not isinstance(desired_state, bool):
        raise ValueError("desired_state must be true, false, or omitted.")
    _, journal, bindings = _preference_snapshot()
    return input_bridge.execute(
        action_id,
        desired_state,
        BridgeContext(bindings_directory=bindings, journal_directory=journal),
    )


def _set_ship_system(arguments: dict[str, Any]) -> dict[str, Any]:
    return _game_control(arguments, "ship_system")


def _open_game_interface(arguments: dict[str, Any]) -> dict[str, Any]:
    return _game_control(arguments, "game_interface")


def _set_power_distribution(arguments: dict[str, Any]) -> dict[str, Any]:
    return _game_control(arguments, "power")


HANDLERS: dict[str, ToolHandler] = {
    "get_operational_snapshot": _operational_snapshot,
    "get_ship_state": _ship_state,
    "get_navigation_state": _navigation_state,
    "get_cargo_manifest": _cargo_manifest,
    "get_control_capabilities": _control_capabilities,
    "inspect_current_system": _inspect_current_system,
    "get_active_operation": _get_active_operation,
    "get_next_instruction": _next_instruction,
    "search_one_way_trades": _search_one_way_trades,
    "search_round_trips": _search_round_trips,
    "plan_trade_route": _plan_trade_route,
    "plan_profitable_transit": _plan_profitable_transit,
    "find_cargo_sale": _find_cargo_sale,
    "source_commodity": _source_commodity,
    "compare_plans": _compare_plans,
    "estimate_reachability": _estimate_reachability,
    "replan_from_current_state": _replan_from_current_state,
    "activate_operation": _activate_operation,
    "set_operation_progress": _set_operation_progress,
    "pause_operation": _pause_operation,
    "resume_operation": _resume_operation,
    "cancel_operation": _cancel_operation,
    "replace_operation": _replace_operation,
    "open_ion_view": _open_ion_view,
    "open_route_console": _open_route_console,
    "populate_planner": _populate_planner,
    "change_search_filters": _change_search_filters,
    "show_information_card": _show_information_card,
    "show_diagnostics": _show_diagnostics,
    "set_ship_system": _set_ship_system,
    "open_game_interface": _open_game_interface,
    "set_power_distribution": _set_power_distribution,
}


def _authorize_invocation(
    tool_name: str,
    arguments: dict[str, Any],
    preferences: ComputerPreferences,
    source: InvocationSource,
    *,
    confirmed: bool = False,
) -> AuthorizationResult:
    expected_group = GAME_TOOL_GROUPS.get(tool_name)
    if expected_group is not None:
        action_id = str(arguments.get("action_id", "")).strip()
        action = CONTROLS_BY_ID.get(action_id)
        if action is None or action.group != expected_group or not action.initial_release:
            return AuthorizationResult(
                False, "Unknown or prohibited game-control action for this tool."
            )
    tool_result = authorize_tool(
        tool_name, preferences, source, confirmed=confirmed
    )
    if not tool_result.allowed or expected_group is None:
        return tool_result
    return authorize_control_action(
        action_id, preferences, source, confirmed=confirmed
    )


def _serialize_invocation(record: ComputerInvocation) -> dict[str, Any]:
    return {
        "id": record.id,
        "tool_name": record.tool_name,
        "source": record.source,
        "status": record.status,
        "arguments": record.arguments,
        "result": record.result,
        "error": record.error,
        "confirmation_id": record.confirmation_id,
        "created_at": record.created_at.isoformat(),
        "completed_at": (
            record.completed_at.isoformat() if record.completed_at else None
        ),
    }


def _execute_record(invocation_id: str, timeout_seconds: float) -> dict[str, Any]:
    with SessionLocal() as session:
        record = session.get(ComputerInvocation, invocation_id)
        if record is None:
            raise LookupError("Computer invocation was not found.")
        handler = HANDLERS.get(record.tool_name)
        if handler is None:
            record.status = "failed"
            record.error = "This Computer tool is not executable in the current release."
            record.completed_at = _now()
            session.commit()
            event_bus.publish("computer.invocation.failed", _serialize_invocation(record))
            return _serialize_invocation(record)
        record.status = "running"
        session.commit()
        event_bus.publish("computer.invocation.started", _serialize_invocation(record))
        arguments = dict(record.arguments)

    if not _execution_slots.acquire(timeout=timeout_seconds):
        result = None
        status = "timed_out"
        error = "Computer execution capacity was unavailable before the timeout."
    elif record.tool_name in NON_CANCELLABLE_SIDE_EFFECT_TOOLS:
        try:
            result = handler(arguments)
            status = "completed"
            error = None
        except Exception as exc:
            result = None
            status = "failed"
            error = str(exc) or type(exc).__name__
        finally:
            _execution_slots.release()
    else:
        output: Queue[tuple[str, Any]] = Queue(maxsize=1)

        def run_handler() -> None:
            try:
                output.put(("completed", handler(arguments)))
            except Exception as exc:
                output.put(("failed", exc))
            finally:
                _execution_slots.release()

        threading.Thread(
            target=run_handler,
            name=f"ion-computer-{record.tool_name}",
            daemon=True,
        ).start()
        try:
            outcome, value = output.get(timeout=timeout_seconds)
            if outcome == "completed":
                result = value
                status = "completed"
                error = None
            else:
                result = None
                status = "failed"
                error = str(value) or type(value).__name__
        except Empty:
            result = None
            status = "timed_out"
            error = f"Tool execution exceeded the {timeout_seconds:g}-second limit."

    with SessionLocal() as session:
        record = session.get(ComputerInvocation, invocation_id)
        if record is None:
            raise LookupError("Computer invocation was not found.")
        record.status = status
        record.result = result
        record.error = error
        record.completed_at = _now()
        session.commit()
        session.refresh(record)
        serialized = _serialize_invocation(record)
    event_bus.publish(
        "computer.invocation.completed"
        if status == "completed"
        else "computer.invocation.failed",
        serialized,
    )
    return serialized


def invoke_tool(
    tool_name: str,
    arguments: dict[str, Any],
    source: InvocationSource,
    preferences: ComputerPreferences,
    *,
    timeout_seconds: float = 5,
) -> dict[str, Any]:
    authorization = _authorize_invocation(
        tool_name, arguments, preferences, source
    )
    invocation_id = str(uuid4())
    now = _now()
    confirmation_id: str | None = None
    status = "denied"
    error = authorization.reason

    if not authorization.allowed and "confirmation" in authorization.reason.casefold():
        confirmation_id = str(uuid4())
        status = "awaiting_confirmation"
        error = None
    elif authorization.allowed:
        status = "queued"
        error = None

    with SessionLocal() as session:
        if confirmation_id:
            session.add(
                ComputerConfirmation(
                    id=confirmation_id,
                    tool_name=tool_name,
                    source=source.value,
                    arguments=arguments,
                    arguments_hash=_json_hash(arguments),
                    status="pending",
                    created_at=now,
                    expires_at=now + timedelta(minutes=2),
                )
            )
        record = ComputerInvocation(
            id=invocation_id,
            tool_name=tool_name,
            source=source.value,
            status=status,
            arguments=arguments,
            error=error,
            confirmation_id=confirmation_id,
            created_at=now,
        )
        session.add(record)
        session.commit()
        session.refresh(record)
        serialized = _serialize_invocation(record)

    if status == "denied":
        event_bus.publish("computer.invocation.failed", serialized)
        return serialized
    if status == "awaiting_confirmation":
        event_bus.publish(
            "computer.confirmation.requested",
            {
                "confirmation_id": confirmation_id,
                "invocation_id": invocation_id,
                "tool_name": tool_name,
                "arguments": arguments,
                "expires_at": (now + timedelta(minutes=2)).isoformat(),
            },
        )
        return serialized
    return _execute_record(invocation_id, timeout_seconds)


def resolve_confirmation(
    confirmation_id: str,
    preferences: ComputerPreferences,
    *,
    approve: bool,
    timeout_seconds: float = 5,
) -> dict[str, Any]:
    now = _now()
    with SessionLocal() as session:
        confirmation = session.get(ComputerConfirmation, confirmation_id)
        if confirmation is None:
            raise LookupError("Computer confirmation was not found.")
        invocation = session.scalar(
            select(ComputerInvocation).where(
                ComputerInvocation.confirmation_id == confirmation_id
            )
        )
        if invocation is None:
            raise LookupError("The confirmation has no matching invocation.")
        expires_at = confirmation.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if confirmation.status != "pending":
            raise ValueError("This confirmation has already been resolved.")
        if expires_at <= now:
            confirmation.status = "expired"
            confirmation.resolved_at = now
            invocation.status = "expired"
            invocation.error = "Commander confirmation expired."
            invocation.completed_at = now
            session.commit()
            return _serialize_invocation(invocation)
        if not approve:
            confirmation.status = "rejected"
            confirmation.resolved_at = now
            invocation.status = "canceled"
            invocation.error = "Commander rejected the proposed action."
            invocation.completed_at = now
            session.commit()
            result = _serialize_invocation(invocation)
            event_bus.publish("computer.invocation.failed", result)
            return result
        if _json_hash(invocation.arguments) != confirmation.arguments_hash:
            confirmation.status = "invalid"
            confirmation.resolved_at = now
            invocation.status = "failed"
            invocation.error = "Confirmation integrity check failed."
            invocation.completed_at = now
            session.commit()
            return _serialize_invocation(invocation)
        source = InvocationSource(confirmation.source)
        authorization = _authorize_invocation(
            confirmation.tool_name,
            dict(invocation.arguments),
            preferences,
            source,
            confirmed=True,
        )
        if not authorization.allowed:
            invocation.status = "denied"
            invocation.error = authorization.reason
            invocation.completed_at = now
            confirmation.status = "denied"
            confirmation.resolved_at = now
            session.commit()
            return _serialize_invocation(invocation)
        confirmation.status = "approved"
        confirmation.resolved_at = now
        invocation.status = "queued"
        session.commit()
        invocation_id = invocation.id
    return _execute_record(invocation_id, timeout_seconds)


def recent_invocations(limit: int = 50) -> list[dict[str, Any]]:
    with SessionLocal() as session:
        records = session.scalars(
            select(ComputerInvocation)
            .order_by(ComputerInvocation.created_at.desc())
            .limit(max(1, min(limit, 200)))
        ).all()
        return [_serialize_invocation(record) for record in records]


def cancel_invocation(invocation_id: str) -> dict[str, Any]:
    now = _now()
    with SessionLocal() as session:
        invocation = session.get(ComputerInvocation, invocation_id)
        if invocation is None:
            raise LookupError("Computer invocation was not found.")
        if invocation.status not in {"queued", "awaiting_confirmation"}:
            raise ValueError("This invocation can no longer be canceled.")
        if invocation.confirmation_id:
            confirmation = session.get(
                ComputerConfirmation, invocation.confirmation_id
            )
            if confirmation and confirmation.status == "pending":
                confirmation.status = "canceled"
                confirmation.resolved_at = now
        invocation.status = "canceled"
        invocation.error = "Commander canceled the invocation."
        invocation.completed_at = now
        session.commit()
        session.refresh(invocation)
        result = _serialize_invocation(invocation)
    event_bus.publish("computer.invocation.failed", result)
    return result
