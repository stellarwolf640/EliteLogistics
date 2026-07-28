import { useEffect, useState } from "react";
import type { SearchDraft } from "./types";

const STORAGE_KEY = "elite-logistics-search-draft-v1";

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
  const [draft, setDraft] = useState<SearchDraft>(() => {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (!saved) return defaultDraft;
    try {
      return { ...defaultDraft, ...JSON.parse(saved) };
    } catch {
      return defaultDraft;
    }
  });

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(draft));
  }, [draft]);

  return { draft, setDraft };
}
