import type {
  DataStatus,
  JobResponse,
  ImmersiveTradeRouteResponse,
  LocationResult,
  RoundTripResponse,
  SearchDraft,
  ShipProfile,
  TradeResponse,
} from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(detail.detail ?? "Request failed");
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const api = {
  dataStatus: () => request<DataStatus>("/api/data/status"),
  packInfo: () => request<{ url: string; bytes: number; available: boolean; error?: string }>("/api/data/spansh-pack-info"),
  locations: (query: string) =>
    request<LocationResult[]>(`/api/locations/search?q=${encodeURIComponent(query)}&limit=12`),
  profiles: () => request<ShipProfile[]>("/api/ship-profiles"),
  createProfile: (payload: Omit<ShipProfile, "id">) =>
    request<ShipProfile>("/api/ship-profiles", { method: "POST", body: JSON.stringify(payload) }),
  deleteProfile: (id: number) => request<void>(`/api/ship-profiles/${id}`, { method: "DELETE" }),
  trades: (draft: SearchDraft) =>
    request<TradeResponse>("/api/trades/search", {
      method: "POST",
      body: JSON.stringify(buildTradePayload(draft)),
    }),
  roundTrips: (draft: SearchDraft) =>
    request<RoundTripResponse>("/api/round-trips/search", {
      method: "POST",
      body: JSON.stringify(buildTradePayload(draft)),
    }),
  tradeRoutes: (draft: SearchDraft) =>
    request<ImmersiveTradeRouteResponse>("/api/trade-routes/search", {
      method: "POST",
      body: JSON.stringify(buildTradePayload(draft)),
    }),
  startTransit: (draft: SearchDraft) =>
    request<{ job_id: string; status: string }>("/api/transit/plans", {
      method: "POST",
      body: JSON.stringify({
        state: buildState(draft),
        destination_system_id64: Number(draft.destinationSystemId64),
        destination_station_market_id: optionalNumber(draft.destinationStationMarketId),
        filters: buildFilters(draft),
        detour_limit: 0.2,
        max_trade_stops: 6,
        max_leg_jumps: 5,
      }),
    }),
  job: (id: string) => request<JobResponse>(`/api/jobs/${id}`),
  startImport: (download = false) =>
    request<{ job_id: string; status: string }>("/api/data/spansh-imports", {
      method: "POST",
      body: JSON.stringify({ download }),
    }),
  cacheRegion: (draft: SearchDraft) =>
    request<{ imported: number; radius_ly: number; system_id64: number }>("/api/data/regions/cache", {
      method: "POST",
      body: JSON.stringify(buildTradePayload(draft)),
    }),
  deletePack: () => request<void>("/api/data/spansh-pack", { method: "DELETE" }),
};

function optionalNumber(value: string): number | null {
  return value.trim() ? Number(value) : null;
}

function buildState(draft: SearchDraft) {
  return {
    origin_system_id64: Number(draft.originSystemId64),
    origin_station_market_id: optionalNumber(draft.originStationMarketId),
    ship: {
      cargo_capacity: draft.cargoCapacity,
      laden_jump_range: draft.ladenJumpRange,
      pad_size: draft.padSize,
    },
    credits: draft.credits,
    rebuy_reserve: draft.rebuyReserve,
    cash_reserve: draft.cashReserve,
  };
}

function buildFilters(draft: SearchDraft) {
  return {
    max_market_age_hours: draft.maxMarketAgeHours,
    max_station_distance_ls: draft.maxStationDistanceLs,
    min_supply_multiplier: 2,
    min_demand_multiplier: 2,
    include_fleet_carriers: draft.includeFleetCarriers,
    include_planetary: draft.includePlanetary,
    include_odyssey: draft.includeOdyssey,
    include_permit_systems: false,
    include_restricted: false,
    hide_low_confidence: draft.hideLowConfidence,
  };
}

function buildTradePayload(draft: SearchDraft) {
  return {
    state: buildState(draft),
    filters: buildFilters(draft),
    sort: "recommended",
    max_results: 50,
    max_system_distance_ly: draft.maxSystemDistanceLy,
  };
}
