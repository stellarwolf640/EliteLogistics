"""Deterministic, low-overhead typed command interpreter for ION Computer."""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from .computer import InvocationSource
from .computer_runtime import invoke_tool
from .schemas import ComputerPreferences


@dataclass(frozen=True)
class Intent:
    name: str
    confidence: float
    arguments: dict[str, Any]
    clarification: str | None = None


_contexts: dict[str, dict[str, Any]] = {}
_context_lock = threading.Lock()


def _normalized(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9.%]+", " ", text.casefold()).split()).strip(
        " ."
    )


def interpret_command(text: str, context: dict[str, Any] | None = None) -> Intent:
    value = _normalized(text)
    if not value:
        return Intent("empty", 0.0, {}, "Enter a command for ION Computer.")

    if value in {"brief me", "briefing", "status report", "give me a briefing"}:
        return Intent("briefing", 1.0, {})
    if value in {"where am i", "current location", "what system am i in"}:
        return Intent("location", 1.0, {})
    if value in {
        "what is my next stop",
        "whats my next stop",
        "next stop",
        "next instruction",
        "what do i do next",
    }:
        return Intent("next_instruction", 1.0, {})
    if value in {"open route console", "show route console", "open active route"}:
        return Intent("open_route_console", 1.0, {})

    distance_match = re.fullmatch(
        r"(?:find|search for|show me) (?:a )?round trip(?: trade)?(?: within| under| up to) (\d+(?:\.\d+)?)"
        r"(?: light years?| ly)?",
        value,
    )
    if distance_match:
        distance = float(distance_match.group(1))
        if not 1 <= distance <= 1000:
            return Intent(
                "round_trip",
                0.95,
                {},
                "Choose a round-trip distance between 1 and 1,000 light-years.",
            )
        return Intent("round_trip", 0.98, {"distance_ly": distance})
    followup_match = re.fullmatch(
        r"(?:make it|change (?:that|it) to|use) (\d+(?:\.\d+)?)"
        r"(?: light years?| ly)",
        value,
    )
    if followup_match and context and context.get("last_intent") == "round_trip":
        distance = float(followup_match.group(1))
        if not 1 <= distance <= 1000:
            return Intent(
                "round_trip",
                0.9,
                {},
                "Choose a round-trip distance between 1 and 1,000 light-years.",
            )
        return Intent("round_trip", 0.92, {"distance_ly": distance})

    if value in {
        "exclude planetary stations",
        "remove planetary stations",
        "no planetary stations",
    }:
        return Intent("filter", 1.0, {"includePlanetary": False})
    if value in {
        "exclude fleet carriers",
        "remove fleet carriers",
        "no fleet carriers",
    }:
        return Intent("filter", 1.0, {"includeFleetCarriers": False})
    if value in {"include planetary stations", "allow planetary stations"}:
        return Intent("filter", 1.0, {"includePlanetary": True})
    if value in {"include fleet carriers", "allow fleet carriers"}:
        return Intent("filter", 1.0, {"includeFleetCarriers": True})

    state_match = re.fullmatch(
        r"(?:set )?(landing gear|gear|cargo scoop|scoop|lights|ship lights|night vision|hardpoints)"
        r"(?: to)? (down|up|on|off|open|closed|deploy|deployed|retract|retracted)",
        value,
    )
    if state_match:
        subject, requested = state_match.groups()
        action_id = {
            "landing gear": "landing_gear",
            "gear": "landing_gear",
            "cargo scoop": "cargo_scoop",
            "scoop": "cargo_scoop",
            "lights": "ship_lights",
            "ship lights": "ship_lights",
            "night vision": "night_vision",
            "hardpoints": "hardpoints",
        }[subject]
        desired = requested in {"down", "on", "open", "deploy", "deployed"}
        return Intent(
            "ship_system",
            0.98 if subject not in {"gear", "scoop", "lights"} else 0.92,
            {"action_id": action_id, "desired_state": desired},
        )
    if value in {
        "landing gear",
        "gear",
        "cargo scoop",
        "scoop",
        "lights",
        "ship lights",
        "night vision",
        "hardpoints",
    }:
        return Intent(
            "ambiguous_control",
            0.75,
            {},
            f"Should I turn {value} on or off?",
        )

    interface_actions = {
        "open galaxy map": "galaxy_map",
        "show galaxy map": "galaxy_map",
        "open system map": "system_map",
        "show system map": "system_map",
        "open navigation panel": "navigation_panel",
        "open nav panel": "navigation_panel",
        "open communications panel": "communications_panel",
        "open comms panel": "communications_panel",
        "open role panel": "role_panel",
        "open internal panel": "internal_panel",
    }
    if value in interface_actions:
        return Intent(
            "game_interface", 1.0, {"action_id": interface_actions[value]}
        )
    power_actions = {
        "balance power": "power_balance",
        "balance pips": "power_balance",
        "power to engines": "power_engines",
        "increase engine power": "power_engines",
        "power to systems": "power_systems",
        "increase systems power": "power_systems",
        "power to weapons": "power_weapons",
        "increase weapons power": "power_weapons",
    }
    if value in power_actions:
        return Intent("power", 1.0, {"action_id": power_actions[value]})

    return Intent(
        "unsupported",
        0.0,
        {},
        "I did not recognize that command. Try “Brief me,” “Where am I,” "
        "“Find a round trip within 100 ly,” or one of the suggested controls.",
    )


def execute_command(
    text: str,
    preferences: ComputerPreferences,
    *,
    session_id: str | None = None,
) -> dict[str, Any]:
    session_id = session_id or str(uuid4())
    with _context_lock:
        context = dict(_contexts.get(session_id, {}))
    intent = interpret_command(text, context)
    response: dict[str, Any] = {
        "session_id": session_id,
        "text": text,
        "intent": intent.name,
        "confidence": intent.confidence,
        "clarification": intent.clarification,
        "reply": intent.clarification or "",
        "invocations": [],
        "suggestions": [
            "Brief me",
            "Where am I?",
            "What is my next stop?",
            "Find a round trip within 100 ly",
            "Open route console",
        ],
    }
    if intent.clarification or intent.confidence < 0.85:
        return response

    def run(tool: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        invocation = invoke_tool(
            tool,
            arguments or {},
            InvocationSource.EXPLICIT_USER,
            preferences,
            timeout_seconds=5,
        )
        response["invocations"].append(invocation)
        return invocation

    if intent.name == "briefing":
        invocation = run("get_operational_snapshot")
        if invocation["status"] != "completed":
            response["reply"] = _execution_reply(invocation, "")
            return response
        data = invocation.get("result") or {}
        location = data.get("location") or {}
        ship = data.get("ship") or {}
        navigation = data.get("navigation") or {}
        response["reply"] = (
            f"{_address(preferences)} You are in "
            f"{location.get('system') or 'an unknown system'}"
            f"{_station_phrase(location.get('station'))}. "
            f"Vessel: {ship.get('name') or ship.get('model') or 'unknown'}. "
            f"Cargo: {ship.get('cargo_count') or 0}"
            f"/{ship.get('cargo_capacity') or '—'} tonnes. "
            f"Navigation target: {navigation.get('target_system') or 'none'}."
        )
    elif intent.name == "location":
        invocation = run("get_operational_snapshot")
        if invocation["status"] != "completed":
            response["reply"] = _execution_reply(invocation, "")
            return response
        location = (invocation.get("result") or {}).get("location") or {}
        response["reply"] = (
            f"{_address(preferences)} Current location: "
            f"{location.get('system') or 'unknown system'}"
            f"{_station_phrase(location.get('station'))}."
        )
    elif intent.name == "next_instruction":
        invocation = run("get_next_instruction")
        result = invocation.get("result") or {}
        response["reply"] = str(
            result.get("instruction") or invocation.get("error") or "No instruction is available."
        )
    elif intent.name == "open_route_console":
        invocation = run("open_route_console")
        response["reply"] = _execution_reply(invocation, "Opening the active route console.")
    elif intent.name == "round_trip":
        distance = intent.arguments["distance_ly"]
        first = run(
            "change_search_filters",
            {"filters": {"maxSystemDistanceLy": distance}},
        )
        second = run("open_ion_view", {"view": "round_trips"})
        if first["status"] == second["status"] == "completed":
            response["reply"] = (
                f"Round-trip planner opened with a {distance:g} light-year search radius. "
                "Review the commander state, then start the search."
            )
        else:
            response["reply"] = _first_error(response["invocations"])
    elif intent.name == "filter":
        invocation = run("change_search_filters", {"filters": intent.arguments})
        label = next(iter(intent.arguments)).replace("include", "").replace("_", " ")
        state = "included" if next(iter(intent.arguments.values())) else "excluded"
        response["reply"] = _execution_reply(
            invocation, f"{label.strip().title()} are now {state}."
        )
    elif intent.name == "ship_system":
        invocation = run("set_ship_system", intent.arguments)
        response["reply"] = _control_reply(invocation)
    elif intent.name == "game_interface":
        invocation = run("open_game_interface", intent.arguments)
        response["reply"] = _control_reply(invocation)
    elif intent.name == "power":
        invocation = run("set_power_distribution", intent.arguments)
        response["reply"] = _control_reply(invocation)

    with _context_lock:
        if len(_contexts) >= 100:
            _contexts.pop(next(iter(_contexts)))
        _contexts[session_id] = {
            "last_intent": intent.name,
            "arguments": intent.arguments,
        }
    return response


def _address(preferences: ComputerPreferences) -> str:
    return "Commander," if preferences.address_as_commander else ""


def _station_phrase(station: Any) -> str:
    return f", at {station}" if station else ""


def _first_error(invocations: list[dict[str, Any]]) -> str:
    return next(
        (
            str(value.get("error"))
            for value in invocations
            if value.get("error")
        ),
        "The command could not be completed.",
    )


def _execution_reply(invocation: dict[str, Any], success: str) -> str:
    if invocation["status"] == "completed":
        return success
    if invocation["status"] == "awaiting_confirmation":
        return "Commander confirmation is required before I can continue."
    return str(invocation.get("error") or "The command could not be completed.")


def _control_reply(invocation: dict[str, Any]) -> str:
    if invocation["status"] != "completed":
        return _execution_reply(invocation, "Command sent.")
    result = invocation.get("result") or {}
    return {
        "already_set": "The requested state is already set; no input was sent.",
        "verified": "Command completed and verified by Elite telemetry.",
        "sent_unverified": "Command sent. Elite does not expose a reliable completion state.",
        "timed_out": "Command sent, but telemetry did not confirm it. I did not retry.",
    }.get(str(result.get("outcome")), "Command completed.")
