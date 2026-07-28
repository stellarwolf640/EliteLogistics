from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from .database import MarketObservation, Station, System
from .schemas import (
    PlayerState,
    RoundTrip,
    SearchFilters,
    TradeLeg,
    TradeSearchRequest,
    TransitRequest,
    TransitResult,
    TransitSummary,
    ImmersiveTradeRoute,
)

PAD_RANK = {"S": 0, "M": 1, "L": 2}
CONFIDENCE_RANK = {"Low": 0, "Medium": 1, "High": 2}


def distance(a: System, b: System) -> float:
    return math.dist((a.x, a.y, a.z), (b.x, b.y, b.z))


def jump_count(system_distance: float, laden_range: float) -> int:
    if system_distance <= 0:
        return 0
    return max(1, math.ceil(system_distance / (0.85 * laden_range)))


def supercruise_seconds(distance_ls: float) -> int:
    estimate = 75 + 20 * math.log2(max(1.0, distance_ls) / 100)
    return round(min(900, max(60, estimate)))


def leg_seconds(system_distance: float, laden_range: float, station_distance_ls: float, planetary: bool) -> int:
    return (
        60
        + jump_count(system_distance, laden_range) * 55
        + supercruise_seconds(station_distance_ls)
        + 90
        + (180 if planetary else 0)
    )


def confidence(
    *,
    observed_at: datetime,
    arrival_seconds: int,
    max_age_hours: float,
    supply: int,
    demand: int,
    quantity: int,
    fleet_carrier: bool,
    now: datetime | None = None,
) -> tuple[int, str]:
    now = now or datetime.now(UTC)
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=UTC)
    age_hours = max(0.0, (now - observed_at).total_seconds() / 3600 + arrival_seconds / 3600)
    freshness = max(0.0, 1 - age_hours / max_age_hours) * 50
    target = max(1, quantity * 2)
    supply_points = min(1, supply / target) * 25
    demand_points = min(1, demand / target) * 25
    score = round(max(0, freshness + supply_points + demand_points - (15 if fleet_carrier else 0)))
    rating = "High" if score >= 75 else "Medium" if score >= 45 else "Low"
    return score, rating


def station_allowed(station: Station, system: System, state: PlayerState, filters: SearchFilters) -> bool:
    if PAD_RANK[station.largest_pad] < PAD_RANK[state.ship.pad_size]:
        return False
    if station.distance_to_arrival_ls > filters.max_station_distance_ls:
        return False
    if station.fleet_carrier and not filters.include_fleet_carriers:
        return False
    if station.planetary and not filters.include_planetary:
        return False
    if station.odyssey and not filters.include_odyssey:
        return False
    if station.restricted and not filters.include_restricted:
        return False
    if system.permit_required and not filters.include_permit_systems:
        return False
    return True


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def build_trade_leg(
    source: MarketObservation,
    destination: MarketObservation,
    state: PlayerState,
    filters: SearchFilters,
    *,
    credits: int | None = None,
    now: datetime | None = None,
) -> TradeLeg | None:
    credits = state.available_credits if credits is None else credits
    if source.buy_price <= 0 or destination.sell_price <= source.buy_price:
        return None
    src_station, dst_station = source.station, destination.station
    src_system, dst_system = src_station.system, dst_station.system
    if not station_allowed(src_station, src_system, state, filters):
        return None
    if not station_allowed(dst_station, dst_system, state, filters):
        return None
    quantity = min(
        state.ship.cargo_capacity,
        source.supply,
        destination.demand,
        credits // source.buy_price,
    )
    if quantity <= 0:
        return None
    if source.supply < quantity * filters.min_supply_multiplier:
        return None
    if destination.demand < quantity * filters.min_demand_multiplier:
        return None
    now = now or datetime.now(UTC)
    if (now - _aware(source.observed_at)).total_seconds() > filters.max_market_age_hours * 3600:
        return None
    if (now - _aware(destination.observed_at)).total_seconds() > filters.max_market_age_hours * 3600:
        return None
    system_distance = distance(src_system, dst_system)
    seconds = leg_seconds(
        system_distance,
        state.ship.laden_jump_range,
        dst_station.distance_to_arrival_ls,
        dst_station.planetary,
    )
    score, rating = confidence(
        observed_at=min(_aware(source.observed_at), _aware(destination.observed_at)),
        arrival_seconds=seconds,
        max_age_hours=filters.max_market_age_hours,
        supply=source.supply,
        demand=destination.demand,
        quantity=quantity,
        fleet_carrier=src_station.fleet_carrier or dst_station.fleet_carrier,
        now=now,
    )
    if filters.hide_low_confidence and rating == "Low":
        return None
    per_ton = destination.sell_price - source.buy_price
    profit = per_ton * quantity
    warnings: list[str] = []
    if rating != "High":
        warnings.append(f"{rating} market confidence")
    if src_station.fleet_carrier or dst_station.fleet_carrier:
        warnings.append("Fleet carrier market")
    return TradeLeg(
        source_market_id=src_station.market_id,
        source_station=src_station.name,
        source_system_id64=src_system.id64,
        source_system=src_system.name,
        destination_market_id=dst_station.market_id,
        destination_station=dst_station.name,
        destination_system_id64=dst_system.id64,
        destination_system=dst_system.name,
        commodity_id=source.commodity_id,
        commodity=source.commodity.display_name,
        buy_price=source.buy_price,
        sell_price=destination.sell_price,
        quantity=quantity,
        profit_per_ton=per_ton,
        trip_profit=profit,
        system_distance_ly=round(system_distance, 2),
        jumps=jump_count(system_distance, state.ship.laden_jump_range),
        estimated_seconds=seconds,
        credits_per_hour=round(profit / seconds * 3600, 2),
        first_trip_credits_per_hour=round(profit / seconds * 3600, 2),
        confidence_score=score,
        confidence=rating,
        source_observed_at=source.observed_at,
        destination_observed_at=destination.observed_at,
        provider=source.provider if source.provider == destination.provider else f"{source.provider}+{destination.provider}",
        warnings=warnings,
    )


def _sort_key(leg: TradeLeg, mode: str) -> float:
    if mode == "trip_profit":
        return leg.trip_profit
    if mode == "profit_per_ton":
        return leg.profit_per_ton
    if mode == "profit_per_jump":
        return leg.trip_profit / max(1, leg.jumps)
    if mode == "credits_per_hour":
        return leg.credits_per_hour
    if mode == "convenience":
        return -(leg.estimated_seconds + leg.relocation_seconds + leg.jumps * 30)
    return leg.first_trip_credits_per_hour * (0.5 + leg.confidence_score / 200)


def load_observations(
    session: Session,
    *,
    market_ids: Iterable[int] | None = None,
    commodity_ids: Iterable[int] | None = None,
) -> list[MarketObservation]:
    statement = select(MarketObservation).options(
        joinedload(MarketObservation.station).joinedload(Station.system),
        joinedload(MarketObservation.commodity),
    )
    if market_ids is not None:
        ids = list(market_ids)
        if not ids:
            return []
        statement = statement.where(MarketObservation.market_id.in_(ids))
    if commodity_ids is not None:
        ids = list(commodity_ids)
        if not ids:
            return []
        statement = statement.where(MarketObservation.commodity_id.in_(ids))
    return list(session.scalars(statement).all())


def find_trades(session: Session, request: TradeSearchRequest) -> list[TradeLeg]:
    origin = session.get(System, request.state.origin_system_id64)
    if origin is None:
        return []
    radius = request.max_system_distance_ly
    candidate_stations = list(
        session.scalars(
            select(Station)
            .join(System)
            .where(
                System.x.between(origin.x - radius, origin.x + radius),
                System.y.between(origin.y - radius, origin.y + radius),
                System.z.between(origin.z - radius, origin.z + radius),
            )
            .options(joinedload(Station.system))
        ).all()
    )
    candidate_stations = [
        station for station in candidate_stations if distance(origin, station.system) <= radius
    ]
    candidate_market_ids = [station.market_id for station in candidate_stations]
    observations = load_observations(session, market_ids=candidate_market_ids)
    sources = [item for item in observations if item.buy_price > 0 and item.supply > 0]
    by_commodity: dict[int, list[MarketObservation]] = {}
    for item in observations:
        by_commodity.setdefault(item.commodity_id, []).append(item)
    routes: list[TradeLeg] = []
    for source in sources:
        for destination in by_commodity.get(source.commodity_id, []):
            if destination.market_id == source.market_id:
                continue
            leg = build_trade_leg(source, destination, request.state, request.filters)
            if leg:
                to_route = distance(origin, source.station.system)
                same_market = request.state.origin_station_market_id == source.market_id
                relocation_seconds = 0 if same_market else leg_seconds(
                    to_route,
                    request.state.ship.laden_jump_range,
                    source.station.distance_to_arrival_ls,
                    source.station.planetary,
                )
                first_trip_seconds = relocation_seconds + leg.estimated_seconds
                leg = leg.model_copy(
                    update={
                        "distance_to_route_ly": round(to_route, 2),
                        "relocation_jumps": jump_count(to_route, request.state.ship.laden_jump_range),
                        "relocation_seconds": relocation_seconds,
                        "first_trip_credits_per_hour": round(
                            leg.trip_profit / first_trip_seconds * 3600, 2
                        ),
                    }
                )
                routes.append(leg)
    routes.sort(key=lambda leg: _sort_key(leg, request.sort), reverse=True)
    return routes[: request.max_results]


def find_round_trips(session: Session, request: TradeSearchRequest) -> list[RoundTrip]:
    outbound = find_trades(session, request)
    relevant_markets = {
        market_id
        for item in outbound
        for market_id in (item.source_market_id, item.destination_market_id)
    }
    observations = load_observations(session, market_ids=relevant_markets)
    results: list[RoundTrip] = []
    for first in outbound:
        return_sources = [o for o in observations if o.market_id == first.destination_market_id]
        return_destinations = [o for o in observations if o.market_id == first.source_market_id]
        best: TradeLeg | None = None
        for source in return_sources:
            for destination in return_destinations:
                if source.commodity_id != destination.commodity_id:
                    continue
                leg = build_trade_leg(
                    source,
                    destination,
                    request.state,
                    request.filters,
                    credits=request.state.available_credits + first.trip_profit,
                )
                if leg and (best is None or leg.trip_profit > best.trip_profit):
                    best = leg
        if best:
            total_profit = first.trip_profit + best.trip_profit
            seconds = first.relocation_seconds + first.estimated_seconds + best.estimated_seconds
            rating = min((first.confidence, best.confidence), key=lambda value: CONFIDENCE_RANK[value])
            results.append(
                RoundTrip(
                    outbound=first,
                    return_leg=best,
                    total_profit=total_profit,
                    estimated_seconds=seconds,
                    relocation_seconds=first.relocation_seconds,
                    credits_per_hour=round(total_profit / seconds * 3600, 2),
                    confidence=rating,
                )
            )
    results.sort(key=lambda item: item.credits_per_hour, reverse=True)
    return results[: request.max_results]


def find_immersive_trade_routes(session: Session, request: TradeSearchRequest) -> list[ImmersiveTradeRoute]:
    """Build varied multi-stop hauling circuits where continuity matters more than peak profit."""
    candidates = find_trades(session, request)
    if not candidates:
        return []
    by_source: dict[int, list[TradeLeg]] = {}
    for leg in candidates:
        by_source.setdefault(leg.source_market_id, []).append(leg)
    plans: list[ImmersiveTradeRoute] = []
    for seed in candidates[:20]:
        legs = [seed]
        visited = {seed.source_market_id, seed.destination_market_id}
        commodities = {seed.commodity_id}
        current_market = seed.destination_market_id
        credits = request.state.available_credits + seed.trip_profit
        for _ in range(5):
            options: list[TradeLeg] = []
            source_observations = load_observations(session, market_ids=[current_market])
            if not source_observations:
                break
            candidate_markets = {
                leg.destination_market_id
                for leg in candidates
                if leg.destination_market_id not in visited
            }
            targets = load_observations(session, market_ids=candidate_markets)
            targets_by_commodity: dict[int, list[MarketObservation]] = {}
            for target in targets:
                targets_by_commodity.setdefault(target.commodity_id, []).append(target)
            for source in source_observations:
                for target in targets_by_commodity.get(source.commodity_id, []):
                    leg = build_trade_leg(
                        source, target, request.state, request.filters, credits=credits
                    )
                    if leg:
                        options.append(leg)
            if not options:
                break
            options.sort(
                key=lambda leg: (
                    1 if leg.commodity_id not in commodities else 0,
                    leg.confidence_score,
                    leg.system_distance_ly,
                    math.log1p(leg.trip_profit),
                ),
                reverse=True,
            )
            chosen = options[0]
            legs.append(chosen)
            visited.add(chosen.destination_market_id)
            commodities.add(chosen.commodity_id)
            current_market = chosen.destination_market_id
            credits += chosen.trip_profit
        if len(legs) < 2:
            continue
        confidence_score = min(leg.confidence_score for leg in legs)
        plans.append(
            ImmersiveTradeRoute(
                name=f"{legs[0].source_system} Cargo Circuit",
                legs=legs,
                total_profit=sum(leg.trip_profit for leg in legs),
                total_distance_ly=round(sum(leg.system_distance_ly for leg in legs), 2),
                estimated_jumps=sum(leg.jumps for leg in legs),
                estimated_seconds=sum(leg.estimated_seconds for leg in legs),
                confidence="High" if confidence_score >= 75 else "Medium" if confidence_score >= 45 else "Low",
                cargo_variety=len(commodities),
            )
        )
    unique: dict[tuple[int, ...], ImmersiveTradeRoute] = {}
    for plan in plans:
        key = tuple(leg.destination_market_id for leg in plan.legs)
        unique.setdefault(key, plan)
    return sorted(
        unique.values(),
        key=lambda plan: (len(plan.legs), plan.cargo_variety, plan.confidence, plan.total_distance_ly),
        reverse=True,
    )[:6]


@dataclass
class TransitState:
    market_id: int
    system: System
    credits: int
    elapsed: int
    travelled: float
    profit: int
    legs: list[TradeLeg]
    visited: frozenset[int]
    confidence_score: int
    positioning_station: str | None = None
    positioning_system: str | None = None


PROFILE_WEIGHTS = {
    "Fast": (0.15, 0.35, 0.35, 0.10, 0.05),
    "Balanced": (0.30, 0.25, 0.25, 0.15, 0.05),
    "Profit": (0.45, 0.15, 0.15, 0.15, 0.10),
}


def _normalize(value: float, upper: float) -> float:
    return max(0.0, min(1.0, value / max(upper, 1e-9)))


def _state_score(state: TransitState, direct: float, destination: System, profile: str) -> float:
    profit_w, progress_w, time_w, risk_w, detour_w = PROFILE_WEIGHTS[profile]
    remaining = distance(state.system, destination)
    progress = max(0, direct - remaining)
    detour = max(0, state.travelled + remaining - direct)
    return (
        profit_w * _normalize(math.log1p(state.profit), math.log1p(20_000_000))
        + progress_w * _normalize(progress, direct)
        + time_w * (1 - _normalize(state.elapsed, 7200))
        + risk_w * _normalize(state.confidence_score, 100)
        + detour_w * (1 - _normalize(detour, direct))
    )


def plan_transit(session: Session, request: TransitRequest) -> TransitResult:
    origin = session.get(System, request.state.origin_system_id64)
    destination = session.get(System, request.destination_system_id64)
    if origin is None or destination is None:
        raise ValueError("Origin or destination system is not in the local dataset")
    direct_distance = distance(origin, destination)
    direct_jumps = jump_count(direct_distance, request.state.ship.laden_jump_range)
    destination_station = session.get(Station, request.destination_station_market_id) if request.destination_station_market_id else None
    direct_seconds = (
        direct_jumps * 55
        + 60
        + (supercruise_seconds(destination_station.distance_to_arrival_ls) + 90 if destination_station else 0)
        + (180 if destination_station and destination_station.planetary else 0)
    )
    direct_summary = TransitSummary(
        profile="Direct",
        legs=[],
        total_distance_ly=round(direct_distance, 2),
        estimated_jumps=direct_jumps,
        estimated_seconds=direct_seconds,
        expected_profit=0,
        extra_seconds_vs_direct=0,
        extra_distance_vs_direct=0,
        confidence="High",
        warnings=["Exact star-by-star path is plotted in-game."],
    )
    exact_start_markets = [
        station.market_id
        for station in origin.stations
        if request.state.origin_station_market_id is None or station.market_id == request.state.origin_station_market_id
    ]
    max_path = direct_distance * (1 + request.detour_limit)
    max_leg_distance = request.max_leg_jumps * 0.85 * request.state.ship.laden_jump_range
    margin = direct_distance * request.detour_limit + request.max_leg_jumps * request.state.ship.laden_jump_range
    candidate_query = (
        select(Station)
        .join(System)
        .options(joinedload(Station.system))
        .where(
            System.x.between(min(origin.x, destination.x) - margin, max(origin.x, destination.x) + margin),
            System.y.between(min(origin.y, destination.y) - margin, max(origin.y, destination.y) + margin),
            System.z.between(min(origin.z, destination.z) - margin, max(origin.z, destination.z) + margin),
        )
    )
    candidate_stations = [
        station
        for station in session.scalars(candidate_query).all()
        if distance(origin, station.system) + distance(station.system, destination) <= max_path + 1e-6
        and station_allowed(station, station.system, request.state, request.filters)
    ]
    observations = load_observations(
        session,
        market_ids={station.market_id for station in candidate_stations} | set(exact_start_markets),
    )
    by_market: dict[int, list[MarketObservation]] = {}
    for item in observations:
        by_market.setdefault(item.market_id, []).append(item)
    best_options: list[TransitSummary] = []
    for profile in PROFILE_WEIGHTS:
        beam = [
            TransitState(
                market_id=market_id,
                system=origin,
                credits=request.state.available_credits,
                elapsed=0,
                travelled=0,
                profit=0,
                legs=[],
                visited=frozenset({market_id}),
                confidence_score=100,
            )
            for market_id in exact_start_markets
        ]
        nearby_starts = sorted(
            (
                station
                for station in candidate_stations
                if station.market_id not in exact_start_markets
                and distance(origin, station.system) <= max_leg_distance
                and by_market.get(station.market_id)
            ),
            key=lambda station: distance(origin, station.system),
        )[:20]
        beam.extend(
            [
                TransitState(
                    market_id=station.market_id,
                    system=station.system,
                    credits=request.state.available_credits,
                    elapsed=leg_seconds(
                        distance(origin, station.system),
                        request.state.ship.laden_jump_range,
                        station.distance_to_arrival_ls,
                        station.planetary,
                    ),
                    travelled=distance(origin, station.system),
                    profit=0,
                    legs=[],
                    visited=frozenset({station.market_id}),
                    confidence_score=100,
                    positioning_station=station.name,
                    positioning_system=station.system.name,
                )
                for station in nearby_starts
            ]
        )
        if not beam:
            continue
        completed: list[TransitState] = []
        for _ in range(request.max_trade_stops):
            expanded: list[TransitState] = []
            for state in beam:
                sources = by_market.get(state.market_id, [])
                outgoing: list[tuple[float, TransitState]] = []
                for station in candidate_stations:
                    if station.market_id in state.visited:
                        continue
                    leg_distance = distance(state.system, station.system)
                    if leg_distance <= 0 or leg_distance > max_leg_distance:
                        continue
                    if state.travelled + leg_distance + distance(station.system, destination) > max_path + 1e-6:
                        continue
                    for source in sources:
                        for target in by_market.get(station.market_id, []):
                            if source.commodity_id != target.commodity_id:
                                continue
                            leg = build_trade_leg(
                                source,
                                target,
                                request.state,
                                request.filters,
                                credits=state.credits,
                            )
                            if leg is None:
                                continue
                            next_state = TransitState(
                                market_id=station.market_id,
                                system=station.system,
                                credits=state.credits + leg.trip_profit,
                                elapsed=state.elapsed + leg.estimated_seconds,
                                travelled=state.travelled + leg.system_distance_ly,
                                profit=state.profit + leg.trip_profit,
                                legs=state.legs + [leg],
                                visited=state.visited | {station.market_id},
                                confidence_score=min(state.confidence_score, leg.confidence_score),
                                positioning_station=state.positioning_station,
                                positioning_system=state.positioning_system,
                            )
                            outgoing.append((_state_score(next_state, direct_distance, destination, profile), next_state))
                outgoing.sort(key=lambda pair: pair[0], reverse=True)
                expanded.extend(state for _, state in outgoing[:20])
            if not expanded:
                break
            expanded.sort(key=lambda item: _state_score(item, direct_distance, destination, profile), reverse=True)
            beam = expanded[:40]
            completed.extend(beam)
        if not completed:
            continue
        best = max(completed, key=lambda item: _state_score(item, direct_distance, destination, profile))
        final_distance = distance(best.system, destination)
        final_jumps = jump_count(final_distance, request.state.ship.laden_jump_range)
        final_seconds = 60 + final_jumps * 55
        if destination_station:
            final_seconds += supercruise_seconds(destination_station.distance_to_arrival_ls) + 90
            if destination_station.planetary:
                final_seconds += 180
        total_seconds = best.elapsed + final_seconds
        total_distance = best.travelled + final_distance
        rating = "High" if best.confidence_score >= 75 else "Medium" if best.confidence_score >= 45 else "Low"
        best_options.append(
            TransitSummary(
                profile=profile,
                legs=best.legs,
                total_distance_ly=round(total_distance, 2),
                estimated_jumps=sum(leg.jumps for leg in best.legs) + final_jumps,
                estimated_seconds=total_seconds,
                expected_profit=best.profit,
                extra_seconds_vs_direct=max(0, total_seconds - direct_seconds),
                extra_distance_vs_direct=round(max(0, total_distance - direct_distance), 2),
                confidence=rating,
                positioning_station=best.positioning_station,
                positioning_system=best.positioning_system,
                warnings=["Exact star-by-star path is plotted in-game."],
            )
        )
    return TransitResult(direct=direct_summary, options=best_options[:3])
