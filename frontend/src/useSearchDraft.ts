import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import type { Preferences, SearchDraft } from "./types";

export const defaultDraft: SearchDraft = {
  originSystemId64: "",
  originStationMarketId: "",
  originLocationLabel: "",
  destinationSystemId64: "",
  destinationStationMarketId: "",
  destinationLocationLabel: "",
  cargoCapacity: 104,
  ladenJumpRange: 18.7,
  padSize: "M",
  credits: 12_500_000,
  rebuyReserve: 600_000,
  cashReserve: 250_000,
  maxMarketAgeHours: 4,
  maxStationDistanceLs: 2000,
  maxSystemDistanceLy: 100,
  includeFleetCarriers: false,
  includePlanetary: false,
  includeOdyssey: false,
  hideLowConfidence: true,
};

export function useSearchDraft() {
  const [draft, setDraft] = useState<SearchDraft>(defaultDraft);
  const preferences = useQuery({ queryKey: ["preferences"], queryFn: api.preferences });
  const save = useMutation({ mutationFn: api.updatePreferences });
  const hydrated = useRef(false);

  useEffect(() => {
    if (!preferences.data || hydrated.current) return;
    setDraft(fromPreferenceDraft(preferences.data));
    hydrated.current = true;
  }, [preferences.data]);

  useEffect(() => {
    if (!preferences.data || !hydrated.current) return;
    const timer = window.setTimeout(() => {
      save.mutate({ ...preferences.data!, search_draft: toPreferenceDraft(draft) });
    }, 350);
    return () => window.clearTimeout(timer);
  }, [draft, preferences.data]);

  return { draft, setDraft, preferences: preferences.data, savePreferences: save.mutate };
}

function fromPreferenceDraft(preferences: Preferences): SearchDraft {
  const value = preferences.search_draft;
  return {
    originSystemId64: value.origin_system_id64,
    originStationMarketId: value.origin_station_market_id,
    originLocationLabel: value.origin_location_label,
    destinationSystemId64: value.destination_system_id64,
    destinationStationMarketId: value.destination_station_market_id,
    destinationLocationLabel: value.destination_location_label,
    cargoCapacity: value.cargo_capacity,
    ladenJumpRange: value.laden_jump_range,
    padSize: value.pad_size,
    credits: value.credits,
    rebuyReserve: value.rebuy_reserve,
    cashReserve: value.cash_reserve,
    maxMarketAgeHours: value.max_market_age_hours,
    maxStationDistanceLs: value.max_station_distance_ls,
    maxSystemDistanceLy: value.max_system_distance_ly,
    includeFleetCarriers: value.include_fleet_carriers,
    includePlanetary: value.include_planetary,
    includeOdyssey: value.include_odyssey,
    hideLowConfidence: value.hide_low_confidence,
  };
}

function toPreferenceDraft(value: SearchDraft): Preferences["search_draft"] {
  return {
    origin_system_id64: value.originSystemId64,
    origin_station_market_id: value.originStationMarketId,
    origin_location_label: value.originLocationLabel,
    destination_system_id64: value.destinationSystemId64,
    destination_station_market_id: value.destinationStationMarketId,
    destination_location_label: value.destinationLocationLabel,
    cargo_capacity: value.cargoCapacity,
    laden_jump_range: value.ladenJumpRange,
    pad_size: value.padSize,
    credits: value.credits,
    rebuy_reserve: value.rebuyReserve,
    cash_reserve: value.cashReserve,
    max_market_age_hours: value.maxMarketAgeHours,
    max_station_distance_ls: value.maxStationDistanceLs,
    max_system_distance_ly: value.maxSystemDistanceLy,
    include_fleet_carriers: value.includeFleetCarriers,
    include_planetary: value.includePlanetary,
    include_odyssey: value.includeOdyssey,
    hide_low_confidence: value.hideLowConfidence,
  };
}
