import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Boxes,
  Database,
  Gauge,
  PackageSearch,
  RefreshCw,
  Route,
  Map,
  Ship,
  Truck,
  Wrench,
  X,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api } from "./api";
import {
  EmptyState,
  FlightBoard,
  Notice,
  SearchFields,
  TradeCard,
  TransitCard,
  formatCredits,
  formatTime,
} from "./components";
import type { ImmersiveTradeRoute, JobResponse, RoundTrip, SearchDraft, ShipProfile, TradeLeg, TransitResult, TransitSummary } from "./types";
import { useSearchDraft } from "./useSearchDraft";
import { optimizeShip, SHIP_CATALOG, type OptimizationMode } from "./shipCatalog";

const routeLabels: Record<string, string[]> = {
  "/": ["HOME"],
  "/operations": ["HOME", "TRADE OPERATIONS"],
  "/trade": ["HOME", "TRADE OPERATIONS", "BEST TRADES"],
  "/round-trips": ["HOME", "TRADE OPERATIONS", "ROUND TRIPS"],
  "/trade-routes": ["HOME", "TRADE OPERATIONS", "TRADE ROUTES"],
  "/navigation": ["HOME", "NAVIGATION"],
  "/transit": ["HOME", "NAVIGATION", "PROFITABLE TRANSIT"],
  "/fleet": ["HOME", "FLEET MANAGEMENT"],
  "/ships": ["HOME", "FLEET MANAGEMENT", "SHIP PROFILES"],
  "/ship-optimizations": ["HOME", "FLEET MANAGEMENT", "SHIP OPTIMIZATIONS"],
  "/data": ["HOME", "DATA NETWORK"],
};

export default function App() {
  const path = usePath();
  const { draft, setDraft } = useSearchDraft();
  const update = (patch: Partial<SearchDraft>) => setDraft((current) => ({ ...current, ...patch }));
  const status = useQuery({ queryKey: ["data-status"], queryFn: api.dataStatus });
  if (path === "/flight-board") {
    try {
      const payload = JSON.parse(localStorage.getItem("elite-logistics-flight-board") ?? "null");
      if (payload) return <FlightBoard {...payload} allowPopout={false} onClose={() => window.close()} />;
    } catch {
      // A malformed saved board simply returns to the normal planning shell.
    }
  }

  return (
    <div className="app-shell">
      <main>
        <ConsoleHeader path={path} observations={status.data?.market_observations ?? 0} />
        {path === "/" && <Dashboard status={status.data} draft={draft} />}
        {path === "/operations" && <OperationsMenu />}
        {path === "/trade" && <TradePage draft={draft} update={update} />}
        {path === "/round-trips" && <RoundTripPage draft={draft} update={update} />}
        {path === "/trade-routes" && <TradeRoutesPage draft={draft} update={update} />}
        {path === "/navigation" && <NavigationMenu />}
        {path === "/transit" && <TransitPage draft={draft} update={update} />}
        {path === "/fleet" && <FleetMenu />}
        {path === "/ships" && <ShipsPage draft={draft} update={update} />}
        {path === "/ship-optimizations" && <ShipOptimizationsPage draft={draft} update={update} />}
        {path === "/data" && <DataPage draft={draft} update={update} />}
        {!routeLabels[path] && <Dashboard status={status.data} draft={draft} />}
      </main>
    </div>
  );
}

function ConsoleHeader({ path, observations }: { path: string; observations: number }) {
  const trail = routeLabels[path] ?? ["HOME"];
  return (
    <header className="console-header">
      <button className="console-brand" onClick={() => navigateTo("/")}>
        <Boxes size={24} /><div><strong>ELITE LOGISTICS</strong><span>INDEPENDENT PILOTS FEDERATION</span></div>
      </button>
      <div className="breadcrumb">
        {trail.map((label, index) => <span key={label} className={index === trail.length - 1 ? "active" : ""}>{label}</span>)}
      </div>
      <div className="console-status"><span className={observations ? "online" : ""} /><div><b>MARKET LINK</b><small>{observations.toLocaleString()} RECORDS</small></div></div>
    </header>
  );
}

function navigateTo(path: string) {
  window.history.pushState({}, "", path);
  window.dispatchEvent(new Event("elite-logistics:navigate"));
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function usePath() {
  const [path, setPath] = useState(window.location.pathname);
  useEffect(() => {
    const update = () => setPath(window.location.pathname);
    window.addEventListener("popstate", update);
    window.addEventListener("elite-logistics:navigate", update);
    return () => {
      window.removeEventListener("popstate", update);
      window.removeEventListener("elite-logistics:navigate", update);
    };
  }, []);
  return path;
}

function useNavigate() {
  return navigateTo;
}

function PageHeader({ eyebrow, title, body }: { eyebrow: string; title: string; body: string }) {
  return (
    <div className="page-header">
      <span className="eyebrow">{eyebrow}</span>
      <h1>{title}</h1>
      <p>{body}</p>
    </div>
  );
}

function Dashboard({ status, draft }: { status?: Awaited<ReturnType<typeof api.dataStatus>>; draft: SearchDraft }) {
  const navigate = useNavigate();
  const available = Math.max(0, draft.credits - draft.rebuyReserve - draft.cashReserve);
  return (
    <div className="page console-home">
      <section className="commander-strip">
        <div><span>COMMANDER STATE</span><strong>{draft.originLocationLabel || "LOCATION NOT SET"}</strong></div>
        <div><span>ACTIVE VESSEL</span><strong>{draft.cargoCapacity} T CARGO · {draft.ladenJumpRange} LY</strong></div>
        <div><span>AVAILABLE CAPITAL</span><strong>{formatCredits(available)}</strong></div>
        <div><span>DATA COVERAGE</span><strong>{status?.systems.toLocaleString() ?? 0} SYSTEMS</strong></div>
      </section>
      <div className="console-intro"><span>STARPORT SERVICES</span><h1>SELECT A SERVICE</h1><p>Independent logistics, navigation, fleet outfitting, and market intelligence.</p></div>
      <section className="service-grid">
        <ServiceTile index="01" icon={Truck} title="Trade Operations" body="Commodity trades, closed loops, and immersive multi-stop cargo contracts." meta="3 SERVICES" onClick={() => navigate("/operations")} featured />
        <ServiceTile index="02" icon={Route} title="Navigation" body="Plan direct and profitable travel across populated space." meta="1 SERVICE" onClick={() => navigate("/navigation")} />
        <ServiceTile index="03" icon={Ship} title="Fleet Management" body="Store ship profiles and plan complete role-specific module loadouts." meta="2 SERVICES" onClick={() => navigate("/fleet")} />
        <ServiceTile index="04" icon={Database} title="Data Network" body="Control live, regional, and full-galaxy market coverage." meta={`${status?.market_observations.toLocaleString() ?? 0} RECORDS`} onClick={() => navigate("/data")} />
      </section>
    </div>
  );
}

function ServiceTile({ index, icon: Icon, title, body, meta, onClick, featured }: { index: string; icon: typeof Gauge; title: string; body: string; meta: string; onClick: () => void; featured?: boolean }) {
  return (
    <button className={`service-tile ${featured ? "featured" : ""}`} onClick={onClick}>
      <span className="service-index">{index}</span><Icon size={34} />
      <div><span>{meta}</span><h2>{title}</h2><p>{body}</p></div>
      <b>ENTER <Route size={15} /></b>
    </button>
  );
}

function MenuScreen({ code, title, body, children }: { code: string; title: string; body: string; children: React.ReactNode }) {
  return <div className="page submenu"><div className="console-intro"><span>{code}</span><h1>{title}</h1><p>{body}</p></div><section className="service-grid submenu-grid">{children}</section></div>;
}

function OperationsMenu() {
  return <MenuScreen code="OPERATIONS / CARGO" title="TRADE OPERATIONS" body="Choose the type of freight operation to prepare.">
    <ServiceTile index="01" icon={Gauge} title="Best Trades" body="Rank practical one-way cargo sales by time, confidence, and first-trip earnings." meta="PROFIT SEARCH" onClick={() => navigateTo("/trade")} />
    <ServiceTile index="02" icon={RefreshCw} title="Round Trips" body="Find paired outbound and return commodities for repeatable loops." meta="CLOSED LOOP" onClick={() => navigateTo("/round-trips")} />
    <ServiceTile index="03" icon={Map} title="Trade Routes" body="Generate longer multi-stop hauling contracts focused on the experience of the journey." meta="IMMERSIVE HAULAGE" onClick={() => navigateTo("/trade-routes")} featured />
  </MenuScreen>;
}

function NavigationMenu() {
  return <MenuScreen code="NAVIGATION / ROUTING" title="NAVIGATION" body="Prepare a route that balances destination progress, cargo opportunities, and market risk.">
    <ServiceTile index="01" icon={Route} title="Profitable Transit" body="Compare direct travel with Fast, Balanced, and Profit cargo corridors." meta="LONG-RANGE ROUTING" onClick={() => navigateTo("/transit")} featured />
  </MenuScreen>;
}

function FleetMenu() {
  return <MenuScreen code="FLEET / OUTFITTING" title="FLEET MANAGEMENT" body="Select a vessel, store its operating limits, or prepare a complete outfitting plan.">
    <ServiceTile index="01" icon={Ship} title="Ship Profiles" body="Store the real capacity, jump range, and pad requirements of the ships you fly." meta="VESSEL REGISTRY" onClick={() => navigateTo("/ships")} />
    <ServiceTile index="02" icon={Wrench} title="Ship Optimizations" body="Review every core, optional, utility, and hardpoint choice for a specialized build." meta="OUTFITTING PLAN" onClick={() => navigateTo("/ship-optimizations")} featured />
  </MenuScreen>;
}

function TradePage({ draft, update }: { draft: SearchDraft; update: (patch: Partial<SearchDraft>) => void }) {
  const navigate = useNavigate();
  const [board, setBoard] = useState<TradeLeg | null>(null);
  const search = useMutation({ mutationFn: () => api.trades(draft) });
  const tradeTo = (leg: TradeLeg) => {
    update({
      destinationSystemId64: String(leg.destination_system_id64),
      destinationStationMarketId: String(leg.destination_market_id),
      destinationLocationLabel: `${leg.destination_station}, ${leg.destination_system}`,
    });
    navigate("/transit");
  };
  return (
    <div className="page narrow">
      <PageHeader eyebrow="Trade / one way" title="Find the useful trade." body="Profit matters. So do jumps, supercruise, stale prices, and your rebuy." />
      <section className="planner-panel">
        <SearchFields draft={draft} update={update} />
        <button className="primary search-button" disabled={search.isPending || !draft.originSystemId64} onClick={() => search.mutate()}>
          {search.isPending ? <RefreshCw className="spin" size={17} /> : <PackageSearch size={17} />}
          {search.isPending ? "Calculating…" : "Find trades"}
        </button>
      </section>
      {search.error && <Notice tone="warning">{search.error.message}</Notice>}
      <section className="results">
        {search.data && <div className="results-heading"><h2>{search.data.routes.length} practical routes</h2><span>{formatCredits(search.data.available_credits)} available to trade</span></div>}
        {search.data?.routes.map((leg) => <TradeCard key={`${leg.source_market_id}-${leg.destination_market_id}-${leg.commodity_id}`} leg={leg} onTransit={tradeTo} onOpen={setBoard} />)}
        {search.data?.routes.length === 0 && <EmptyState title="No practical routes found" body="Try a larger distance, older market age, or import fresher market data." />}
        {!search.data && <EmptyState title="Ready when you are" body="Tell us where you are and how far away to look. Your form is saved on this device." icon={PackageSearch} />}
      </section>
      {board && <FlightBoard title={`${board.source_system} → ${board.destination_system}`} legs={[board]} summary={{ profit: board.trip_profit, seconds: board.estimated_seconds + board.relocation_seconds, distance: board.system_distance_ly + board.distance_to_route_ly, jumps: board.jumps + board.relocation_jumps }} onClose={() => setBoard(null)} />}
    </div>
  );
}

function RoundTripPage({ draft, update }: { draft: SearchDraft; update: (patch: Partial<SearchDraft>) => void }) {
  const [board, setBoard] = useState<RoundTrip | null>(null);
  const search = useMutation({ mutationFn: () => api.roundTrips(draft) });
  return (
    <div className="page narrow">
      <PageHeader eyebrow="Trade / closed loop" title="Never come home empty." body="Compare cargo in both directions, with capital and confidence recalculated for the return." />
      <section className="planner-panel">
        <SearchFields draft={draft} update={update} />
        <button className="primary search-button" disabled={search.isPending || !draft.originSystemId64} onClick={() => search.mutate()}>
          {search.isPending ? <RefreshCw className="spin" size={17} /> : <RefreshCw size={17} />}
          {search.isPending ? "Calculating…" : "Find round trips"}
        </button>
      </section>
      {search.error && <Notice tone="warning">{search.error.message}</Notice>}
      <section className="results">
        {search.data && <div className="results-heading"><h2>{search.data.routes.length} closed loops</h2><span>Ranked by estimated CR/hour</span></div>}
        {search.data?.routes.map((route, index) => (
          <article className="round-card" key={`${route.outbound.destination_market_id}-${index}`}>
            <div className="round-summary">
              <span className="eyebrow">Round trip</span>
              <strong>+{formatCredits(route.total_profit)}</strong>
              <small>{formatCredits(route.credits_per_hour)}/hr · {formatTime(route.estimated_seconds)}</small>
            </div>
            <div className="round-legs">
              <TradeCard leg={route.outbound} />
              <TradeCard leg={route.return_leg} />
            </div>
            <button className="secondary board-button" onClick={() => setBoard(route)}>Open round-trip console</button>
          </article>
        ))}
        {search.data?.routes.length === 0 && <EmptyState title="No valid return cargo" body="No two-way loop met your supply, demand, confidence, and access rules." />}
        {!search.data && <EmptyState title="Build a closed loop" body="The return leg uses your projected balance after the outbound sale." icon={RefreshCw} />}
      </section>
      {board && <FlightBoard title={`${board.outbound.source_system} cargo loop`} legs={[board.outbound, board.return_leg]} summary={{ profit: board.total_profit, seconds: board.estimated_seconds, distance: board.outbound.distance_to_route_ly + board.outbound.system_distance_ly + board.return_leg.system_distance_ly, jumps: board.outbound.relocation_jumps + board.outbound.jumps + board.return_leg.jumps }} onClose={() => setBoard(null)} />}
    </div>
  );
}

function TradeRoutesPage({ draft, update }: { draft: SearchDraft; update: (patch: Partial<SearchDraft>) => void }) {
  const [board, setBoard] = useState<ImmersiveTradeRoute | null>(null);
  const search = useMutation({ mutationFn: () => api.tradeRoutes(draft) });
  return (
    <div className="page wide">
      <PageHeader eyebrow="Operations / trade routes" title="Haul for the journey." body="Build a continuous multi-stop cargo run with varied commodities and dependable markets. Profit still matters, but it no longer controls the mission." />
      <section className="planner-panel">
        <SearchFields draft={draft} update={update} />
        <button className="primary search-button" disabled={search.isPending || !draft.originSystemId64} onClick={() => search.mutate()}>
          {search.isPending ? <RefreshCw className="spin" size={17} /> : <Map size={17} />}
          {search.isPending ? "Building cargo circuit…" : "Generate trade routes"}
        </button>
      </section>
      {search.error && <Notice tone="warning">{search.error.message}</Notice>}
      <section className="immersive-routes">
        {search.data?.routes.map((route, index) => (
          <article className="route-mission" key={`${route.name}-${index}`}>
            <div className="mission-code">LOG-{String(index + 1).padStart(2, "0")}</div>
            <div><span className="eyebrow">Independent haulage contract</span><h2>{route.name}</h2><p>{route.legs.length} deliveries · {route.cargo_variety} cargo types · {route.total_distance_ly} ly</p></div>
            <div className="mission-total"><span>Projected earnings</span><strong>+{formatCredits(route.total_profit)}</strong><small>{formatTime(route.estimated_seconds)} · {route.estimated_jumps} jumps</small></div>
            <button className="primary" onClick={() => setBoard(route)}>Accept route</button>
          </article>
        ))}
        {search.data?.routes.length === 0 && <EmptyState title="No continuous route found" body="Increase the search radius, allow older market reports, or add regional data coverage." icon={Map} />}
        {!search.data && <EmptyState title="Your next haul starts here" body="Trade Routes are designed as multi-stop assignments you can fly alone or share with a wing. Group coordination will build on this foundation later." icon={Map} />}
      </section>
      {board && <FlightBoard title={board.name} legs={board.legs} summary={{ profit: board.total_profit, seconds: board.estimated_seconds, distance: board.total_distance_ly, jumps: board.estimated_jumps }} onClose={() => setBoard(null)} />}
    </div>
  );
}

function TransitPage({ draft, update }: { draft: SearchDraft; update: (patch: Partial<SearchDraft>) => void }) {
  const [jobId, setJobId] = useState<string | null>(null);
  const [board, setBoard] = useState<TransitSummary | null>(null);
  const start = useMutation({
    mutationFn: () => api.startTransit(draft),
    onSuccess: (value) => setJobId(value.job_id),
  });
  const job = useQuery({
    queryKey: ["job", jobId],
    queryFn: () => api.job(jobId!),
    enabled: Boolean(jobId),
    refetchInterval: (query) => (query.state.data?.status === "complete" || query.state.data?.status === "failed" ? false : 800),
  });
  const result = job.data?.status === "complete" ? (job.data.result as TransitResult) : undefined;
  const options = useMemo(() => result ? [result.direct, ...result.options] : [], [result]);
  return (
    <div className="page wide">
      <PageHeader eyebrow="Travel / profitable transit" title="Earn while you relocate." body="Balance forward progress with worthwhile cargo stops, then compare every plan against going direct." />
      <section className="planner-panel">
        <SearchFields draft={draft} update={update} transit />
        <button
          className="primary search-button"
          disabled={start.isPending || !draft.originSystemId64 || !draft.destinationSystemId64}
          onClick={() => start.mutate()}
        >
          {(start.isPending || job.data?.status === "running") ? <RefreshCw className="spin" size={17} /> : <Route size={17} />}
          {job.data?.status === "running" ? "Exploring trade corridors…" : "Plan profitable transit"}
        </button>
      </section>
      {(start.error || job.data?.error) && <Notice tone="warning">{start.error?.message ?? job.data?.error}</Notice>}
      {result && (
        <section className="transit-results">
          <div className="results-heading"><h2>Direct versus profitable travel</h2><span>20% maximum detour · up to 6 cargo stops</span></div>
          <div className="transit-grid">
            {options.map((option) => <TransitCard key={option.profile} option={option} featured={option.profile === "Balanced"} onOpen={setBoard} />)}
          </div>
          {result.options.length === 0 && <Notice tone="warning">No valid cargo sale was found in the current corridor data. Cache a regional sector covering this journey, increase the market-age limit, or allow a larger station distance. The direct plan remains safe to use.</Notice>}
        </section>
      )}
      {!jobId && <EmptyState title="Two destinations. Three trade-offs." body="Fast minimizes delay. Balanced protects progress and profit. Profit accepts more travel when the credits justify it." icon={Route} />}
      {board && <FlightBoard title={`${board.profile} transit plan`} legs={board.legs} summary={{ profit: board.expected_profit, seconds: board.estimated_seconds, distance: board.total_distance_ly, jumps: board.estimated_jumps }} preflight={board.positioning_station ? `POSITION EMPTY TO ${board.positioning_station}, ${board.positioning_system}, THEN LOAD THE FIRST CARGO ORDER.` : undefined} onClose={() => setBoard(null)} />}
    </div>
  );
}

function ShipsPage({ draft, update }: { draft: SearchDraft; update: (patch: Partial<SearchDraft>) => void }) {
  const queryClient = useQueryClient();
  const profiles = useQuery({ queryKey: ["profiles"], queryFn: api.profiles });
  const [form, setForm] = useState<Omit<ShipProfile, "id">>({
    name: "Type-6 — Cargo",
    ship_model: "Type-6 Transporter",
    cargo_capacity: 104,
    unladen_jump_range: 24.7,
    laden_jump_range: 18.7,
    pad_size: "M",
    has_fuel_scoop: true,
    shielded: true,
    notes: "",
  });
  const create = useMutation({
    mutationFn: () => api.createProfile(form),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["profiles"] }),
  });
  const chooseModel = (model: string) => {
    const ship = SHIP_CATALOG.find((item) => item.model === model);
    if (!ship) return;
    setForm({
      ...form,
      name: `${ship.model} — Cargo`,
      ship_model: ship.model,
      cargo_capacity: Math.round(ship.cargoBuild * 0.82),
      unladen_jump_range: ship.balancedRange,
      laden_jump_range: ship.cargoRange,
      pad_size: ship.pad,
      has_fuel_scoop: true,
      shielded: true,
      notes: `${ship.role}; editable planning baseline.`,
    });
  };
  const remove = useMutation({
    mutationFn: api.deleteProfile,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["profiles"] }),
  });
  return (
    <div className="page narrow">
      <PageHeader eyebrow="Fleet / ship profiles" title="Use the ship you actually fly." body="Profiles store derived hauling limits. Module-level outfitting stays out of v1." />
      <div className="profile-grid">
        {profiles.data?.map((profile) => (
          <article className="profile-card" key={profile.id}>
            <Ship size={24} />
            <div><span>{profile.ship_model}</span><h3>{profile.name}</h3><p>{profile.cargo_capacity} t · {profile.laden_jump_range} ly laden · {profile.pad_size} pad</p></div>
            <button className="secondary" onClick={() => update({ cargoCapacity: profile.cargo_capacity, ladenJumpRange: profile.laden_jump_range, padSize: profile.pad_size })}>Use profile</button>
            <button className="icon-button danger" aria-label={`Delete ${profile.name}`} onClick={() => remove.mutate(profile.id)}><X size={16} /></button>
          </article>
        ))}
      </div>
      <section className="planner-panel">
        <h2>Create a profile</h2>
        <div className="form-grid two">
          <label className="field"><span>Profile name</span><input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
          <label className="field"><span>Ship model</span><select value={form.ship_model} onChange={(e) => chooseModel(e.target.value)}>{SHIP_CATALOG.map((ship) => <option key={ship.model}>{ship.model}</option>)}</select></label>
        </div>
        <div className="form-grid four">
          <label className="field"><span>Cargo</span><input type="number" value={form.cargo_capacity} onChange={(e) => setForm({ ...form, cargo_capacity: Number(e.target.value) })} /></label>
          <label className="field"><span>Unladen range</span><input type="number" value={form.unladen_jump_range} onChange={(e) => setForm({ ...form, unladen_jump_range: Number(e.target.value) })} /></label>
          <label className="field"><span>Laden range</span><input type="number" value={form.laden_jump_range} onChange={(e) => setForm({ ...form, laden_jump_range: Number(e.target.value) })} /></label>
          <label className="field"><span>Pad</span><select value={form.pad_size} onChange={(e) => setForm({ ...form, pad_size: e.target.value as "S" | "M" | "L" })}><option>S</option><option>M</option><option>L</option></select></label>
        </div>
        <button className="primary" onClick={() => create.mutate()}><Ship size={17} /> Save profile</button>
      </section>
    </div>
  );
}

function ShipOptimizationsPage({ draft, update }: { draft: SearchDraft; update: (patch: Partial<SearchDraft>) => void }) {
  const [model, setModel] = useState("Type-6 Transporter");
  const [mode, setMode] = useState<OptimizationMode>("Balanced");
  const ship = SHIP_CATALOG.find((item) => item.model === model)!;
  const result = optimizeShip(ship, mode);
  return (
    <div className="page narrow">
      <PageHeader eyebrow="Outfitting / planning" title="Choose what your ship is for." body="Compare practical hauling priorities before committing credits in outfitting. These are planning baselines, not exact module builds." />
      <section className="planner-panel optimization-console">
        <div className="form-grid two">
          <label className="field"><span>Ship model</span><select value={model} onChange={(e) => setModel(e.target.value)}>{SHIP_CATALOG.map((item) => <option key={item.model}>{item.model}</option>)}</select></label>
          <label className="field"><span>Optimization</span><select value={mode} onChange={(e) => setMode(e.target.value as OptimizationMode)}>{["Balanced", "Cargo first", "Range first", "Safety first"].map((item) => <option key={item}>{item}</option>)}</select></label>
        </div>
        <div className="optimization-readout">
          <div><span>Recommended cargo</span><strong>{result.cargo} t</strong></div>
          <div><span>Estimated laden range</span><strong>{result.ladenRange} ly</strong></div>
          <div><span>Shield posture</span><strong>{result.shields}</strong></div>
          <div><span>Fuel scoop</span><strong>{result.scoop}</strong></div>
        </div>
        <Notice>{result.note} Verify exact numbers in the in-game outfitting screen after choosing modules and engineering.</Notice>
        <div className="module-groups">
          {[
            ["Core internal", result.core],
            ["Optional internal", result.optional],
            ["Utility mounts", result.utilities],
            ["Hardpoints", result.hardpoints],
          ].map(([label, modules]) => (
            <section className="module-group" key={label as string}>
              <div className="module-group-title"><span>{label as string}</span><b>{(modules as typeof result.core).length} SLOTS</b></div>
              <div className="module-list">
                {(modules as typeof result.core).map((module) => (
                  <article key={module.slot}>
                    <div><span>{module.slot}</span><strong>{module.module}</strong></div>
                    <p>{module.purpose}</p>
                  </article>
                ))}
              </div>
            </section>
          ))}
        </div>
        <button className="primary" onClick={() => update({ cargoCapacity: result.cargo, ladenJumpRange: result.ladenRange, padSize: ship.pad })}><Wrench size={17} /> Use these planning limits</button>
      </section>
    </div>
  );
}

function formatBytes(value = 0) {
  if (!value) return "Unknown";
  const units = ["B", "KB", "MB", "GB"];
  const index = Math.min(units.length - 1, Math.floor(Math.log(value) / Math.log(1024)));
  return `${(value / 1024 ** index).toFixed(index > 1 ? 1 : 0)} ${units[index]}`;
}

function DataPage({ draft, update }: { draft: SearchDraft; update: (patch: Partial<SearchDraft>) => void }) {
  const queryClient = useQueryClient();
  const [jobId, setJobId] = useState<string | null>(null);
  const [mode, setMode] = useState(() => localStorage.getItem("elite-logistics-data-mode") ?? "live");
  const [sectorRadius, setSectorRadius] = useState(100);
  const status = useQuery({ queryKey: ["data-status"], queryFn: api.dataStatus });
  const packInfo = useQuery({ queryKey: ["pack-info"], queryFn: api.packInfo, staleTime: 60 * 60 * 1000 });
  const start = useMutation({
    mutationFn: (download: boolean) => api.startImport(download),
    onSuccess: (result) => setJobId(result.job_id),
  });
  const job = useQuery({
    queryKey: ["job", jobId],
    queryFn: () => api.job(jobId!),
    enabled: Boolean(jobId),
    refetchInterval: (query) => (["complete", "failed"].includes(query.state.data?.status ?? "") ? false : 1000),
  });
  const region = useMutation({
    mutationFn: () => api.cacheRegion({ ...draft, maxSystemDistanceLy: sectorRadius }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["data-status"] }),
  });
  const chooseMode = (value: string) => {
    setMode(value);
    localStorage.setItem("elite-logistics-data-mode", value);
  };
  useEffect(() => {
    if (job.data?.status === "complete") queryClient.invalidateQueries({ queryKey: ["data-status"] });
  }, [job.data?.status, queryClient]);
  return (
    <div className="page narrow">
      <PageHeader eyebrow="Data / coverage" title="Know what your route knows." body="Prices are observations. Freshness and coverage are part of every recommendation." />
      <div className="data-cards">
        <article><Database size={21} /><span>Systems</span><strong>{status.data?.systems.toLocaleString() ?? "—"}</strong></article>
        <article><PackageSearch size={21} /><span>Stations</span><strong>{status.data?.stations.toLocaleString() ?? "—"}</strong></article>
        <article><Gauge size={21} /><span>Market prices</span><strong>{status.data?.market_observations.toLocaleString() ?? "—"}</strong></article>
      </div>
      <section className="data-mode-grid">
        {[
          ["live", "Live lookup", "Smallest storage. Pull fresh markets as you search and keep a compact working cache."],
          ["regional", "Regional sectors", "Download larger chunks around where you are for predictable local and offline planning."],
          ["full", "Full galaxy archive", "Maximum coverage and disk use. Best for long-distance planning across unfamiliar space."],
        ].map(([value, title, body]) => (
          <button className={`data-mode ${mode === value ? "active" : ""}`} key={value} onClick={() => chooseMode(value)}>
            <span>{mode === value ? "ACTIVE MODE" : "DATA MODE"}</span><strong>{title}</strong><p>{body}</p>
          </button>
        ))}
      </section>
      {mode === "regional" && (
        <section className="planner-panel">
          <span className="eyebrow">Sector cache / current position</span>
          <h2>Cache a region around {draft.originLocationLabel || "your selected system"}</h2>
          <div className="form-grid two">
            <label className="field"><span>Sector radius</span><select value={sectorRadius} onChange={(e) => setSectorRadius(Number(e.target.value))}><option value={50}>Local sector · 50 ly</option><option value={100}>Trade sector · 100 ly</option><option value={250}>Travel sector · 250 ly</option></select></label>
            <label className="field"><span>Current location</span><input readOnly value={draft.originLocationLabel || "Choose your location in a planner first"} /></label>
          </div>
          <button className="primary" disabled={!draft.originSystemId64 || region.isPending} onClick={() => { update({ maxSystemDistanceLy: sectorRadius }); region.mutate(); }}>
            {region.isPending ? <RefreshCw className="spin" size={17} /> : <Database size={17} />}
            {region.isPending ? "Caching regional markets…" : `Cache ${sectorRadius} ly sector`}
          </button>
          {region.data && <Notice>{region.data.imported.toLocaleString()} regional market candidates added to the local cache.</Notice>}
          {region.error && <Notice tone="warning">{region.error.message}</Notice>}
        </section>
      )}
      {mode === "full" && (
      <section className="planner-panel">
        <span className="eyebrow">Optional offline coverage</span>
        <h2>Spansh station data pack</h2>
        <p className="muted">The full archive is streamed into the local index without expanding the whole file. Interrupted downloads resume from the saved chunk. Download size: <strong>{formatBytes(packInfo.data?.bytes)}</strong>. Saved download: <strong>{formatBytes(status.data?.pack_bytes || status.data?.partial_pack_bytes)}</strong>. Indexed database: <strong>{formatBytes(status.data?.database_bytes)}</strong>.</p>
        <div className="pack-path">{status.data?.pack_path}</div>
        <button className="primary" disabled={start.isPending || job.data?.status === "running"} onClick={() => start.mutate(!status.data?.pack_installed)}>
          {job.data?.status === "running" ? <RefreshCw className="spin" size={17} /> : <Database size={17} />}
          {job.data?.status === "running" ? `${(job.data.result as any)?.phase ?? "Preparing data"}… ${Math.round((job.data.progress ?? 0) * 100)}%` : status.data?.pack_installed ? "Import data pack" : "Download and import data pack"}
        </button>
        {job.data?.status === "running" && (job.data.result as any)?.downloaded_bytes && (
          <div className="download-telemetry">
            <span>{formatBytes((job.data.result as any).downloaded_bytes)} / {formatBytes((job.data.result as any).total_bytes)}</span>
            <span>{formatBytes((job.data.result as any).speed_bps)}/s</span>
            <span>ETA {formatTime((job.data.result as any).eta_seconds ?? 0)}</span>
          </div>
        )}
        {!status.data?.pack_installed && <Notice>The optional pack is very large. This action downloads it directly from Spansh, then builds the local index.</Notice>}
        {job.data?.status === "complete" && <Notice>Import complete. Local route searches now use the updated market index.</Notice>}
        {job.data?.status === "failed" && <Notice tone="warning">{job.data.error}</Notice>}
      </section>
      )}
      {mode === "live" && <Notice>Live lookup is active. Searches request fresh regional candidates only when needed and retain a small local cache for repeat use.</Notice>}
      <Notice>Community market data can change before you arrive. Confidence is reduced using observation age, supply, demand, and estimated arrival time.</Notice>
    </div>
  );
}
