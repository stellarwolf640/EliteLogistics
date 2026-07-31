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

export interface EliteCargoItem {
  commodity: string;
  canonical_commodity: string;
  count: number;
  stolen: number;
  mission_id: number | null;
}

export interface EliteTransaction {
  kind: "buy" | "sell";
  market_id: number;
  commodity: string;
  canonical_commodity: string;
  quantity: number;
  price: number;
  timestamp: string | null;
}

export interface EliteLiveState {
  directory: string;
  available: boolean;
  source_kind: "unavailable" | "journal" | "reference";
  game_running: boolean;
  latest_event_at: string | null;
  journal_file: string | null;
  commander: string | null;
  credits: number | null;
  system_id64: number | null;
  system_name: string | null;
  system_position: number[] | null;
  station_market_id: number | null;
  station_name: string | null;
  station_type: string | null;
  station_distance_ls: number | null;
  largest_pad: "S" | "M" | "L" | null;
  docked: boolean;
  phase: string;
  ship_model: string | null;
  ship_name: string | null;
  ship_ident: string | null;
  ship_id: number | null;
  cargo_capacity: number | null;
  cargo_count: number;
  max_jump_range: number | null;
  rebuy: number | null;
  cargo: EliteCargoItem[];
  target_system_id64: number | null;
  target_system_name: string | null;
  target_station_name: string | null;
  landing_pad: number | null;
  nav_route: Array<{ system_id64: number; system_name: string; star_class: string | null; position: number[] | null }>;
  status_flags: string[];
  transactions: EliteTransaction[];
  files: Record<string, boolean>;
  warnings: string[];
}

export interface EliteStatus {
  enabled: boolean;
  auto_apply_planning_state: boolean;
  configured_directory: string;
  reference_directory: string | null;
  market_records_updated: number;
  state: EliteLiveState;
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

export interface WindowBounds {
  x: number | null;
  y: number | null;
  width: number;
  height: number;
  maximized: boolean;
}

export interface Preferences {
  schema_version: 3;
  search_draft: {
    origin_system_id64: string;
    origin_station_market_id: string;
    origin_location_label: string;
    destination_system_id64: string;
    destination_station_market_id: string;
    destination_location_label: string;
    cargo_capacity: number;
    laden_jump_range: number;
    pad_size: "S" | "M" | "L";
    credits: number;
    rebuy_reserve: number;
    cash_reserve: number;
    max_market_age_hours: number;
    max_station_distance_ls: number;
    max_system_distance_ly: number;
    include_fleet_carriers: boolean;
    include_planetary: boolean;
    include_odyssey: boolean;
    hide_low_confidence: boolean;
  };
  data_mode: "live" | "regional" | "full";
  close_behavior: "exit" | "tray";
  main_window: WindowBounds;
  route_window: WindowBounds;
  route_fullscreen: boolean;
  route_always_on_top: boolean;
  update_last_checked_at: string | null;
  elite_enabled: boolean;
  elite_journal_directory: string;
  elite_auto_apply_planning_state: boolean;
  computer: {
    schema_version: 1;
    enabled: boolean;
    mode: "off" | "command" | "lite" | "enhanced" | "automatic";
    address_as_commander: boolean;
    verbosity: "brief" | "standard" | "detailed" | "silent";
    proactivity: "silent" | "critical" | "operational" | "conversational";
    class_b_enabled: boolean;
    enabled_game_actions: string[];
    confirmation_policy: "always" | "recommended" | "minimal";
    bindings_directory: string;
  };
}

export type ComputerPreferences = Preferences["computer"];

export interface ComputerTool {
  name: string;
  category: string;
  description: string;
  permission: "read" | "ion" | "game_green" | "game_amber" | "confirm";
  initial_release: boolean;
  requires_explicit_user: boolean;
  requires_confirmation: boolean;
  proactive_allowed: boolean;
  implementation_status: "contract_only" | "available";
}

export interface ComputerControl {
  action_id: string;
  group: string;
  label: string;
  permission: "game_green" | "game_amber";
  desired_state: boolean;
  verifiable: boolean;
  initial_release: boolean;
  description: string;
}

export interface ComputerStatus {
  foundation_version: number;
  settings: ComputerPreferences;
  runtimes: Record<string, string>;
  catalog: {
    tools: number;
    initial_tools: number;
    controls: number;
    initial_controls: number;
  };
  execution_available: boolean;
  executable_tools: string[];
  warnings: string[];
}

export interface ComputerInvocation {
  id: string;
  tool_name: string;
  source: string;
  status: "queued" | "running" | "completed" | "failed" | "timed_out" | "denied" | "awaiting_confirmation" | "canceled" | "expired";
  arguments: Record<string, unknown>;
  result: Record<string, unknown> | null;
  error: string | null;
  confirmation_id: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface BindingSlot {
  device: string;
  device_kind: "keyboard" | "mouse" | "controller" | "hotas" | "unknown";
  key: string;
  modifiers: string[];
  display: string;
}

export interface BindingCapability {
  action_id: string;
  label: string;
  elite_binding: string | null;
  primary: BindingSlot | null;
  secondary: BindingSlot | null;
  status: "ready" | "unbound" | "conflict";
  conflicts: string[];
}

export interface BindingReport {
  available: boolean;
  configured_directory: string;
  file_name: string | null;
  preset: string | null;
  major_version?: string | null;
  minor_version?: string | null;
  capabilities: BindingCapability[];
  device_kinds: string[];
  conflict_count: number;
  warning: string | null;
}

export interface ActiveOperation {
  operation_type: string;
  schema_version: number;
  title: string;
  route_payload: {
    title: string;
    legs: TradeLeg[];
    summary: { profit: number; seconds: number; distance?: number; jumps?: number };
    preflight?: string;
  };
  activated_at: string;
  manual_progress: number;
  status: "active" | "paused" | "completed";
  updated_at: string;
}

export interface EventEnvelope {
  sequence: number;
  type: string;
  timestamp: string;
  payload: unknown;
}

export interface Diagnostics {
  version: string;
  packaged: boolean;
  runtime_paths: Record<string, string>;
  database_ok: boolean;
  webview2_available: boolean | null;
  game_link: EliteStatus;
  recent_errors: string[];
}

export interface UpdateStatus {
  status: "idle" | "checking" | "current" | "available" | "downloading" | "ready" | "error";
  installed_version: string;
  available_version: string | null;
  release_notes: string;
  progress: number;
  error: string | null;
  installer_path: string | null;
  downloaded_bytes?: number;
  total_bytes?: number;
}
