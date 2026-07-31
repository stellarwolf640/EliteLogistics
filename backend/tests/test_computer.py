from elite_logistics.api import computer_controls, computer_status, computer_tools
from elite_logistics.computer import (
    CONTROL_ACTIONS,
    TOOL_DEFINITIONS,
    InvocationSource,
    authorize_control_action,
    authorize_tool,
)
from elite_logistics.schemas import ComputerPreferences


def enabled_preferences(
    *actions: str, confirmation_policy: str = "recommended"
) -> ComputerPreferences:
    return ComputerPreferences(
        enabled=True,
        mode="command",
        class_b_enabled=True,
        enabled_game_actions=list(actions),
        confirmation_policy=confirmation_policy,
    )


def test_computer_catalog_has_stable_unique_allowlisted_names():
    tool_names = [tool.name for tool in TOOL_DEFINITIONS]
    action_ids = [action.action_id for action in CONTROL_ACTIONS]

    assert len(tool_names) == len(set(tool_names))
    assert len(action_ids) == len(set(action_ids))
    assert "press_key" not in tool_names
    assert "fire_primary" not in action_ids
    assert "boost" not in action_ids
    assert "self_destruct" not in action_ids


def test_computer_and_class_b_controls_are_disabled_by_default():
    preferences = ComputerPreferences()

    assert not authorize_tool(
        "get_operational_snapshot", preferences, InvocationSource.EXPLICIT_USER
    ).allowed
    assert not authorize_control_action(
        "landing_gear", preferences, InvocationSource.EXPLICIT_USER
    ).allowed


def test_computer_preferences_discard_unknown_or_prohibited_actions():
    preferences = ComputerPreferences(
        enabled_game_actions=["landing_gear", "press_key", "landing_gear"]
    )

    assert preferences.enabled_game_actions == ["landing_gear"]


def test_green_control_requires_explicit_intent_and_per_action_opt_in():
    preferences = enabled_preferences("landing_gear")

    assert not authorize_control_action(
        "landing_gear", preferences, InvocationSource.PROACTIVE
    ).allowed
    assert authorize_control_action(
        "landing_gear", preferences, InvocationSource.EXPLICIT_USER
    ).allowed
    assert not authorize_control_action(
        "cargo_scoop", preferences, InvocationSource.EXPLICIT_USER
    ).allowed


def test_amber_control_requires_confirmation():
    preferences = enabled_preferences("fsd_engage")

    assert not authorize_control_action(
        "fsd_engage", preferences, InvocationSource.EXPLICIT_USER
    ).allowed
    assert authorize_control_action(
        "fsd_engage",
        preferences,
        InvocationSource.CONFIRMED_PROPOSAL,
        confirmed=True,
    ).allowed


def test_confirmation_policy_can_protect_green_or_relax_amber_actions():
    always = enabled_preferences("landing_gear", confirmation_policy="always")
    minimal = enabled_preferences("fsd_engage", confirmation_policy="minimal")

    assert not authorize_control_action(
        "landing_gear", always, InvocationSource.EXPLICIT_USER
    ).allowed
    assert authorize_control_action(
        "landing_gear",
        always,
        InvocationSource.EXPLICIT_USER,
        confirmed=True,
    ).allowed
    assert authorize_control_action(
        "fsd_engage", minimal, InvocationSource.EXPLICIT_USER
    ).allowed


def test_game_tool_cannot_be_invoked_proactively():
    preferences = enabled_preferences("landing_gear")

    result = authorize_tool(
        "set_ship_system", preferences, InvocationSource.PROACTIVE
    )

    assert not result.allowed
    assert "explicit" in result.reason.casefold()


def test_foundation_apis_expose_contracts_without_execution(session):
    status = computer_status(session)
    tools = computer_tools()
    controls = computer_controls()

    assert status["foundation_version"] == 1
    assert status["execution_available"] is False
    assert status["catalog"]["tools"] == len(tools)
    assert status["catalog"]["controls"] == len(controls)
    assert all(tool["implementation_status"] == "contract_only" for tool in tools)
    assert any(control["action_id"] == "landing_gear" for control in controls)
