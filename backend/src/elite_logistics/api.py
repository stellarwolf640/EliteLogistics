from __future__ import annotations

from datetime import UTC, datetime
import os
from pathlib import Path
from typing import Annotated, Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .config import get_settings
from .computer import (
    FOUNDATION_VERSION as COMPUTER_FOUNDATION_VERSION,
    CONTROL_ACTIONS,
    EXECUTABLE_TOOL_NAMES,
    InvocationSource,
    TOOL_DEFINITIONS,
    control_catalog,
    tool_catalog,
)
from .database import (
    ActiveOperation,
    DataImport,
    Job,
    MarketObservation,
    Preference,
    ShipProfile,
    Station,
    System,
    get_session,
)
from .events import event_bus
from .engine import find_immersive_trade_routes, find_round_trips, find_trades
from .elite_data import EliteDataReader, default_journal_directory, sync_current_market
from .jobs import start_import_job, start_transit_job
from .providers import SpanshRemoteProvider
from .schemas import (
    LocationResult,
    EliteSettingsInput,
    ActiveOperationInput,
    ActiveOperationOutput,
    ImmersiveTradeRouteResponse,
    RoundTripResponse,
    ShipProfileInput,
    ShipProfileOutput,
    TradeSearchRequest,
    TradeSearchResponse,
    TransitRequest,
    PreferencesPayload,
    ComputerPreferences,
    ComputerToolInvocationInput,
)
from .version import APP_VERSION
from .updater import update_service

router = APIRouter(prefix="/api")
DEFAULT_PREFERENCES = PreferencesPayload().model_dump(mode="json")


def _normalize_preferences(values: dict | None) -> PreferencesPayload:
    values = values or {}
    if values.get("schema_version") in (2, 3):
        migrated = {**values, "schema_version": 3}
        migrated.setdefault("computer", {})
        try:
            return PreferencesPayload.model_validate(migrated)
        except ValueError:
            return PreferencesPayload()
    # One-time compatibility for source/development profiles. Frozen builds use
    # a clean Local AppData profile and therefore never inspect repository data.
    defaults = PreferencesPayload()
    search = defaults.search_draft.model_dump()
    for key in search:
        if key in values:
            search[key] = values[key]
    return PreferencesPayload(
        search_draft=search,
        data_mode=values.get("data_mode", "live"),
        elite_enabled=bool(values.get("elite_enabled", False)),
        elite_journal_directory=str(values.get("elite_journal_directory", "")),
        elite_auto_apply_planning_state=bool(
            values.get("elite_auto_apply_planning_state", False)
        ),
    )


def _load_preferences(session: Session) -> PreferencesPayload:
    record = session.get(Preference, 1)
    return _normalize_preferences(record.values if record else None)


def _save_preferences(session: Session, preferences: PreferencesPayload) -> PreferencesPayload:
    values = preferences.model_dump(mode="json")
    record = session.get(Preference, 1)
    if record is None:
        session.add(Preference(id=1, schema_version=3, values=values))
    else:
        record.schema_version = 3
        record.values = values
    session.commit()
    return preferences


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "version": APP_VERSION}


@router.get("/diagnostics")
def diagnostics(session: Session = Depends(get_session)) -> dict:
    settings = get_settings()
    database_ok = True
    try:
        session.execute(select(1))
    except Exception:
        database_ok = False
    log_file = settings.paths.logs / "ion.log"
    recent_errors: list[str] = []
    if log_file.exists():
        try:
            recent_errors = [
                line.rstrip()
                for line in log_file.read_text(encoding="utf-8", errors="replace").splitlines()
                if "ERROR" in line or "CRITICAL" in line
            ][-20:]
        except OSError:
            pass
    return {
        "version": APP_VERSION,
        "packaged": settings.packaged,
        "runtime_paths": {
            "profile": str(settings.paths.root),
            "database": str(settings.paths.database),
            "cache": str(settings.paths.cache),
            "downloads": str(settings.paths.downloads),
            "logs": str(settings.paths.logs),
            "updates": str(settings.paths.updates),
            "webview": str(settings.paths.webview),
        },
        "database_ok": database_ok,
        "webview2_available": (
            os.getenv("ION_WEBVIEW2_AVAILABLE") == "1"
            if "ION_WEBVIEW2_AVAILABLE" in os.environ
            else None
        ),
        "game_link": elite_status(session),
        "recent_errors": recent_errors,
    }


@router.get("/updates/status")
def update_status() -> dict:
    return update_service.status()


@router.post("/updates/check")
def check_for_updates() -> dict:
    return update_service.check(force=True)


@router.post("/updates/download", status_code=status.HTTP_202_ACCEPTED)
def download_update() -> dict:
    try:
        update_service.begin_download()
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    return update_service.status()


@router.get("/data/status")
def data_status(session: Session = Depends(get_session)) -> dict:
    latest = session.scalar(select(func.max(MarketObservation.observed_at)))
    pack_path = get_settings().data_dir / "galaxy_stations.json.gz"
    partial_pack_path = pack_path.with_suffix(pack_path.suffix + ".part")
    database_path = get_settings().paths.database
    return {
        "systems": session.scalar(select(func.count()).select_from(System)) or 0,
        "stations": session.scalar(select(func.count()).select_from(Station)) or 0,
        "market_observations": session.scalar(select(func.count()).select_from(MarketObservation)) or 0,
        "latest_market_observation": latest,
        "online_provider": "Spansh",
        "pack_path": str(pack_path),
        "pack_installed": pack_path.exists(),
        "pack_bytes": pack_path.stat().st_size if pack_path.exists() else 0,
        "partial_pack_bytes": partial_pack_path.stat().st_size if partial_pack_path.exists() else 0,
        "database_bytes": database_path.stat().st_size if database_path.exists() else 0,
    }


@router.get("/data/spansh-pack-info")
async def spansh_pack_info() -> dict:
    url = "https://downloads.spansh.co.uk/galaxy_stations.json.gz"
    try:
        async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
            response = await client.head(url)
            response.raise_for_status()
            return {
                "url": url,
                "bytes": int(response.headers.get("content-length", 0) or 0),
                "available": True,
            }
    except httpx.HTTPError as exc:
        return {"url": url, "bytes": 0, "available": False, "error": str(exc)}


@router.get("/locations/search", response_model=list[LocationResult])
async def locations(
    q: str = Query(min_length=1),
    kind: Literal["all", "system", "station"] = "all",
    limit: int = Query(default=20, ge=1, le=50),
    session: Session = Depends(get_session),
) -> list[LocationResult]:
    needle = f"%{' '.join(q.casefold().split())}%"
    results: list[LocationResult] = []
    if kind in ("all", "system"):
        systems = session.scalars(
            select(System).where(System.normalized_name.like(needle)).order_by(System.name).limit(limit)
        ).all()
        results.extend(
            LocationResult(
                kind="system",
                id=item.id64,
                name=item.name,
                system_id64=item.id64,
                system_name=item.name,
                subtitle="Star system",
            )
            for item in systems
        )
    if kind in ("all", "station") and len(results) < limit:
        stations = session.scalars(
            select(Station)
            .where(Station.normalized_name.like(needle))
            .order_by(Station.name)
            .limit(limit - len(results))
        ).all()
        results.extend(
            LocationResult(
                kind="station",
                id=item.market_id,
                name=item.name,
                system_id64=item.system_id64,
                system_name=item.system.name,
                subtitle=f"{item.system.name} · {item.distance_to_arrival_ls:,.0f} ls",
            )
            for item in stations
        )
    if len(results) >= min(5, limit):
        return results
    try:
        provider = SpanshRemoteProvider(get_settings())
        remote = await provider.search_locations(q, limit)
        provider.cache_search_results(session, remote)
        existing = {(item.kind, item.id) for item in results}
        for result in remote:
            record = result.get("record", result)
            result_type = result.get("type")
            if result_type == "system" and kind in ("all", "system"):
                item = LocationResult(
                    kind="system",
                    id=int(record["id64"]),
                    name=record["name"],
                    system_id64=int(record["id64"]),
                    system_name=record["name"],
                    subtitle="Star system · Spansh",
                )
            elif result_type == "station" and kind in ("all", "station") and record.get("market_id"):
                item = LocationResult(
                    kind="station",
                    id=int(record["market_id"]),
                    name=record["name"],
                    system_id64=int(record["system_id64"]),
                    system_name=record["system_name"],
                    subtitle=f"{record['system_name']} · {float(record.get('distance_to_arrival', 0)):,.0f} ls · Spansh",
                )
            else:
                continue
            if (item.kind, item.id) not in existing:
                results.append(item)
                existing.add((item.kind, item.id))
            if len(results) >= limit:
                break
    except RuntimeError:
        pass
    return results[:limit]


@router.get("/ship-profiles", response_model=list[ShipProfileOutput])
def list_profiles(session: Session = Depends(get_session)) -> list[ShipProfile]:
    return list(session.scalars(select(ShipProfile).order_by(ShipProfile.name)).all())


@router.post("/ship-profiles", response_model=ShipProfileOutput, status_code=status.HTTP_201_CREATED)
def create_profile(payload: ShipProfileInput, session: Session = Depends(get_session)) -> ShipProfile:
    profile = ShipProfile(**payload.model_dump())
    session.add(profile)
    session.commit()
    session.refresh(profile)
    return profile


@router.put("/ship-profiles/{profile_id}", response_model=ShipProfileOutput)
def update_profile(profile_id: int, payload: ShipProfileInput, session: Session = Depends(get_session)) -> ShipProfile:
    profile = session.get(ShipProfile, profile_id)
    if profile is None:
        raise HTTPException(404, "Ship profile not found")
    for key, value in payload.model_dump().items():
        setattr(profile, key, value)
    session.commit()
    session.refresh(profile)
    return profile


@router.delete("/ship-profiles/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_profile(profile_id: int, session: Session = Depends(get_session)) -> Response:
    profile = session.get(ShipProfile, profile_id)
    if profile is None:
        raise HTTPException(404, "Ship profile not found")
    session.delete(profile)
    session.commit()
    return Response(status_code=204)


@router.get("/preferences", response_model=PreferencesPayload)
def get_preferences(session: Session = Depends(get_session)) -> PreferencesPayload:
    return _load_preferences(session)


@router.put("/preferences", response_model=PreferencesPayload)
def put_preferences(
    values: PreferencesPayload, session: Session = Depends(get_session)
) -> PreferencesPayload:
    return _save_preferences(session, values)


@router.put("/computer/settings", response_model=ComputerPreferences)
def put_computer_settings(
    values: ComputerPreferences, session: Session = Depends(get_session)
) -> ComputerPreferences:
    preferences = _load_preferences(session)
    preferences.computer = values
    _save_preferences(session, preferences)
    event_bus.publish("computer.settings.changed", values.model_dump(mode="json"))
    return values


@router.post("/computer/settings/reset", response_model=ComputerPreferences)
def reset_computer_settings(
    session: Session = Depends(get_session),
) -> ComputerPreferences:
    preferences = _load_preferences(session)
    preferences.computer = ComputerPreferences()
    _save_preferences(session, preferences)
    event_bus.publish(
        "computer.settings.changed",
        preferences.computer.model_dump(mode="json"),
    )
    return preferences.computer


@router.get("/computer/status")
def computer_status(session: Session = Depends(get_session)) -> dict:
    preferences = _load_preferences(session).computer
    initial_tools = sum(tool.initial_release for tool in TOOL_DEFINITIONS)
    initial_controls = sum(control.initial_release for control in CONTROL_ACTIONS)
    return {
        "foundation_version": COMPUTER_FOUNDATION_VERSION,
        "settings": preferences.model_dump(mode="json"),
        "runtimes": {
            "command": "policy_runtime",
            "language_model": "not_configured",
            "speech_recognition": "not_configured",
            "text_to_speech": "not_configured",
            "input_bridge": "not_installed",
            "bindings": "discovery_available",
        },
        "catalog": {
            "tools": len(TOOL_DEFINITIONS),
            "initial_tools": initial_tools,
            "controls": len(CONTROL_ACTIONS),
            "initial_controls": initial_controls,
        },
        "execution_available": True,
        "executable_tools": sorted(EXECUTABLE_TOOL_NAMES),
        "warnings": [
            "Command, Lite, Enhanced, speech, and game-input execution are not installed yet.",
            "Class B settings and bindings are preparatory only; ION cannot send game inputs.",
        ],
    }


@router.get("/computer/tools")
def computer_tools(
    category: Annotated[str | None, Query(max_length=60)] = None,
) -> list[dict]:
    tools = tool_catalog()
    return [tool for tool in tools if category is None or tool["category"] == category]


@router.get("/computer/controls")
def computer_controls(
    group: Annotated[str | None, Query(max_length=60)] = None,
) -> list[dict]:
    controls = control_catalog()
    return [control for control in controls if group is None or control["group"] == group]


@router.post("/computer/tools/invoke")
def invoke_computer_tool(
    payload: ComputerToolInvocationInput,
    session: Session = Depends(get_session),
) -> dict:
    from .computer_runtime import invoke_tool

    preferences = _load_preferences(session).computer
    try:
        source = InvocationSource(payload.source)
        return invoke_tool(
            payload.tool_name,
            payload.arguments,
            source,
            preferences,
            timeout_seconds=payload.timeout_seconds,
        )
    except (LookupError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc


class ComputerConfirmationInput(BaseModel):
    approve: bool
    timeout_seconds: float = Field(default=5, ge=0.1, le=30)


@router.post("/computer/confirmations/{confirmation_id}")
def resolve_computer_confirmation(
    confirmation_id: str,
    payload: ComputerConfirmationInput,
    session: Session = Depends(get_session),
) -> dict:
    from .computer_runtime import resolve_confirmation

    preferences = _load_preferences(session).computer
    try:
        return resolve_confirmation(
            confirmation_id,
            preferences,
            approve=payload.approve,
            timeout_seconds=payload.timeout_seconds,
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/computer/invocations")
def get_computer_invocations(
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[dict]:
    from .computer_runtime import recent_invocations

    return recent_invocations(limit)


@router.post("/computer/invocations/{invocation_id}/cancel")
def cancel_computer_invocation(invocation_id: str) -> dict:
    from .computer_runtime import cancel_invocation

    try:
        return cancel_invocation(invocation_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/computer/bindings")
def get_computer_bindings(session: Session = Depends(get_session)) -> dict:
    from .elite_bindings import binding_report, default_bindings_directory

    configured = _load_preferences(session).computer.bindings_directory.strip()
    directory = (
        Path(configured).expanduser().resolve()
        if configured
        else default_bindings_directory()
    )
    return binding_report(directory)


@router.get("/operations/active", response_model=ActiveOperationOutput | None)
def get_active_operation(
    session: Session = Depends(get_session),
) -> ActiveOperationOutput | None:
    record = session.get(ActiveOperation, 1)
    return ActiveOperationOutput.model_validate(record, from_attributes=True) if record else None


@router.put("/operations/active", response_model=ActiveOperationOutput)
def put_active_operation(
    payload: ActiveOperationInput, session: Session = Depends(get_session)
) -> ActiveOperationOutput:
    now = datetime.now(UTC)
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
    session.refresh(record)
    result = ActiveOperationOutput.model_validate(record, from_attributes=True)
    event_bus.publish(
        "operation.progressed" if payload.manual_progress else "operation.changed",
        result.model_dump(mode="json"),
    )
    return result


@router.delete("/operations/active", status_code=status.HTTP_204_NO_CONTENT)
def delete_active_operation(session: Session = Depends(get_session)) -> Response:
    record = session.get(ActiveOperation, 1)
    if record:
        session.delete(record)
        session.commit()
    event_bus.publish("operation.changed", None)
    return Response(status_code=204)


def _elite_settings(session: Session) -> tuple[dict, Path]:
    preferences = _load_preferences(session)
    values = preferences.model_dump()
    configured = preferences.elite_journal_directory.strip()
    directory = Path(configured).expanduser().resolve() if configured else default_journal_directory()
    return values, directory


@router.get("/elite/status")
def elite_status(session: Session = Depends(get_session)) -> dict:
    values, directory = _elite_settings(session)
    state = EliteDataReader(directory).read()
    imported = 0
    if values["elite_enabled"] and state.available:
        try:
            imported = sync_current_market(session, directory, state)
        except Exception as exc:
            session.rollback()
            state.warnings.append(f"Current market could not be synchronized: {exc}")
    return {
        "enabled": bool(values["elite_enabled"]),
        "auto_apply_planning_state": bool(values["elite_auto_apply_planning_state"]),
        "configured_directory": str(directory),
        "reference_directory": (
            str((Path.cwd() / "referenceData").resolve())
            if (Path.cwd() / "referenceData").is_dir()
            else None
        ),
        "market_records_updated": imported,
        "state": state.to_dict(),
    }


@router.put("/elite/settings")
def put_elite_settings(payload: EliteSettingsInput, session: Session = Depends(get_session)) -> dict:
    current = _load_preferences(session)
    directory = payload.journal_directory.strip()
    if payload.enabled and directory and not Path(directory).expanduser().is_dir():
        raise HTTPException(400, "The selected Elite journal directory does not exist.")
    current.elite_enabled = payload.enabled
    current.elite_journal_directory = directory
    current.elite_auto_apply_planning_state = payload.auto_apply_planning_state
    _save_preferences(session, current)
    event_bus.publish("elite.connected" if payload.enabled else "elite.disconnected", {})
    return elite_status(session)


ASSUMPTIONS = [
    "Jump counts use 85% of laden range as a conservative routing factor.",
    "Travel times are estimates; exact star-by-star routing remains in-game.",
    "Market prices are community observations, not guaranteed live prices.",
]


@router.post("/trades/search", response_model=TradeSearchResponse)
async def trades(payload: TradeSearchRequest, session: Session = Depends(get_session)) -> TradeSearchResponse:
    online_note = await _hydrate_online(session, payload)
    return TradeSearchResponse(
        routes=find_trades(session, payload),
        available_credits=payload.state.available_credits,
        assumptions=ASSUMPTIONS + ([online_note] if online_note else []),
    )


@router.post("/round-trips/search", response_model=RoundTripResponse)
async def round_trips(payload: TradeSearchRequest, session: Session = Depends(get_session)) -> RoundTripResponse:
    online_note = await _hydrate_online(session, payload)
    return RoundTripResponse(
        routes=find_round_trips(session, payload),
        available_credits=payload.state.available_credits,
        assumptions=ASSUMPTIONS + ([online_note] if online_note else []),
    )


@router.post("/trade-routes/search", response_model=ImmersiveTradeRouteResponse)
async def immersive_trade_routes(
    payload: TradeSearchRequest, session: Session = Depends(get_session)
) -> ImmersiveTradeRouteResponse:
    online_note = await _hydrate_online(session, payload)
    return ImmersiveTradeRouteResponse(
        routes=find_immersive_trade_routes(session, payload),
        assumptions=ASSUMPTIONS + [
            "Trade Routes favor continuous hauling, route length, commodity variety, and confidence over maximum profit."
        ] + ([online_note] if online_note else []),
    )


@router.post("/data/regions/cache")
async def cache_region(
    payload: TradeSearchRequest, session: Session = Depends(get_session)
) -> dict:
    imported = await SpanshRemoteProvider(get_settings()).hydrate_trade_candidates(
        session,
        origin_id64=payload.state.origin_system_id64,
        cargo_capacity=payload.state.ship.cargo_capacity,
        min_supply_multiplier=payload.filters.min_supply_multiplier,
        max_distance_ly=payload.max_system_distance_ly,
    )
    return {
        "imported": imported,
        "radius_ly": payload.max_system_distance_ly,
        "system_id64": payload.state.origin_system_id64,
    }


async def _hydrate_online(
    session: Session, payload: TradeSearchRequest, *, force: bool = False
) -> str | None:
    import_running = session.scalar(
        select(func.count())
        .select_from(Job)
        .where(Job.kind == "spansh_import", Job.status.in_(("queued", "running")))
    )
    if import_running:
        return "The local data pack is being updated; this search uses the current cache."

    latest = session.scalar(
        select(func.max(MarketObservation.observed_at))
        .join(Station)
        .where(Station.system_id64 == payload.state.origin_system_id64)
    )
    should_refresh = force or latest is None
    if latest is not None:
        latest_aware = latest if latest.tzinfo else latest.replace(tzinfo=UTC)
        should_refresh = force or (datetime.now(UTC) - latest_aware).total_seconds() > 600
    if not should_refresh:
        return None
    try:
        imported = await SpanshRemoteProvider(get_settings()).hydrate_trade_candidates(
            session,
            origin_id64=payload.state.origin_system_id64,
            cargo_capacity=payload.state.ship.cargo_capacity,
            min_supply_multiplier=payload.filters.min_supply_multiplier,
            max_distance_ly=payload.max_system_distance_ly,
        )
        return f"Refreshed {imported} nearby Spansh market candidates."
    except Exception as exc:
        # A failed flush leaves SQLAlchemy's transaction in a rollback-only
        # state. Reset it before checking whether cached data can be used.
        session.rollback()
        local_count = session.scalar(select(func.count()).select_from(MarketObservation)) or 0
        if local_count == 0:
            raise HTTPException(
                503,
                f"Live Spansh data could not be loaded and no local market cache is available: {exc}",
            ) from exc
        return "Live Spansh refresh was unavailable; results use the local cache."


@router.post("/transit/plans", status_code=status.HTTP_202_ACCEPTED)
async def transit(payload: TransitRequest, session: Session = Depends(get_session)) -> dict:
    discovery = TradeSearchRequest(
        state=payload.state,
        filters=payload.filters,
        max_results=50,
        max_system_distance_ly=min(
            1000,
            payload.max_leg_jumps * 0.85 * payload.state.ship.laden_jump_range,
        ),
    )
    await _hydrate_online(session, discovery, force=True)
    return {"job_id": start_transit_job(payload), "status": "queued"}


@router.get("/jobs/{job_id}")
def job(job_id: str, session: Session = Depends(get_session)) -> dict:
    record = session.get(Job, job_id)
    if record is None:
        raise HTTPException(404, "Job not found")
    return {
        "id": record.id,
        "kind": record.kind,
        "status": record.status,
        "progress": record.progress,
        "result": record.result,
        "error": record.error,
    }


class ImportRequest(BaseModel):
    path: str | None = None
    download: bool = False


@router.post("/data/spansh-imports", status_code=status.HTTP_202_ACCEPTED)
def import_spansh(payload: ImportRequest) -> dict:
    path = Path(payload.path) if payload.path else get_settings().data_dir / "galaxy_stations.json.gz"
    path = path.resolve()
    allowed_root = get_settings().data_dir.resolve()
    if allowed_root not in path.parents and path != allowed_root:
        raise HTTPException(400, "Import file must be inside the ION data directory")
    if not path.exists() and not payload.download:
        raise HTTPException(404, f"Data pack not found at {path}")
    return {"job_id": start_import_job(path, download=payload.download), "status": "queued"}


@router.delete("/data/spansh-pack", status_code=status.HTTP_204_NO_CONTENT)
def delete_pack() -> Response:
    path = (get_settings().data_dir / "galaxy_stations.json.gz").resolve()
    if path.exists():
        path.unlink()
    return Response(status_code=204)
