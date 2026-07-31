import time
from pathlib import Path

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.orm import sessionmaker

from elite_logistics.api import (
    computer_controls,
    computer_status,
    computer_tools,
    execute_manual_computer_control,
    invoke_computer_tool,
    put_computer_settings,
    reset_computer_settings,
)
from elite_logistics.computer import (
    CONTROL_ACTIONS,
    TOOL_DEFINITIONS,
    InvocationSource,
    authorize_control_action,
    authorize_tool,
)
from elite_logistics.computer_runtime import (
    HANDLERS,
    cancel_invocation,
    invoke_tool,
    resolve_confirmation,
)
from elite_logistics.computer_commands import execute_command, interpret_command
from elite_logistics.database import ComputerInvocation
from elite_logistics.elite_bindings import (
    binding_report,
    EliteBindingsMonitor,
    locate_active_bindings,
    parse_bindings_file,
)
from elite_logistics.input_bridge import BridgeContext, InputBridge
from elite_logistics.schemas import (
    ComputerCommandInput,
    ComputerManualControlInput,
    ComputerPreferences,
    ComputerToolInvocationInput,
)


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


def test_computer_apis_expose_executable_and_planned_contracts(session):
    status = computer_status(session)
    tools = computer_tools()
    controls = computer_controls()

    assert status["foundation_version"] == 1
    assert status["execution_available"] is True
    assert status["catalog"]["tools"] == len(tools)
    assert status["catalog"]["controls"] == len(controls)
    assert any(tool["implementation_status"] == "available" for tool in tools)
    assert any(tool["implementation_status"] == "contract_only" for tool in tools)
    assert any(control["action_id"] == "landing_gear" for control in controls)


def test_computer_settings_persist_and_reset_to_safe_defaults(session):
    configured = ComputerPreferences(
        enabled=True,
        mode="command",
        class_b_enabled=True,
        enabled_game_actions=["landing_gear"],
        bindings_directory="C:/Elite/Bindings",
    )

    assert put_computer_settings(configured, session).enabled is True
    reset = reset_computer_settings(session)

    assert reset.enabled is False
    assert reset.mode == "off"
    assert reset.class_b_enabled is False
    assert reset.enabled_game_actions == []
    assert computer_status(session)["settings"]["enabled"] is False


def _runtime_factory(session, monkeypatch):
    factory = sessionmaker(bind=session.get_bind(), expire_on_commit=False)
    monkeypatch.setattr("elite_logistics.computer_runtime.SessionLocal", factory)
    return factory


def test_safe_tool_execution_is_audited_and_proactive_user_tools_are_denied(
    session, monkeypatch
):
    _runtime_factory(session, monkeypatch)
    preferences = ComputerPreferences(enabled=True, mode="command")

    completed = invoke_tool(
        "show_information_card",
        {"title": "Test", "body": "Safe structured message."},
        InvocationSource.EXPLICIT_USER,
        preferences,
    )
    denied = invoke_tool(
        "open_route_console",
        {},
        InvocationSource.PROACTIVE,
        preferences,
    )

    assert completed["status"] == "completed"
    assert completed["result"]["action"] == "show_information_card"
    assert denied["status"] == "denied"
    assert "proactive" in denied["error"].casefold()
    assert session.query(ComputerInvocation).count() == 2


def test_tool_timeout_returns_explicit_failure(session, monkeypatch):
    _runtime_factory(session, monkeypatch)
    preferences = ComputerPreferences(enabled=True, mode="command")
    original = HANDLERS["get_operational_snapshot"]

    def slow_handler(_arguments):
        time.sleep(0.05)
        return {"late": True}

    HANDLERS["get_operational_snapshot"] = slow_handler
    try:
        result = invoke_tool(
            "get_operational_snapshot",
            {},
            InvocationSource.EXPLICIT_USER,
            preferences,
            timeout_seconds=0.01,
        )
    finally:
        HANDLERS["get_operational_snapshot"] = original

    assert result["status"] == "timed_out"
    assert "exceeded" in result["error"]


def test_confirmation_cannot_approve_mutated_arguments(session, monkeypatch):
    _runtime_factory(session, monkeypatch)
    preferences = ComputerPreferences(enabled=True, mode="command")
    proposed = invoke_tool(
        "activate_operation",
        {"operation_id": "route-a"},
        InvocationSource.EXPLICIT_USER,
        preferences,
    )
    assert proposed["status"] == "awaiting_confirmation"

    invocation = session.get(ComputerInvocation, proposed["id"])
    invocation.arguments = {"operation_id": "route-b"}
    session.commit()

    resolved = resolve_confirmation(
        proposed["confirmation_id"], preferences, approve=True
    )
    assert resolved["status"] == "failed"
    assert "integrity" in resolved["error"].casefold()


def test_pending_invocation_can_be_canceled(session, monkeypatch):
    _runtime_factory(session, monkeypatch)
    preferences = ComputerPreferences(enabled=True, mode="command")
    proposed = invoke_tool(
        "activate_operation",
        {"operation_id": "route-a"},
        InvocationSource.EXPLICIT_USER,
        preferences,
    )

    canceled = cancel_invocation(proposed["id"])

    assert canceled["status"] == "canceled"
    assert "Commander canceled" in canceled["error"]


def test_binding_discovery_reads_mixed_devices_and_unbound_actions(tmp_path):
    fixture = (
        Path(__file__).parent
        / "fixtures"
        / "bindings"
        / "MixedCustom.4.1.binds"
    )
    target = tmp_path / fixture.name
    target.write_bytes(fixture.read_bytes())
    (tmp_path / "StartPreset.start").write_text(
        "MissingPreset\nMixedCustom.4.1\nMixedCustom.4.1\n",
        encoding="utf-8",
    )

    assert locate_active_bindings(tmp_path) == target
    report = binding_report(tmp_path)
    capabilities = {
        item["action_id"]: item for item in report["capabilities"]
    }

    assert report["available"] is True
    assert report["device_kinds"] == ["controller", "hotas", "keyboard", "mouse"]
    assert capabilities["landing_gear"]["primary"]["device_kind"] == "keyboard"
    assert capabilities["landing_gear"]["secondary"]["device_kind"] == "hotas"
    assert capabilities["night_vision"]["status"] == "unbound"


def test_binding_discovery_reports_conflicts_and_malformed_files(tmp_path):
    conflict = tmp_path / "Conflict.binds"
    conflict.write_text(
        """<Root PresetName="Conflict">
        <LandingGearToggle><Primary Device="Keyboard" Key="Key_L" /></LandingGearToggle>
        <ToggleCargoScoop><Primary Device="Keyboard" Key="Key_L" /></ToggleCargoScoop>
        </Root>""",
        encoding="utf-8",
    )
    report = parse_bindings_file(conflict)
    assert report["conflict_count"] == 2
    assert all(
        item["status"] == "conflict"
        for item in report["capabilities"]
        if item["action_id"] in {"landing_gear", "cargo_scoop"}
    )

    malformed = tmp_path / "Broken.binds"
    malformed.write_text("<Root><Broken>", encoding="utf-8")
    broken = parse_bindings_file(malformed)
    assert broken["available"] is False
    assert "could not be read" in broken["warning"]


def test_binding_monitor_detects_file_changes_without_sending_input(
    tmp_path, monkeypatch
):
    fixture = (
        Path(__file__).parent
        / "fixtures"
        / "bindings"
        / "MixedCustom.4.1.binds"
    )
    target = tmp_path / fixture.name
    target.write_bytes(fixture.read_bytes())
    monitor = EliteBindingsMonitor()
    monkeypatch.setattr(monitor, "_directory", lambda: tmp_path)

    assert monitor.scan_once() is None
    target.write_text(
        target.read_text(encoding="utf-8").replace(
            'Key="Key_Insert"', 'Key="Key_Home"'
        ),
        encoding="utf-8",
    )
    changed = monitor.scan_once()

    assert changed is not None
    assert changed["available"] is True


def _copy_binding_fixture(tmp_path: Path) -> Path:
    fixture = (
        Path(__file__).parent
        / "fixtures"
        / "bindings"
        / "MixedCustom.4.1.binds"
    )
    target = tmp_path / fixture.name
    target.write_bytes(fixture.read_bytes())
    (tmp_path / "StartPreset.start").write_text(
        "MixedCustom.4.1\n", encoding="utf-8"
    )
    return target


def test_input_bridge_verifies_desired_state_and_prevents_double_toggle(tmp_path):
    _copy_binding_fixture(tmp_path)
    status = {"Flags": 0}
    sent = []

    def send(binding):
        sent.append(binding.display)
        status["Flags"] = 4

    bridge = InputBridge(
        foreground_checker=lambda: True,
        sender=send,
        status_reader=lambda _directory: status,
    )
    context = BridgeContext(tmp_path, tmp_path)

    first = bridge.execute("landing_gear", True, context)
    second = bridge.execute("landing_gear", True, context)

    assert first["outcome"] == "verified"
    assert second["outcome"] == "already_set"
    assert sent == ["Keyboard: LeftControl + L"]


def test_input_bridge_blocks_unfocused_unbound_and_emergency_disabled_actions(
    tmp_path,
):
    _copy_binding_fixture(tmp_path)
    bridge = InputBridge(
        foreground_checker=lambda: False,
        sender=lambda _binding: None,
        status_reader=lambda _directory: {"Flags": 0},
    )
    context = BridgeContext(tmp_path, tmp_path)

    try:
        bridge.execute("landing_gear", True, context)
        assert False, "Unfocused Elite should block input."
    except RuntimeError as exc:
        assert "foreground" in str(exc).casefold()

    try:
        bridge.execute("cargo_scoop", True, context)
        assert False, "A HOTAS-only binding should block input."
    except RuntimeError as exc:
        assert "keyboard binding" in str(exc).casefold()

    bridge.emergency_disable()
    try:
        bridge.execute("landing_gear", True, context)
        assert False, "Emergency disable should block input."
    except RuntimeError as exc:
        assert "emergency-disabled" in str(exc).casefold()


def test_manual_controls_work_with_computer_off_but_still_require_action_opt_in(
    session, monkeypatch
):
    _runtime_factory(session, monkeypatch)
    monkeypatch.setattr(
        "elite_logistics.computer_runtime.input_bridge.execute",
        lambda action_id, desired_state, _context: {
            "action_id": action_id,
            "desired_state": desired_state,
            "outcome": "verified",
        },
    )
    monkeypatch.setattr(
        "elite_logistics.computer_runtime._preference_snapshot",
        lambda: (ComputerPreferences(), Path("."), Path(".")),
    )
    preferences = ComputerPreferences(
        enabled=False,
        mode="off",
        class_b_enabled=True,
        enabled_game_actions=["landing_gear"],
    )

    allowed = invoke_tool(
        "set_ship_system",
        {"action_id": "landing_gear", "desired_state": True},
        InvocationSource.MANUAL_CONTROL,
        preferences,
    )
    denied = invoke_tool(
        "set_ship_system",
        {"action_id": "cargo_scoop", "desired_state": True},
        InvocationSource.MANUAL_CONTROL,
        preferences,
    )

    assert allowed["status"] == "completed", allowed["error"]
    assert denied["status"] == "denied"
    assert "not enabled" in denied["error"].casefold()


def test_deterministic_command_interpreter_extracts_intents_and_clarifies():
    route = interpret_command("Find a round trip within 125 light-years.")
    control = interpret_command("Landing gear down.")
    ambiguous = interpret_command("Landing gear.")
    unsupported = interpret_command("Write me a poem about Sol.")
    followup = interpret_command(
        "Make it 80 ly", {"last_intent": "round_trip"}
    )

    assert route.name == "round_trip"
    assert route.arguments["distance_ly"] == 125
    assert control.arguments == {
        "action_id": "landing_gear",
        "desired_state": True,
    }
    assert ambiguous.clarification
    assert unsupported.name == "unsupported"
    assert followup.arguments["distance_ly"] == 80


def test_deterministic_command_uses_shared_executor(monkeypatch):
    calls = []

    def fake_invoke(tool, arguments, source, _preferences, timeout_seconds):
        calls.append((tool, arguments, source, timeout_seconds))
        return {
            "id": str(len(calls)),
            "tool_name": tool,
            "source": source.value,
            "status": "completed",
            "arguments": arguments,
            "result": {"action": "ok"},
            "error": None,
            "confirmation_id": None,
            "created_at": "2026-01-01T00:00:00+00:00",
            "completed_at": "2026-01-01T00:00:00+00:00",
        }

    monkeypatch.setattr(
        "elite_logistics.computer_commands.invoke_tool", fake_invoke
    )
    preferences = ComputerPreferences(enabled=True, mode="command")

    response = execute_command(
        "Find a round trip within 100 ly", preferences, session_id="test"
    )

    assert response["intent"] == "round_trip"
    assert [call[0] for call in calls] == [
        "change_search_filters",
        "open_ion_view",
    ]
    assert calls[0][1]["filters"]["maxSystemDistanceLy"] == 100
    assert all(call[2] == InvocationSource.EXPLICIT_USER for call in calls)


def test_command_endpoint_contract_rejects_background_activation():
    with pytest.raises(ValidationError):
        ComputerCommandInput(
            text="Landing gear down",
            activation="background",
        )


def test_manual_control_has_dedicated_api_and_generic_source_cannot_spoof_it(
    session, monkeypatch
):
    _runtime_factory(session, monkeypatch)
    monkeypatch.setattr(
        "elite_logistics.computer_runtime._preference_snapshot",
        lambda: (ComputerPreferences(), Path("."), Path(".")),
    )
    monkeypatch.setattr(
        "elite_logistics.computer_runtime.input_bridge.execute",
        lambda action_id, desired_state, _context: {
            "action_id": action_id,
            "desired_state": desired_state,
            "outcome": "verified",
        },
    )
    put_computer_settings(
        ComputerPreferences(
            class_b_enabled=True,
            enabled_game_actions=["landing_gear"],
        ),
        session,
    )

    manual = execute_manual_computer_control(
        ComputerManualControlInput(
            action_id="landing_gear",
            desired_state=True,
        ),
        session,
    )
    assert manual["status"] == "completed"

    with pytest.raises(HTTPException) as exc:
        invoke_computer_tool(
            ComputerToolInvocationInput(
                tool_name="set_ship_system",
                arguments={
                    "action_id": "landing_gear",
                    "desired_state": True,
                },
                source="manual_control",
            ),
            session,
        )
    assert "dedicated endpoint" in str(exc.value).casefold()
