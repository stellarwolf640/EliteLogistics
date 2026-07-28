from datetime import UTC, datetime, timedelta

from elite_logistics.engine import confidence, find_immersive_trade_routes, find_round_trips, find_trades, jump_count, plan_transit, supercruise_seconds
from elite_logistics.schemas import (
    PlayerState,
    SearchFilters,
    ShipConstraints,
    TradeSearchRequest,
    TransitRequest,
)


def state() -> PlayerState:
    return PlayerState(
        origin_system_id64=1,
        origin_station_market_id=101,
        ship=ShipConstraints(cargo_capacity=100, laden_jump_range=20, pad_size="M"),
        credits=5_000_000,
        rebuy_reserve=500_000,
        cash_reserve=250_000,
    )


def filters() -> SearchFilters:
    return SearchFilters(max_market_age_hours=24, max_station_distance_ls=2000)


def test_jump_and_supercruise_model_are_conservative():
    assert jump_count(0, 20) == 0
    assert jump_count(20, 20) == 2
    assert 60 <= supercruise_seconds(100) <= 900
    assert supercruise_seconds(10_000) > supercruise_seconds(100)


def test_confidence_boundaries():
    now = datetime.now(UTC)
    score, rating = confidence(
        observed_at=now - timedelta(minutes=5),
        arrival_seconds=300,
        max_age_hours=4,
        supply=1000,
        demand=1000,
        quantity=100,
        fleet_carrier=False,
        now=now,
    )
    assert score >= 75
    assert rating == "High"
    low_score, low_rating = confidence(
        observed_at=now - timedelta(hours=3, minutes=50),
        arrival_seconds=1200,
        max_age_hours=4,
        supply=100,
        demand=100,
        quantity=100,
        fleet_carrier=True,
        now=now,
    )
    assert low_score < 45
    assert low_rating == "Low"


def test_trade_search_uses_current_location_as_radius_center(session):
    request = TradeSearchRequest(
        state=state(),
        filters=filters(),
        max_system_distance_ly=80,
    )
    routes = find_trades(session, request)
    assert routes
    best = routes[0]
    assert best.quantity == 100
    gold = next(route for route in routes if route.commodity == "Gold")
    assert gold.trip_profit == 1_600_000
    assert gold.distance_to_route_ly == 20
    assert gold.relocation_seconds > 0
    assert request.state.available_credits == 4_250_000


def test_round_trip_recalculates_balance(session):
    request = TradeSearchRequest(
        state=state(),
        filters=filters(),
        max_system_distance_ly=80,
    )
    routes = find_round_trips(session, request)
    assert routes
    best = routes[0]
    assert best.outbound.commodity == "Silver"
    assert best.return_leg.commodity == "Consumer Technology"
    assert best.total_profit > best.outbound.trip_profit


def test_immersive_trade_route_builds_a_continuous_manifest(session):
    request = TradeSearchRequest(
        state=state(),
        filters=filters(),
        max_system_distance_ly=80,
    )
    routes = find_immersive_trade_routes(session, request)
    assert routes
    assert len(routes[0].legs) >= 2
    for previous, current in zip(routes[0].legs, routes[0].legs[1:]):
        assert previous.destination_market_id == current.source_market_id


def test_profitable_transit_stays_inside_detour(session):
    request = TransitRequest(
        state=state(),
        destination_system_id64=4,
        destination_station_market_id=104,
        filters=filters(),
        detour_limit=0.2,
        max_trade_stops=4,
        max_leg_jumps=2,
    )
    result = plan_transit(session, request)
    assert result.direct.total_distance_ly == 60
    assert result.options
    assert {option.profile for option in result.options} == {"Fast", "Balanced", "Profit"}
    assert all(option.total_distance_ly <= 72.01 for option in result.options)
    assert all(option.expected_profit > 0 for option in result.options)
