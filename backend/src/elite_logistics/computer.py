"""Provider-neutral capability and authorization foundation for ION Computer.

This module intentionally contains no model runtime, speech engine, raw input
injection, or tool execution. It defines the stable boundary that those future
adapters must obey.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Protocol


FOUNDATION_VERSION = 1

EXECUTABLE_TOOL_NAMES = frozenset(
    {
        "get_operational_snapshot",
        "get_ship_state",
        "get_navigation_state",
        "get_cargo_manifest",
        "get_control_capabilities",
        "inspect_current_system",
        "get_active_operation",
        "get_next_instruction",
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


class ToolPermission(StrEnum):
    READ = "read"
    ION = "ion"
    GAME_GREEN = "game_green"
    GAME_AMBER = "game_amber"
    CONFIRM = "confirm"


class InvocationSource(StrEnum):
    EXPLICIT_USER = "explicit_user"
    CONFIRMED_PROPOSAL = "confirmed_proposal"
    MANUAL_CONTROL = "manual_control"
    PROACTIVE = "proactive"


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    category: str
    description: str
    permission: ToolPermission
    initial_release: bool = False
    requires_explicit_user: bool = False
    requires_confirmation: bool = False
    proactive_allowed: bool = False
    implementation_status: str = "contract_only"

    def to_dict(self) -> dict:
        value = asdict(self)
        value["permission"] = self.permission.value
        value["implementation_status"] = (
            "available" if self.name in EXECUTABLE_TOOL_NAMES else self.implementation_status
        )
        return value


@dataclass(frozen=True)
class ControlAction:
    action_id: str
    group: str
    label: str
    permission: ToolPermission
    desired_state: bool
    verifiable: bool
    initial_release: bool
    description: str

    def to_dict(self) -> dict:
        value = asdict(self)
        value["permission"] = self.permission.value
        return value


class ComputerPreferenceView(Protocol):
    enabled: bool
    mode: str
    class_b_enabled: bool
    enabled_game_actions: list[str]
    confirmation_policy: str


@dataclass(frozen=True)
class AuthorizationResult:
    allowed: bool
    reason: str


def _tool(
    name: str,
    category: str,
    description: str,
    permission: ToolPermission = ToolPermission.READ,
    *,
    initial: bool = False,
    explicit: bool = False,
    confirm: bool = False,
    proactive: bool = False,
) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        category=category,
        description=description,
        permission=permission,
        initial_release=initial,
        requires_explicit_user=explicit,
        requires_confirmation=confirm,
        proactive_allowed=proactive,
    )


TOOL_DEFINITIONS: tuple[ToolDefinition, ...] = (
    _tool("get_operational_snapshot", "awareness", "Summarize commander, vessel, location, route, cargo, and warnings.", initial=True, proactive=True),
    _tool("get_ship_state", "awareness", "Read detailed vessel and ship-system state.", initial=True, proactive=True),
    _tool("get_navigation_state", "awareness", "Read current target, plotted route, remaining jumps, and estimates.", initial=True, proactive=True),
    _tool("get_cargo_manifest", "awareness", "Read current cargo and active-operation cargo instructions.", initial=True),
    _tool("get_recent_events", "awareness", "Read recent meaningful game-link and operation events."),
    _tool("get_control_capabilities", "awareness", "Report available, unbound, disabled, and protected Class B controls.", initial=True),
    _tool("inspect_current_system", "knowledge", "Describe the current system, stations, access, services, and data freshness.", initial=True),
    _tool("inspect_system", "knowledge", "Describe a specified system."),
    _tool("inspect_station", "knowledge", "Describe station access, services, economy, distance, and market freshness.", initial=True),
    _tool("inspect_commodity", "knowledge", "Explain a commodity and relevant local observations."),
    _tool("find_nearby_service", "knowledge", "Find refuel, repair, restock, outfitting, and other requested services.", initial=True),
    _tool("explain_recommendation", "knowledge", "Explain profit, time, confidence, freshness, liquidity, and access.", initial=True),
    _tool("search_one_way_trades", "planning", "Search practical one-way trades from current or manual state.", initial=True),
    _tool("search_round_trips", "planning", "Search profitable two-leg trade loops.", initial=True),
    _tool("plan_trade_route", "planning", "Build an immersion-oriented multi-stop hauling route.", initial=True),
    _tool("plan_profitable_transit", "planning", "Build Direct, Fast, Balanced, and Profit travel options.", initial=True),
    _tool("find_cargo_sale", "planning", "Find practical destinations for cargo already aboard.", initial=True),
    _tool("source_commodity", "planning", "Find sources for a requested commodity and quantity."),
    _tool("compare_plans", "planning", "Compare selected plans by profit, time, distance, risk, and confidence.", initial=True),
    _tool("estimate_reachability", "planning", "Evaluate jump, fuel, pad, permit, and access constraints."),
    _tool("replan_from_current_state", "planning", "Propose a revised operation after state or route changes."),
    _tool("get_active_operation", "operations", "Read the active operation and progress.", initial=True),
    _tool("get_next_instruction", "operations", "Return one concise next operational instruction.", initial=True, proactive=True),
    _tool("activate_operation", "operations", "Persist and activate a selected operation.", ToolPermission.CONFIRM, initial=True, explicit=True, confirm=True),
    _tool("set_operation_progress", "operations", "Advance, reverse, arrive, load, sell, or skip a route step.", ToolPermission.ION, initial=True),
    _tool("pause_operation", "operations", "Pause operation tracking and announcements.", ToolPermission.ION),
    _tool("resume_operation", "operations", "Resume operation tracking and announcements.", ToolPermission.ION),
    _tool("cancel_operation", "operations", "Cancel the active operation.", ToolPermission.CONFIRM, explicit=True, confirm=True),
    _tool("replace_operation", "operations", "Replace the active operation with a prepared plan.", ToolPermission.CONFIRM, explicit=True, confirm=True),
    _tool("open_ion_view", "interface", "Navigate to a named ION service.", ToolPermission.ION, initial=True),
    _tool("open_route_console", "interface", "Open or focus the native route console.", ToolPermission.ION, initial=True),
    _tool("configure_route_console", "interface", "Change route-console display behavior.", ToolPermission.ION),
    _tool("populate_planner", "interface", "Populate supported planner fields without starting a search.", ToolPermission.ION),
    _tool("change_search_filters", "interface", "Change structured planning filters.", ToolPermission.ION),
    _tool("select_result", "interface", "Select a result by stable identifier.", ToolPermission.ION),
    _tool("show_information_card", "interface", "Display a briefing, warning, comparison, or confirmation card.", ToolPermission.ION),
    _tool("show_diagnostics", "interface", "Open relevant ION diagnostics.", ToolPermission.ION),
    _tool("set_ship_system", "game_control", "Set an allowlisted ship system to a desired state.", ToolPermission.GAME_GREEN, initial=True, explicit=True),
    _tool("open_game_interface", "game_control", "Open an allowlisted map or cockpit panel.", ToolPermission.GAME_GREEN, explicit=True),
    _tool("set_power_distribution", "game_control", "Apply an allowlisted bounded power-distribution action.", ToolPermission.GAME_GREEN, initial=True, explicit=True),
    _tool("control_targeting", "game_control", "Execute one allowlisted targeting action.", ToolPermission.GAME_GREEN, explicit=True),
    _tool("control_fsd", "game_control", "Execute one allowlisted FSD action.", ToolPermission.GAME_AMBER, explicit=True, confirm=True),
    _tool("set_throttle_preset", "game_control", "Apply one allowlisted throttle preset.", ToolPermission.GAME_AMBER, explicit=True, confirm=True),
    _tool("cycle_fire_group", "game_control", "Move to the next or previous fire group without firing.", ToolPermission.GAME_GREEN, explicit=True),
    _tool("deploy_defensive_utility", "game_control", "Use one separately enabled defensive consumable.", ToolPermission.GAME_AMBER, explicit=True, confirm=True),
    _tool("get_computer_preferences", "preferences", "Read Computer voice, verbosity, alert, and permission settings."),
    _tool("propose_preference_change", "preferences", "Describe a preference change without applying it."),
    _tool("set_computer_preference", "preferences", "Apply an approved persistent Computer preference.", ToolPermission.CONFIRM, explicit=True, confirm=True),
    _tool("snooze_alert", "alerts", "Temporarily suppress an alert category.", ToolPermission.ION),
    _tool("acknowledge_alert", "alerts", "Acknowledge an alert without disabling future alerts.", ToolPermission.ION),
)


CONTROL_ACTIONS: tuple[ControlAction, ...] = (
    ControlAction("landing_gear", "ship_system", "Landing gear", ToolPermission.GAME_GREEN, True, True, True, "Deploy or retract landing gear."),
    ControlAction("cargo_scoop", "ship_system", "Cargo scoop", ToolPermission.GAME_GREEN, True, True, True, "Deploy or retract the cargo scoop."),
    ControlAction("hardpoints", "ship_system", "Hardpoints", ToolPermission.GAME_AMBER, True, True, True, "Deploy or retract hardpoints."),
    ControlAction("ship_lights", "ship_system", "Ship lights", ToolPermission.GAME_GREEN, True, True, True, "Turn ship lights on or off."),
    ControlAction("night_vision", "ship_system", "Night vision", ToolPermission.GAME_GREEN, True, True, True, "Turn night vision on or off."),
    ControlAction("silent_running", "ship_system", "Silent running", ToolPermission.GAME_AMBER, True, True, False, "Enable or disable silent running."),
    ControlAction("rotational_correction", "ship_system", "Rotational correction", ToolPermission.GAME_GREEN, True, False, False, "Enable or disable rotational correction."),
    ControlAction("orbit_lines", "ship_system", "Orbit lines", ToolPermission.GAME_GREEN, True, False, False, "Show or hide orbit lines."),
    ControlAction("galaxy_map", "game_interface", "Galaxy Map", ToolPermission.GAME_GREEN, False, False, True, "Open the Galaxy Map."),
    ControlAction("system_map", "game_interface", "System Map", ToolPermission.GAME_GREEN, False, False, True, "Open the System Map."),
    ControlAction("navigation_panel", "game_interface", "Navigation panel", ToolPermission.GAME_GREEN, False, False, True, "Open the navigation panel."),
    ControlAction("communications_panel", "game_interface", "Communications panel", ToolPermission.GAME_GREEN, False, False, True, "Open the communications panel."),
    ControlAction("role_panel", "game_interface", "Role panel", ToolPermission.GAME_GREEN, False, False, True, "Open the role panel."),
    ControlAction("internal_panel", "game_interface", "Internal panel", ToolPermission.GAME_GREEN, False, False, True, "Open the internal panel."),
    ControlAction("power_balance", "power", "Balance power", ToolPermission.GAME_GREEN, False, False, True, "Balance power distribution."),
    ControlAction("power_engines", "power", "Increase engine power", ToolPermission.GAME_GREEN, False, False, True, "Increase engine power by one bounded input."),
    ControlAction("power_systems", "power", "Increase systems power", ToolPermission.GAME_GREEN, False, False, True, "Increase systems power by one bounded input."),
    ControlAction("power_weapons", "power", "Increase weapons power", ToolPermission.GAME_GREEN, False, False, True, "Increase weapons power by one bounded input."),
    ControlAction("target_ahead", "targeting", "Target ahead", ToolPermission.GAME_GREEN, False, False, False, "Target the object ahead."),
    ControlAction("next_target", "targeting", "Next target", ToolPermission.GAME_GREEN, False, False, False, "Select the next target."),
    ControlAction("next_hostile", "targeting", "Next hostile target", ToolPermission.GAME_GREEN, False, False, False, "Select the next hostile target."),
    ControlAction("next_route_system", "targeting", "Next route system", ToolPermission.GAME_GREEN, False, False, False, "Target the next system in the plotted route."),
    ControlAction("fsd_engage", "navigation", "Engage FSD", ToolPermission.GAME_AMBER, False, True, False, "Engage the configured FSD mode."),
    ControlAction("fsd_cancel", "navigation", "Cancel FSD", ToolPermission.GAME_AMBER, False, True, False, "Cancel an FSD charge where supported."),
    ControlAction("throttle_zero", "throttle", "Throttle zero", ToolPermission.GAME_AMBER, False, False, False, "Set throttle to zero."),
    ControlAction("throttle_75", "throttle", "Throttle 75%", ToolPermission.GAME_AMBER, False, False, False, "Set throttle to 75%."),
    ControlAction("chaff", "utility", "Deploy chaff", ToolPermission.GAME_AMBER, False, False, False, "Deploy one chaff charge."),
    ControlAction("heat_sink", "utility", "Deploy heat sink", ToolPermission.GAME_AMBER, False, False, False, "Deploy one heat sink."),
    ControlAction("shield_cell", "utility", "Use shield-cell bank", ToolPermission.GAME_AMBER, False, False, False, "Use one shield-cell bank activation."),
    ControlAction("ecm", "utility", "Activate ECM", ToolPermission.GAME_AMBER, False, False, False, "Activate ECM."),
)


TOOLS_BY_NAME = {tool.name: tool for tool in TOOL_DEFINITIONS}
CONTROLS_BY_ID = {control.action_id: control for control in CONTROL_ACTIONS}

if len(TOOLS_BY_NAME) != len(TOOL_DEFINITIONS):
    raise RuntimeError("Computer tool names must be unique.")
if len(CONTROLS_BY_ID) != len(CONTROL_ACTIONS):
    raise RuntimeError("Computer control action IDs must be unique.")


def tool_catalog() -> list[dict]:
    return [tool.to_dict() for tool in TOOL_DEFINITIONS]


def control_catalog() -> list[dict]:
    return [control.to_dict() for control in CONTROL_ACTIONS]


def _game_confirmation_required(
    permission: ToolPermission, confirmation_policy: str
) -> bool:
    return confirmation_policy == "always" or (
        permission == ToolPermission.GAME_AMBER
        and confirmation_policy != "minimal"
    )


def authorize_tool(
    tool_name: str,
    preferences: ComputerPreferenceView,
    source: InvocationSource,
    *,
    confirmed: bool = False,
) -> AuthorizationResult:
    tool = TOOLS_BY_NAME.get(tool_name)
    if tool is None:
        return AuthorizationResult(False, "Unknown Computer tool.")
    manual_game_control = (
        source == InvocationSource.MANUAL_CONTROL
        and tool.permission in (ToolPermission.GAME_GREEN, ToolPermission.GAME_AMBER)
    )
    if (not preferences.enabled or preferences.mode == "off") and not manual_game_control:
        return AuthorizationResult(False, "ION Computer is disabled.")
    if tool.requires_explicit_user and source == InvocationSource.PROACTIVE:
        return AuthorizationResult(False, "This tool requires an explicit commander action.")
    if source == InvocationSource.PROACTIVE and not tool.proactive_allowed:
        return AuthorizationResult(False, "This tool is not available to proactive events.")
    if tool.permission in (ToolPermission.GAME_GREEN, ToolPermission.GAME_AMBER):
        if not preferences.class_b_enabled:
            return AuthorizationResult(False, "Class B game controls are disabled.")
        if source not in (
            InvocationSource.EXPLICIT_USER,
            InvocationSource.CONFIRMED_PROPOSAL,
            InvocationSource.MANUAL_CONTROL,
        ):
            return AuthorizationResult(False, "Game controls require direct commander intent.")
    confirmation_required = (
        tool.permission == ToolPermission.CONFIRM
        or (
            tool.permission in (ToolPermission.GAME_GREEN, ToolPermission.GAME_AMBER)
            and _game_confirmation_required(
                tool.permission, preferences.confirmation_policy
            )
        )
        or (
            tool.requires_confirmation
            and tool.permission
            not in (ToolPermission.GAME_GREEN, ToolPermission.GAME_AMBER)
        )
    )
    if confirmation_required and not confirmed:
        return AuthorizationResult(False, "Commander confirmation is required.")
    return AuthorizationResult(True, "Authorized by the current Computer policy.")


def authorize_control_action(
    action_id: str,
    preferences: ComputerPreferenceView,
    source: InvocationSource,
    *,
    confirmed: bool = False,
) -> AuthorizationResult:
    action = CONTROLS_BY_ID.get(action_id)
    if action is None:
        return AuthorizationResult(False, "Unknown or prohibited game-control action.")
    if (
        not preferences.enabled or preferences.mode == "off"
    ) and source != InvocationSource.MANUAL_CONTROL:
        return AuthorizationResult(False, "ION Computer is disabled.")
    if not preferences.class_b_enabled:
        return AuthorizationResult(False, "Class B game controls are disabled.")
    if action_id not in preferences.enabled_game_actions:
        return AuthorizationResult(False, "This game-control action is not enabled.")
    if source not in (
        InvocationSource.EXPLICIT_USER,
        InvocationSource.CONFIRMED_PROPOSAL,
        InvocationSource.MANUAL_CONTROL,
    ):
        return AuthorizationResult(False, "Game controls require direct commander intent.")
    if _game_confirmation_required(
        action.permission, preferences.confirmation_policy
    ) and not confirmed:
        return AuthorizationResult(False, "This protected game-control action requires confirmation.")
    return AuthorizationResult(True, "Authorized by the current Computer policy.")
