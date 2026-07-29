from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, HttpUrl
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .config import get_settings
from .database import (
    DataImport,
    Job,
    MarketObservation,
    Preference,
    ShipProfile,
    Station,
    System,
    get_session,
)
from .engine import find_immersive_trade_routes, find_round_trips, find_trades
from .elite_adapter import read_elite_state
from .jobs import start_import_job, start_transit_job
from .providers import SpanshRemoteProvider
from .schemas import (
    EliteGameState,
    LocationResult,
    ImmersiveTradeRouteResponse,
    RoundTripResponse,
    ShipProfileInput,
    ShipProfileOutput,
    TradeSearchRequest,
    TradeSearchResponse,
    TransitRequest,
)

router = APIRouter(prefix="/api")
DEFAULT_PREFERENCES = {
    "max_market_age_hours": 4,
    "max_station_distance_ls": 2000,
    "min_supply_multiplier": 2,
    "min_demand_multiplier": 2,
    "include_fleet_carriers": False,
    "include_planetary": False,
    "include_odyssey": False,
    "include_permit_systems": False,
    "include_restricted": False,
    "hide_low_confidence": True,
    "detour_limit": 0.2,
}


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "version": "0.1.0"}


@router.get("/elite/state", response_model=EliteGameState)
def elite_state() -> EliteGameState:
    settings = get_settings()
    return read_elite_state(settings.elite_journal_dir)


@router.get("/data/status")
def data_status(session: Session = Depends(get_session)) -> dict:
    latest = session.scalar(select(func.max(MarketObservation.observed_at)))
    pack_path = get_settings().data_dir / "galaxy_stations.json.gz"
    partial_pack_path = pack_path.with_suffix(pack_path.suffix + ".part")
    database_path = get_settings().data_dir / "elite-logistics.db"
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


@router.get("/preferences")
def get_preferences(session: Session = Depends(get_session)) -> dict:
    record = session.get(Preference, 1)
    return record.values if record else DEFAULT_PREFERENCES


@router.put("/preferences")
def put_preferences(values: dict, session: Session = Depends(get_session)) -> dict:
    merged = {**DEFAULT_PREFERENCES, **values}
    record = session.get(Preference, 1)
    if record is None:
        record = Preference(id=1, schema_version=1, values=merged)
        session.add(record)
    else:
        record.values = merged
    session.commit()
    return merged


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
        raise HTTPException(400, "Import file must be inside the Elite Logistics data directory")
    if not path.exists() and not payload.download:
        raise HTTPException(404, f"Data pack not found at {path}")
    return {"job_id": start_import_job(path, download=payload.download), "status": "queued"}


@router.delete("/data/spansh-pack", status_code=status.HTTP_204_NO_CONTENT)
def delete_pack() -> Response:
    path = (get_settings().data_dir / "galaxy_stations.json.gz").resolve()
    if path.exists():
        path.unlink()
    return Response(status_code=204)
