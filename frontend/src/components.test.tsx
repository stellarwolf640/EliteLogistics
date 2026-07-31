import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ConfidenceBadge, FlightBoard, LocationPicker, SearchFields, TradeCard, elitePlanningPatch } from "./components";
import { ComputerPage, ConsoleHeader } from "./App";
import type { EliteStatus, SearchDraft, TradeLeg } from "./types";
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
    expect(screen.getByRole("button", { name: "Auto-fill with live data" })).toBeDisabled();
  });

  it("maps supported live game values into trade and transit fields", () => {
    const patch = elitePlanningPatch({
      available: true,
      system_id64: 10,
      system_name: "Origin",
      station_market_id: 11,
      station_name: "Origin Hub",
      docked: true,
      cargo_capacity: 216,
      max_jump_range: 31.4,
      credits: 25_000_000,
      rebuy: 1_200_000,
      target_system_id64: 20,
      target_system_name: "Waypoint",
      target_station_name: "Mercator Port",
      nav_route: [],
    } as unknown as EliteStatus["state"], true);

    expect(patch).toMatchObject({
      originSystemId64: "10",
      originStationMarketId: "11",
      originLocationLabel: "Origin Hub, Origin",
      cargoCapacity: 216,
      ladenJumpRange: 31.4,
      credits: 25_000_000,
      rebuyReserve: 1_200_000,
      destinationSystemId64: "20",
      destinationLocationLabel: "Mercator Port, Waypoint",
    });
  });

  it("uses breadcrumb hierarchy entries as navigation controls", () => {
    window.history.pushState({}, "", "/trade");
    window.scrollTo = vi.fn();
    render(<ConsoleHeader path="/trade" observations={100} />);

    fireEvent.click(screen.getByRole("button", { name: "TRADE OPERATIONS" }));

    expect(window.location.pathname).toBe("/operations");
    expect(screen.getByRole("button", { name: "BEST TRADES" })).toBeDisabled();
  });

  it("keeps available Elite data visibly linked while telemetry is idle", () => {
    const elite = {
      enabled: true,
      state: { available: true, game_running: false },
    } as EliteStatus;

    render(<ConsoleHeader path="/" observations={100} elite={elite} />);

    expect(screen.getByText("LINKED")).toBeInTheDocument();
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

  it("shows safe Computer settings and lets a cleared bindings path stay clear", async () => {
    const computerSettings = {
      schema_version: 1,
      enabled: false,
      mode: "off",
      address_as_commander: true,
      verbosity: "standard",
      proactivity: "critical",
      class_b_enabled: false,
      enabled_game_actions: [],
      confirmation_policy: "recommended",
      bindings_directory: "C:\\Elite\\Bindings",
    };
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      let body: unknown = [];
      if (url.includes("/api/computer/status")) {
        body = {
          foundation_version: 1,
          settings: computerSettings,
          runtimes: { command: "policy_runtime", input_bridge: "not_installed" },
          catalog: { tools: 1, initial_tools: 1, controls: 1, initial_controls: 1 },
          execution_available: true,
          executable_tools: ["get_operational_snapshot"],
          warnings: ["Class B settings are preparatory only; ION cannot send game inputs."],
        };
      } else if (url.includes("/api/computer/tools")) {
        body = [{
          name: "get_operational_snapshot",
          category: "awareness",
          description: "Operational state",
          permission: "read",
          initial_release: true,
          requires_explicit_user: false,
          requires_confirmation: false,
          proactive_allowed: true,
          implementation_status: "available",
        }];
      } else if (url.includes("/api/computer/controls")) {
        body = [{
          action_id: "landing_gear",
          group: "ship_system",
          label: "Landing gear",
          permission: "game_green",
          desired_state: true,
          verifiable: true,
          initial_release: true,
          description: "Deploy or retract landing gear.",
        }];
      } else if (url.includes("/api/computer/bindings")) {
        body = {
          available: true,
          configured_directory: "C:\\Elite\\Bindings",
          file_name: "Custom.binds",
          preset: "Custom",
          capabilities: [{
            action_id: "landing_gear",
            label: "Landing gear",
            elite_binding: "LandingGearToggle",
            primary: { device: "Keyboard", device_kind: "keyboard", key: "Key_L", modifiers: [], display: "Keyboard: L" },
            secondary: null,
            status: "ready",
            conflicts: [],
            ion_status: "ready",
            input_bridge_available: true,
          }],
          device_kinds: ["keyboard"],
          conflict_count: 0,
          warning: null,
          input_bridge_available: true,
        };
      } else if (url.includes("/api/computer/input-bridge")) {
        body = {
          available: true,
          platform: "windows",
          emergency_disabled: false,
          emergency_hotkey: "Ctrl + Shift + Pause",
          busy: false,
          active_action: null,
          last_result: null,
          minimum_interval_seconds: 0.4,
        };
      }
      return { ok: true, status: 200, json: async () => body } as Response;
    }));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}><ComputerPage /></QueryClientProvider>);

    expect(await screen.findByText("Computer settings")).toBeInTheDocument();
    expect(await screen.findByText("Computer console")).toBeInTheDocument();
    expect(await screen.findByText("READY FOR FOREGROUND CHECK")).toBeInTheDocument();
    expect(await screen.findByText(/cannot send game inputs/i)).toBeInTheDocument();
    expect(await screen.findByText("Keyboard: L")).toBeInTheDocument();
    const path = screen.getByDisplayValue("C:\\Elite\\Bindings");
    fireEvent.change(path, { target: { value: "" } });
    expect(path).toHaveValue("");
  });
});
