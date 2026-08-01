import hashlib
import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException

from elite_logistics.api import ComputerDataDeletionInput, delete_local_computer_data
from elite_logistics.computer_alerts import (
    ComputerAlertEngine,
    evaluate_alerts,
    snooze_category,
)
from elite_logistics.computer_commands import execute_command
from elite_logistics.computer_models import (
    MODEL_ALLOWED_TOOLS,
    LocalModelManager,
    verify_model_manifest,
)
from elite_logistics.database import (
    ComputerAlert,
    ComputerInvocation,
    recover_interrupted_computer,
)
from elite_logistics.schemas import ComputerPreferences


def test_alert_facts_are_deterministic_and_critical_alerts_interrupt():
    alerts = evaluate_alerts(
        {
            "fuel_percent": 12.4,
            "hull_health": 28.0,
            "status_flags": ["Low fuel"],
        },
        None,
        None,
        None,
    )

    assert [alert.category for alert in alerts] == ["fuel_risk", "hull_risk"]
    assert all(alert.severity == "critical" for alert in alerts)
    assert all(alert.interrupt_allowed for alert in alerts)
    assert alerts[0].fingerprint == alerts[0].fingerprint


def test_alert_engine_deduplicates_and_never_disables_critical(session):
    engine = ComputerAlertEngine()
    preferences = ComputerPreferences(
        enabled=True,
        proactivity="critical",
        disabled_alert_categories=["fuel_risk"],
    )
    now = datetime.now(UTC)
    state = {"fuel_percent": 10.0, "status_flags": []}

    first = engine.process(session, state, None, preferences, now=now)
    second = engine.process(
        session, state, state, preferences, now=now + timedelta(seconds=10)
    )

    assert len(first) == 1
    assert first[0]["category"] == "fuel_risk"
    assert second == []
    assert session.query(ComputerAlert).count() == 1


def test_critical_alert_categories_cannot_be_snoozed(session):
    with pytest.raises(ValueError, match="cannot be snoozed"):
        snooze_category(session, "fuel_risk", 30)


def test_model_manifest_requires_matching_tier_and_checksum(tmp_path):
    model = tmp_path / "lite.gguf"
    model.write_bytes(b"verified local model fixture")
    digest = hashlib.sha256(model.read_bytes()).hexdigest()
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "tier": "lite",
                "version": "test-1",
                "model_file": model.name,
                "sha256": digest,
                "estimated_memory_mb": 1024,
            }
        ),
        encoding="utf-8",
    )

    verified, error = verify_model_manifest(str(manifest), "lite")
    assert error is None
    assert verified is not None
    assert verified.sha256 == digest

    model.write_bytes(b"corrupted")
    verified, error = verify_model_manifest(str(manifest), "lite")
    assert verified is None
    assert error == "checksum_failed"


def test_model_status_evaluation_is_bound_to_selected_model(tmp_path):
    def manifest(tier: str, contents: bytes):
        model = tmp_path / f"{tier}.gguf"
        model.write_bytes(contents)
        digest = hashlib.sha256(contents).hexdigest()
        path = tmp_path / f"{tier}.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "tier": tier,
                    "version": "test",
                    "model_file": model.name,
                    "sha256": digest,
                    "estimated_memory_mb": 1024,
                }
            ),
            encoding="utf-8",
        )
        return path, digest

    lite_path, lite_hash = manifest("lite", b"lite")
    enhanced_path, _enhanced_hash = manifest("enhanced", b"enhanced")
    preferences = ComputerPreferences(
        mode="enhanced",
        model_runtime_enabled=True,
        lite_model_manifest=str(lite_path),
        enhanced_model_manifest=str(enhanced_path),
        model_evaluated_sha256=lite_hash,
        model_evaluation_score=1.0,
    )

    status = LocalModelManager().status(preferences)
    assert status["lite"]["verified"] is True
    assert status["enhanced"]["verified"] is True
    assert status["evaluation_current"] is False


def test_model_tool_allowlist_excludes_game_controls_and_preferences():
    assert "set_ship_system" not in MODEL_ALLOWED_TOOLS
    assert "open_game_interface" not in MODEL_ALLOWED_TOOLS
    assert "set_power_distribution" not in MODEL_ALLOWED_TOOLS
    assert "change_computer_settings" not in MODEL_ALLOWED_TOOLS


def test_unavailable_local_model_falls_back_to_deterministic_command():
    response = execute_command(
        "This is intentionally unsupported",
        ComputerPreferences(
            enabled=True,
            mode="lite",
            model_runtime_enabled=True,
        ),
    )

    assert response["runtime"] == "command"
    assert "deterministic command mode" in response["runtime_warning"].casefold()


def test_restart_recovery_fails_invocations_without_retry(session):
    now = datetime.now(UTC)
    session.add(
        ComputerInvocation(
            id="interrupted",
            tool_name="set_ship_system",
            source="explicit_user",
            status="running",
            arguments={"action_id": "landing_gear"},
            created_at=now,
        )
    )
    session.commit()

    assert recover_interrupted_computer(session) == 1
    recovered = session.get(ComputerInvocation, "interrupted")
    assert recovered.status == "failed"
    assert "not retried" in recovered.error
    assert recovered.completed_at is not None


def test_local_data_deletion_requires_exact_confirmation(session):
    with pytest.raises(HTTPException) as exc:
        delete_local_computer_data(
            ComputerDataDeletionInput(confirmation="delete it"),
            session,
        )

    assert exc.value.status_code == 400
