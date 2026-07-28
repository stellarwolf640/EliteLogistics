export type Confidence = "High" | "Medium" | "Low";

export interface DataStatus {
  systems: number;
  stations: number;
  market_observations: number;
  latest_market_observation: string | null;
  online_provider: string;
  pack_path: string;
  pack_installed: boolean;
  pack_bytes: number;
  partial_pack_bytes: number;
  database_bytes: number;
}

export interface LocationResult {
  kind: "system" | "station";
  id: number;
  name: string;
  system_id64: number;
  system_name: string;
  subtitle: string;
}

export interface ShipProfile {
  id: number;
  name: string;
  ship_model: string;
  cargo_capacity: number;
  unladen_jump_range: number;
  laden_jump_range: number;
  pad_size: "S" | "M" | "L";
  has_fuel_scoop: boolean;
  shielded: boolean;
  notes: string;
}

export interface TradeLeg {
  source_market_id: number;
  source_station: string;
  source_system_id64: number;
  source_system: string;
  destination_market_id: number;
  destination_station: string;
  destination_system_id64: number;
  destination_system: string;
  commodity_id: number;
  commodity: string;
  buy_price: number;
  sell_price: number;
  quantity: number;
  profit_per_ton: number;
  trip_profit: number;
  system_distance_ly: number;
  jumps: number;
  estimated_seconds: number;
  credits_per_hour: number;
  distance_to_route_ly: number;
  relocation_jumps: number;
  relocation_seconds: number;
  first_trip_credits_per_hour: number;
  confidence_score: number;
  confidence: Confidence;
  source_observed_at: string;
  destination_observed_at: string;
  provider: string;
  warnings: string[];
}

export interface TradeResponse {
  routes: TradeLeg[];
  available_credits: number;
  assumptions: string[];
}

export interface RoundTrip {
  outbound: TradeLeg;
  return_leg: TradeLeg;
  total_profit: number;
  estimated_seconds: number;
  relocation_seconds: number;
  credits_per_hour: number;
  confidence: Confidence;
}

export interface RoundTripResponse {
  routes: RoundTrip[];
  available_credits: number;
  assumptions: string[];
}

export interface TransitSummary {
  profile: "Direct" | "Fast" | "Balanced" | "Profit";
  legs: TradeLeg[];
  total_distance_ly: number;
  estimated_jumps: number;
  estimated_seconds: number;
  expected_profit: number;
  extra_seconds_vs_direct: number;
  extra_distance_vs_direct: number;
  confidence: Confidence;
  positioning_station: string | null;
  positioning_system: string | null;
  warnings: string[];
}

export interface TransitResult {
  direct: TransitSummary;
  options: TransitSummary[];
}

export interface ImmersiveTradeRoute {
  name: string;
  legs: TradeLeg[];
  total_profit: number;
  total_distance_ly: number;
  estimated_jumps: number;
  estimated_seconds: number;
  confidence: Confidence;
  cargo_variety: number;
}

export interface ImmersiveTradeRouteResponse {
  routes: ImmersiveTradeRoute[];
  assumptions: string[];
}

export interface JobResponse {
  id: string;
  kind: string;
  status: "queued" | "running" | "complete" | "failed";
  progress: number;
  result: TransitResult | { counts?: Record<string, number>; path?: string; downloaded_bytes?: number; total_bytes?: number; speed_bps?: number; eta_seconds?: number; phase?: string } | null;
  error: string | null;
}

export interface SearchDraft {
  originSystemId64: string;
  originStationMarketId: string;
  originLocationLabel: string;
  destinationSystemId64: string;
  destinationStationMarketId: string;
  destinationLocationLabel: string;
  cargoCapacity: number;
  ladenJumpRange: number;
  padSize: "S" | "M" | "L";
  credits: number;
  rebuyReserve: number;
  cashReserve: number;
  maxMarketAgeHours: number;
  maxStationDistanceLs: number;
  maxSystemDistanceLy: number;
  includeFleetCarriers: boolean;
  includePlanetary: boolean;
  includeOdyssey: boolean;
  hideLowConfidence: boolean;
}
