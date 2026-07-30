import asyncio
import base64
from datetime import UTC, datetime

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from elite_logistics.api import (
    _normalize_preferences,
    delete_active_operation,
    get_active_operation,
    put_active_operation,
)
from elite_logistics.desktop import _clamp_bounds
from elite_logistics.config import get_settings
from elite_logistics.events import EventBus
from elite_logistics.schemas import ActiveOperationInput, PreferencesPayload
from elite_logistics.updater import UpdateService, _release_not_found, _version_tuple
import httpx


def test_corrupt_preferences_fall_back_safely():
    value = _normalize_preferences(
        {"schema_version": 2, "close_behavior": "launch-escape-pod", "search_draft": {}}
    )
    assert value == PreferencesPayload()
    assert value.close_behavior == "exit"


def test_frozen_runtime_uses_clean_local_appdata_profile(tmp_path, monkeypatch):
    monkeypatch.delenv("ELITE_LOGISTICS_DATA_DIR", raising=False)
    monkeypatch.delenv("ELITE_LOGISTICS_DATABASE_URL", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr("elite_logistics.config.is_frozen", lambda: True)
    settings = get_settings()
    assert settings.paths.root == tmp_path / "IntraStellar Logistics" / "ION"
    assert settings.paths.database.name == "ion.db"
    assert settings.paths.webview.is_dir()


def test_active_operation_round_trip(session):
    payload = ActiveOperationInput(
        operation_type="cargo_manifest",
        title="Sol to Achenar",
        route_payload={"legs": [], "summary": {"profit": 0, "seconds": 90}},
        activated_at=datetime.now(UTC),
        manual_progress=2,
    )
    written = put_active_operation(payload, session)
    restored = get_active_operation(session)
    assert restored is not None
    assert restored.title == written.title
    assert restored.manual_progress == 2
    delete_active_operation(session)
    assert get_active_operation(session) is None


def test_event_buffer_replays_and_detects_gap():
    bus = EventBus(capacity=2)
    first = bus.publish("one", {})
    second = bus.publish("two", {})
    third = bus.publish("three", {})
    assert [event["type"] for event in bus.replay_after(first["sequence"])] == ["two", "three"]
    fourth = bus.publish("four", {})
    assert bus.replay_after(first["sequence"]) is None
    assert bus.replay_after(second["sequence"])[0]["sequence"] == third["sequence"]
    assert bus.replay_after(third["sequence"])[0]["sequence"] == fourth["sequence"]


def test_event_subscriber_receives_thread_safe_publication():
    async def scenario():
        bus = EventBus()
        subscriber_id, queue = bus.subscribe()
        try:
            bus.publish("operation.changed", {"title": "Test"})
            event = await asyncio.wait_for(queue.get(), 0.5)
            assert event["type"] == "operation.changed"
        finally:
            bus.unsubscribe(subscriber_id)

    asyncio.run(scenario())


def test_invalid_window_position_is_clamped(monkeypatch):
    monkeypatch.setattr(
        "elite_logistics.desktop._screen_bounds", lambda: (0, 0, 1920, 1080)
    )
    value = _clamp_bounds(
        {"x": -5000, "y": 8000, "width": 9000, "height": 9000}, 1500, 950
    )
    assert value["width"] == 1920
    assert value["height"] == 1080
    assert value["x"] >= 0
    assert value["y"] >= 0


def test_update_manifest_requires_matching_ed25519_signature(tmp_path, monkeypatch):
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    public_path = tmp_path / "public.txt"
    public_path.write_text(base64.b64encode(public).decode())
    monkeypatch.setattr(
        "elite_logistics.updater.resource_path", lambda *_parts: public_path
    )
    content = b'{"version":"9.9.9"}\n'
    signature = base64.b64encode(private.sign(content))
    UpdateService()._verify_manifest(content, signature)


def test_semantic_versions_do_not_allow_downgrade():
    assert _version_tuple("v0.2.0") > _version_tuple("0.1.9")


def test_missing_github_release_is_not_an_application_error():
    request = httpx.Request("GET", "https://api.github.com/repos/example/releases/latest")
    response = httpx.Response(404, request=request)

    assert _release_not_found(
        httpx.HTTPStatusError("Not Found", request=request, response=response)
    )
