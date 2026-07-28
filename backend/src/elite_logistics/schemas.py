from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


PadSize = Literal["S", "M", "L"]
SortMode = Literal["recommended", "trip_profit", "profit_per_ton", "profit_per_jump", "credits_per_hour", "convenience"]


class ShipConstraints(BaseModel):
    cargo_capacity: int = Field(gt=0, le=2000)
    laden_jump_range: float = Field(gt=0, le=500)
    pad_size: PadSize = "M"


class SearchFilters(BaseModel):
    max_market_age_hours: float = Field(default=4, gt=0, le=720)
    max_station_distance_ls: float = Field(default=2000, ge=0)
    min_supply_multiplier: float = Field(default=2, ge=0)
    min_demand_multiplier: float = Field(default=2, ge=0)
    include_fleet_carriers: bool = False
    include_planetary: bool = False
    include_odyssey: bool = False
    include_permit_systems: bool = False
    include_restricted: bool = False
    hide_low_confidence: bool = True


class PlayerState(BaseModel):
    origin_system_id64: int
    origin_station_market_id: int | None = None
    ship: ShipConstraints
    credits: int = Field(ge=0)
    rebuy_reserve: int = Field(default=0, ge=0)
    cash_reserve: int = Field(default=0, ge=0)

    @property
    def available_credits(self) -> int:
        return max(0, self.credits - self.rebuy_reserve - self.cash_reserve)


class TradeSearchRequest(BaseModel):
    state: PlayerState
    filters: SearchFilters = Field(default_factory=SearchFilters)
    sort: SortMode = "recommended"
    max_results: int = Field(default=50, ge=1, le=200)
    max_system_distance_ly: float = Field(default=100, gt=0, le=1000)


class TradeLeg(BaseModel):
    source_market_id: int
    source_station: str
    source_system_id64: int
    source_system: str
    destination_market_id: int
    destination_station: str
    destination_system_id64: int
    destination_system: str
    commodity_id: int
    commodity: str
    buy_price: int
    sell_price: int
    quantity: int
    profit_per_ton: int
    trip_profit: int
    system_distance_ly: float
    jumps: int
    estimated_seconds: int
    credits_per_hour: float
    distance_to_route_ly: float = 0
    relocation_jumps: int = 0
    relocation_seconds: int = 0
    first_trip_credits_per_hour: float = 0
    confidence_score: int
    confidence: Literal["High", "Medium", "Low"]
    source_observed_at: datetime
    destination_observed_at: datetime
    provider: str
    warnings: list[str] = Field(default_factory=list)


class TradeSearchResponse(BaseModel):
    routes: list[TradeLeg]
    available_credits: int
    assumptions: list[str]


class RoundTrip(BaseModel):
    outbound: TradeLeg
    return_leg: TradeLeg
    total_profit: int
    estimated_seconds: int
    relocation_seconds: int = 0
    credits_per_hour: float
    confidence: Literal["High", "Medium", "Low"]


class RoundTripResponse(BaseModel):
    routes: list[RoundTrip]
    available_credits: int
    assumptions: list[str]


class TransitRequest(BaseModel):
    state: PlayerState
    destination_system_id64: int
    destination_station_market_id: int | None = None
    filters: SearchFilters = Field(default_factory=SearchFilters)
    detour_limit: float = Field(default=0.2, ge=0, le=2)
    max_trade_stops: int = Field(default=6, ge=0, le=12)
    max_leg_jumps: int = Field(default=5, ge=1, le=20)

    @model_validator(mode="after")
    def destination_differs(self) -> "TransitRequest":
        if self.destination_system_id64 == self.state.origin_system_id64:
            raise ValueError("Destination system must differ from origin")
        return self


class TransitSummary(BaseModel):
    profile: Literal["Direct", "Fast", "Balanced", "Profit"]
    legs: list[TradeLeg]
    total_distance_ly: float
    estimated_jumps: int
    estimated_seconds: int
    expected_profit: int
    extra_seconds_vs_direct: int
    extra_distance_vs_direct: float
    confidence: Literal["High", "Medium", "Low"]
    positioning_station: str | None = None
    positioning_system: str | None = None
    warnings: list[str] = Field(default_factory=list)


class TransitResult(BaseModel):
    direct: TransitSummary
    options: list[TransitSummary]


class ImmersiveTradeRoute(BaseModel):
    name: str
    legs: list[TradeLeg]
    total_profit: int
    total_distance_ly: float
    estimated_jumps: int
    estimated_seconds: int
    confidence: Literal["High", "Medium", "Low"]
    cargo_variety: int


class ImmersiveTradeRouteResponse(BaseModel):
    routes: list[ImmersiveTradeRoute]
    assumptions: list[str]


class ShipProfileInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    ship_model: str = Field(min_length=1, max_length=100)
    cargo_capacity: int = Field(gt=0, le=2000)
    unladen_jump_range: float = Field(gt=0, le=500)
    laden_jump_range: float = Field(gt=0, le=500)
    pad_size: PadSize
    has_fuel_scoop: bool = False
    shielded: bool = True
    notes: str = Field(default="", max_length=1000)


class ShipProfileOutput(ShipProfileInput):
    id: int


class LocationResult(BaseModel):
    kind: Literal["system", "station"]
    id: int
    name: str
    system_id64: int
    system_name: str
    subtitle: str
