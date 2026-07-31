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
from .elite_bindings import binding_report, default_bindings_directory
from .elite_data import EliteDataReader, default_journal_directory
from .events import event_bus
from .input_bridge import BridgeContext, input_bridge, keyboard_binding_supported
from .schemas import ComputerPreferences


ToolHandler = Callable[[dict[str, Any]], dict[str, Any]]
_execution_slots = threading.BoundedSemaphore(4)

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

    output: Queue[tuple[str, Any]] = Queue(maxsize=1)
    if not _execution_slots.acquire(timeout=timeout_seconds):
        result = None
        status = "timed_out"
        error = "Computer execution capacity was unavailable before the timeout."
    else:
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
