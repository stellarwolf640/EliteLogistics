import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ConfidenceBadge, FlightBoard, LocationPicker, SearchFields, TradeCard } from "./components";
import { ConsoleHeader } from "./App";
import type { SearchDraft, TradeLeg } from "./types";
import { defaultDraft } from "./useSearchDraft";
import { optimizeShip, SHIP_CATALOG } from "./shipCatalog";

const leg: TradeLeg = {
  source_market_id: 1,
  source_station: "Origin Hub",
  source_system_id64: 10,
  source_system: "Origin",
  destination_market_id: 2,
  destination_station: "Mercator Port",
  destination_system_id64: 20,
  destination_system: "Waypoint",
  commodity_id: 100,
  commodity: "Silver",
  buy_price: 10_000,
  sell_price: 23_000,
  quantity: 100,
  profit_per_ton: 13_000,
  trip_profit: 1_300_000,
  system_distance_ly: 20,
  jumps: 2,
  estimated_seconds: 300,
  credits_per_hour: 15_600_000,
  distance_to_route_ly: 0,
  relocation_jumps: 0,
  relocation_seconds: 0,
  first_trip_credits_per_hour: 15_600_000,
  confidence_score: 91,
  confidence: "High",
  source_observed_at: "2026-07-28T16:00:00Z",
  destination_observed_at: "2026-07-28T16:00:00Z",
  provider: "fixture",
  warnings: [],
};

describe("route presentation", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });
  it("shows confidence and the full cargo instruction", () => {
    render(<TradeCard leg={leg} />);
    expect(screen.getByText("Silver · 100 t")).toBeInTheDocument();
    expect(screen.getByText(/100 t Silver at 10,000 CR\/t/)).toBeInTheDocument();
    expect(screen.getByText("High · 91")).toBeInTheDocument();
  });

  it("labels low confidence clearly", () => {
    render(<ConfidenceBadge value="Low" score={32} />);
    expect(screen.getByText("Low · 32")).toHaveClass("confidence-low");
  });

  it("asks for the current location and exposes the trade search radius", () => {
    const draft: SearchDraft = { ...defaultDraft, maxSystemDistanceLy: 75 };
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <SearchFields draft={draft} update={() => undefined} />
      </QueryClientProvider>,
    );
    expect(screen.getByText("Where are you?")).toBeInTheDocument();
    expect(screen.getByText("Look for routes within")).toBeInTheDocument();
    expect(screen.getByDisplayValue("75")).toBeInTheDocument();
  });

  it("uses breadcrumb hierarchy entries as navigation controls", () => {
    window.history.pushState({}, "", "/trade");
    window.scrollTo = vi.fn();
    render(<ConsoleHeader path="/trade" observations={100} />);

    fireEvent.click(screen.getByRole("button", { name: "TRADE OPERATIONS" }));

    expect(window.location.pathname).toBe("/operations");
    expect(screen.getByRole("button", { name: "BEST TRADES" })).toBeDisabled();
  });

  it("keeps a location field empty when the operator clears it", () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const onClear = vi.fn();
    render(
      <QueryClientProvider client={client}>
        <LocationPicker label="Where are you?" value="Sol" onSelect={() => undefined} onClear={onClear} />
      </QueryClientProvider>,
    );
    const input = screen.getByDisplayValue("Sol");
    fireEvent.change(input, { target: { value: "" } });
    expect(input).toHaveValue("");
    expect(onClear).toHaveBeenCalledOnce();
  });

  it("builds different slot-by-slot outfitting manifests", () => {
    const type6 = SHIP_CATALOG.find((ship) => ship.model === "Type-6 Transporter")!;
    const cargo = optimizeShip(type6, "Cargo first");
    const safety = optimizeShip(type6, "Safety first");
    expect(cargo.core).toHaveLength(8);
    expect(cargo.optional).toHaveLength(type6.optionalSlots.length);
    expect(cargo.optional.map((item) => item.module)).not.toEqual(safety.optional.map((item) => item.module));
    expect(safety.utilities.some((item) => item.module.includes("Shield Booster"))).toBe(true);
  });

  it("shows a manual route-progress guide when live game data is unavailable", () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise(() => undefined)));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <FlightBoard
          title="Test route"
          legs={[leg]}
          summary={{ profit: leg.trip_profit, seconds: leg.estimated_seconds }}
          onClose={() => undefined}
        />
      </QueryClientProvider>,
    );
    expect(screen.getByText("ROUTE GUIDE")).toBeInTheDocument();
    expect(screen.getByText("MANUAL PROGRESS")).toBeInTheDocument();
    expect(screen.getByText("Advance")).toBeInTheDocument();
  });

  it("switches the progress rail to live tracking when Elite is running", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        enabled: true,
        auto_apply_planning_state: false,
        configured_directory: "C:\\Elite",
        reference_directory: null,
        market_records_updated: 0,
        state: {
          available: true,
          source_kind: "journal",
          game_running: true,
          phase: "supercruise",
          station_market_id: null,
          station_name: null,
          system_id64: 10,
          system_name: "Origin",
          target_system_name: "Waypoint",
          nav_route: [],
          cargo: [{ commodity: "Silver", canonical_commodity: "silver", count: 100, stolen: 0, mission_id: null }],
          transactions: [],
          landing_pad: null,
        },
      }),
    }));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <FlightBoard
          title="Live route"
          legs={[leg]}
          summary={{ profit: leg.trip_profit, seconds: leg.estimated_seconds }}
          onClose={() => undefined}
        />
      </QueryClientProvider>,
    );
    expect(await screen.findByText("LIVE ROUTE TRACKING")).toBeInTheDocument();
    expect(screen.getByText("Target: Waypoint")).toBeInTheDocument();
  });
});
