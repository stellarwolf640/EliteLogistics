import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Cable,
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
  Settings,
  Bot,
  Keyboard,
  ShieldCheck,
  RotateCcw,
  Terminal,
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
  elitePlanningPatch,
  formatCredits,
  formatTime,
} from "./components";
import type { BindingCapability, ComputerInvocation, ComputerPreferences, EliteStatus, ImmersiveTradeRoute, JobResponse, Preferences, RoundTrip, SearchDraft, ShipProfile, TradeLeg, TransitResult, TransitSummary } from "./types";
import { useSearchDraft } from "./useSearchDraft";
import { optimizeShip, SHIP_CATALOG, type OptimizationMode } from "./shipCatalog";
import { connectQueryEvents } from "./events";
import { desktopCall } from "./desktopBridge";

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
  "/computer": ["HOME", "COMPUTER"],
  "/settings": ["HOME", "ION SETTINGS"],
};

const breadcrumbTargets: Record<string, string> = {
  HOME: "/",
  "TRADE OPERATIONS": "/operations",
  "BEST TRADES": "/trade",
  "ROUND TRIPS": "/round-trips",
  "TRADE ROUTES": "/trade-routes",
  NAVIGATION: "/navigation",
  "PROFITABLE TRANSIT": "/transit",
  "FLEET MANAGEMENT": "/fleet",
  "SHIP PROFILES": "/ships",
  "SHIP OPTIMIZATIONS": "/ship-optimizations",
  "DATA NETWORK": "/data",
  COMPUTER: "/computer",
  "ION SETTINGS": "/settings",
};

export function eliteLinkVisual(elite?: EliteStatus) {
  if (!elite?.enabled) {
    return { className: "", compactLabel: "DISABLED", detailLabel: "LINK DISABLED" };
  }
  if (elite.state.game_running) {
    return { className: "live", compactLabel: "LIVE", detailLabel: "LIVE TELEMETRY" };
  }
  if (elite.state.available) {
    return { className: "ready", compactLabel: "LINKED", detailLabel: "LINK ACTIVE" };
  }
  return { className: "", compactLabel: "NO SIGNAL", detailLabel: "NO JOURNAL" };
}

export default function App() {
  const path = usePath();
  const { draft, setDraft } = useSearchDraft();
  const queryClient = useQueryClient();
  const [computerCard, setComputerCard] = useState<{ title: string; body: string; tone: string } | null>(null);
  useEffect(() => connectQueryEvents(queryClient), [queryClient]);
  const update = (patch: Partial<SearchDraft>) => setDraft((current) => ({ ...current, ...patch }));
  useEffect(() => {
    const handle = (event: Event) => {
      const detail = (event as CustomEvent).detail as {
        action?: string;
        path?: string;
        fields?: Partial<SearchDraft>;
        filters?: Partial<SearchDraft>;
        title?: string;
        body?: string;
        tone?: string;
      };
      if (detail.action === "navigate" && detail.path) navigateTo(detail.path);
      if (detail.action === "open_route_console") void desktopCall("open_route_console");
      if (detail.action === "populate_planner" && detail.fields) update(detail.fields);
      if (detail.action === "change_filters" && detail.filters) update(detail.filters);
      if (detail.action === "show_information_card" && detail.body) {
        setComputerCard({
          title: detail.title || "Computer",
          body: detail.body,
          tone: detail.tone || "information",
        });
      }
    };
    window.addEventListener("ion:computer-interface", handle);
    return () => window.removeEventListener("ion:computer-interface", handle);
  }, []);
  const status = useQuery({ queryKey: ["data-status"], queryFn: api.dataStatus });
  const elite = useQuery({
    queryKey: ["elite-status"],
    queryFn: api.eliteStatus,
  });
  useEffect(() => {
    const connection = elite.data;
    const state = connection?.state;
    if (!connection?.enabled || !connection.auto_apply_planning_state || !state?.available || !state.system_id64) return;
    setDraft((current) => {
      const next = {
        ...current,
        ...elitePlanningPatch(state),
      };
      return JSON.stringify(next) === JSON.stringify(current) ? current : next;
    });
  }, [elite.data, setDraft]);
  if (path === "/flight-board") {
    return <PersistedRouteConsole />;
  }

  return (
    <div className="app-shell">
      <DesktopFrame />
      <main>
        <ConsoleHeader path={path} observations={status.data?.market_observations ?? 0} elite={elite.data} />
        {path === "/" && <Dashboard status={status.data} draft={draft} elite={elite.data} />}
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
        {path === "/computer" && <ComputerPage />}
        {path === "/settings" && <SettingsPage />}
        {!routeLabels[path] && <Dashboard status={status.data} draft={draft} />}
        {computerCard && (
          <aside className={`computer-information-card ${computerCard.tone}`}>
            <span className="eyebrow">ION Computer</span>
            <h2>{computerCard.title}</h2>
            <p>{computerCard.body}</p>
            <button className="secondary" onClick={() => setComputerCard(null)}>Dismiss</button>
          </aside>
        )}
      </main>
    </div>
  );
}

export function ConsoleHeader({ path, observations, elite }: { path: string; observations: number; elite?: EliteStatus }) {
  const trail = routeLabels[path] ?? ["HOME"];
  const gameLink = eliteLinkVisual(elite);
  return (
    <header className="console-header">
      <button className="console-brand" onClick={() => navigateTo("/")}>
        <span className="ion-monogram">ION</span>
        <div><strong>INTRASTELLAR OPERATIONS NETWORK</strong><span>PROVIDED BY INTRASTELLAR LOGISTICS · ISL</span></div>
      </button>
      <div className="breadcrumb">
        {trail.map((label, index) => {
          const active = index === trail.length - 1;
          return <button key={label} className={active ? "active" : ""} disabled={active} onClick={() => navigateTo(breadcrumbTargets[label] ?? "/")}>{label}</button>;
        })}
      </div>
      <div className="header-links">
        <div className="console-status"><span className={observations ? "online" : ""} /><div><b>MARKET LINK</b><small>{observations.toLocaleString()} RECORDS</small></div></div>
        <div className="console-status"><span className={gameLink.className === "live" ? "online" : gameLink.className === "ready" ? "standby" : ""} /><div><b>GAME LINK</b><small>{gameLink.compactLabel}</small></div></div>
      </div>
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

function PersistedRouteConsole() {
  const operation = useQuery({ queryKey: ["active-operation"], queryFn: api.activeOperation });
  if (operation.isLoading) return <><DesktopFrame routeConsole /><div className="route-console-loading">RESTORING ACTIVE OPERATION…</div></>;
  if (!operation.data) return <><DesktopFrame routeConsole /><div className="route-console-empty"><EmptyState title="No active operation" body="Open a route from the main ION window to populate this console." icon={Route} /></div></>;
  return <><DesktopFrame routeConsole /><FlightBoard {...operation.data.route_payload} activatedAt={operation.data.activated_at} initialManualStep={operation.data.manual_progress} allowPopout={false} onClose={() => void desktopCall("close_route_console")} /></>;
}

function DesktopFrame({ routeConsole = false }: { routeConsole?: boolean }) {
  const [desktop, setDesktop] = useState(Boolean(window.pywebview?.api));
  const preferences = useQuery({ queryKey: ["preferences"], queryFn: api.preferences });
  const queryClient = useQueryClient();
  useEffect(() => {
    const ready = () => setDesktop(true);
    window.addEventListener("pywebviewready", ready);
    return () => window.removeEventListener("pywebviewready", ready);
  }, []);
  if (!desktop) return null;
  return (
    <div className="desktop-frame">
      <div className="desktop-drag-region pywebview-drag-region">
        <span>ION</span><b>{routeConsole ? "ACTIVE ROUTE CONSOLE" : "INTRASTELLAR OPERATIONS NETWORK"}</b>
      </div>
      {routeConsole && <>
        <button aria-label="Toggle always on top" title="Always on top" onClick={() => {
          const enabled = !(preferences.data?.route_always_on_top ?? false);
          void desktopCall("set_route_always_on_top", enabled).then(() => queryClient.invalidateQueries({ queryKey: ["preferences"] }));
        }}>{preferences.data?.route_always_on_top ? "UNPIN" : "PIN"}</button>
        <button aria-label="Toggle fullscreen" title="Fullscreen" onClick={() => {
          const enabled = !(preferences.data?.route_fullscreen ?? false);
          void desktopCall("set_route_fullscreen", enabled).then(() => queryClient.invalidateQueries({ queryKey: ["preferences"] }));
        }}>{preferences.data?.route_fullscreen ? "WINDOW" : "FULL"}</button>
      </>}
      {!routeConsole && <button aria-label="Minimize ION" onClick={() => void desktopCall("minimize")}>—</button>}
      {!routeConsole && <button aria-label="Maximize or restore ION" onClick={() => void desktopCall("toggle_maximize")}>□</button>}
      <button className="desktop-close" aria-label={`Close ${routeConsole ? "route console" : "ION"}`} onClick={() => void desktopCall(routeConsole ? "close_route_console" : "close")}>×</button>
    </div>
  );
}

function SearchDataNotice({ assumptions }: { assumptions?: string[] }) {
  const message = [...(assumptions ?? [])].reverse().find((item) =>
    /Refreshed|local data pack|Live Spansh/i.test(item)
  );
  if (!message) return null;
  const warning = /unavailable|current cache|could not/i.test(message);
  return <Notice tone={warning ? "warning" : "info"}>{message}</Notice>;
}

function Dashboard({ status, draft, elite }: { status?: Awaited<ReturnType<typeof api.dataStatus>>; draft: SearchDraft; elite?: EliteStatus }) {
  const navigate = useNavigate();
  const available = Math.max(0, draft.credits - draft.rebuyReserve - draft.cashReserve);
  return (
    <div className="page console-home">
      <section className="brand-masthead" aria-label="ION — IntraStellar Operations Network">
        <img src="/branding/ion-logo.png" alt="ION — IntraStellar Operations Network, provided by IntraStellar Logistics" />
      </section>
      <section className="commander-strip">
        <div><span>{elite?.enabled && elite.state.commander ? `CMDR ${elite.state.commander}` : "COMMANDER STATE"}</span><strong>{draft.originLocationLabel || "LOCATION NOT SET"}</strong></div>
        <div><span>ACTIVE VESSEL</span><strong>{elite?.enabled && elite.state.ship_name ? `${elite.state.ship_name} · ` : ""}{draft.cargoCapacity} T · {draft.ladenJumpRange.toFixed(1)} LY</strong></div>
        <div><span>AVAILABLE CAPITAL</span><strong>{formatCredits(available)}</strong></div>
        <div><span>DATA COVERAGE</span><strong>{status?.systems.toLocaleString() ?? 0} SYSTEMS</strong></div>
      </section>
      <div className="console-intro"><span>ION OPERATIONS SERVICES</span><h1>SELECT A SERVICE</h1><p>Commander logistics, navigation, fleet outfitting, and market intelligence provided by IntraStellar Logistics.</p></div>
      <section className="service-grid">
        <ServiceTile index="01" icon={Truck} title="Trade Operations" body="Commodity trades, closed loops, and immersive multi-stop cargo contracts." meta="3 SERVICES" onClick={() => navigate("/operations")} featured />
        <ServiceTile index="02" icon={Route} title="Navigation" body="Plan direct and profitable travel across populated space." meta="1 SERVICE" onClick={() => navigate("/navigation")} />
        <ServiceTile index="03" icon={Ship} title="Fleet Management" body="Store ship profiles and plan complete role-specific module loadouts." meta="2 SERVICES" onClick={() => navigate("/fleet")} />
        <ServiceTile index="04" icon={Database} title="Data Network" body="Control live, regional, and full-galaxy market coverage." meta={`${status?.market_observations.toLocaleString() ?? 0} RECORDS`} onClick={() => navigate("/data")} />
        <ServiceTile index="05" icon={Bot} title="Computer" body="Configure Computer policy, inspect Elite bindings, and run safe ION awareness tools." meta="COMMAND FOUNDATION" onClick={() => navigate("/computer")} featured />
        <ServiceTile index="06" icon={Settings} title="ION Settings" body="Desktop behavior, route-console display, updates, and local diagnostics." meta="SYSTEM CONTROL" onClick={() => navigate("/settings")} />
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
        <SearchDataNotice assumptions={search.data?.assumptions} />
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
        <SearchDataNotice assumptions={search.data?.assumptions} />
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
        <SearchDataNotice assumptions={search.data?.assumptions} />
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
  const preferences = useQuery({ queryKey: ["preferences"], queryFn: api.preferences });
  const [mode, setMode] = useState("live");
  const [sectorRadius, setSectorRadius] = useState(100);
  const status = useQuery({ queryKey: ["data-status"], queryFn: api.dataStatus });
  const elite = useQuery({ queryKey: ["elite-status"], queryFn: api.eliteStatus });
  const [eliteDirectory, setEliteDirectory] = useState("");
  const [eliteEnabled, setEliteEnabled] = useState(false);
  const [eliteAutoApply, setEliteAutoApply] = useState(false);
  const packInfo = useQuery({ queryKey: ["pack-info"], queryFn: api.packInfo, staleTime: 60 * 60 * 1000 });
  const start = useMutation({
    mutationFn: (download: boolean) => api.startImport(download),
    onSuccess: (result) => setJobId(result.job_id),
  });
  const job = useQuery({
    queryKey: ["job", jobId],
    queryFn: () => api.job(jobId!),
    enabled: Boolean(jobId),
  });
  const region = useMutation({
    mutationFn: () => api.cacheRegion({ ...draft, maxSystemDistanceLy: sectorRadius }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["data-status"] }),
  });
  const saveElite = useMutation({
    mutationFn: (enabled: boolean) => api.updateEliteSettings({
      enabled,
      journal_directory: eliteDirectory,
      auto_apply_planning_state: eliteAutoApply,
    }),
    onSuccess: (result) => {
      queryClient.setQueryData(["elite-status"], result);
      queryClient.invalidateQueries({ queryKey: ["data-status"] });
      setEliteDirectory(result.configured_directory);
      setEliteEnabled(result.enabled);
      setEliteAutoApply(result.auto_apply_planning_state);
    },
  });
  const chooseMode = (value: string) => {
    setMode(value);
    if (preferences.data && (value === "live" || value === "regional" || value === "full")) {
      void api.updatePreferences({ ...preferences.data, data_mode: value });
    }
  };
  useEffect(() => {
    if (preferences.data) setMode(preferences.data.data_mode);
  }, [preferences.data?.data_mode]);
  useEffect(() => {
    if (job.data?.status === "complete") queryClient.invalidateQueries({ queryKey: ["data-status"] });
  }, [job.data?.status, queryClient]);
  useEffect(() => {
    if (!elite.data) return;
    setEliteDirectory(elite.data.configured_directory);
    setEliteEnabled(elite.data.enabled);
    setEliteAutoApply(elite.data.auto_apply_planning_state);
  }, [elite.data?.configured_directory, elite.data?.enabled, elite.data?.auto_apply_planning_state]);
  const gameLink = eliteLinkVisual(elite.data);
  return (
    <div className="page narrow">
      <PageHeader eyebrow="Data / coverage" title="Know what your route knows." body="Prices are observations. Freshness and coverage are part of every recommendation." />
      <section className="planner-panel elite-link-panel">
        <div className="elite-link-heading">
          <div><span className="eyebrow">Local telemetry / optional</span><h2>Elite Dangerous game link</h2></div>
          <div className={`link-state ${gameLink.className}`}><Cable size={18} /><span>{gameLink.detailLabel}</span></div>
        </div>
        <p className="muted">Read the journal and companion JSON files written by Elite. The game link can update your location, balance, ship limits, cargo, navigation target, and active route progress. Manual planning remains available at all times.</p>
        <div className="form-grid two">
          <label className="field"><span>Elite journal directory</span><div className="path-picker"><input value={eliteDirectory} onChange={(event) => setEliteDirectory(event.target.value)} placeholder="C:\Users\...\Saved Games\Frontier Developments\Elite Dangerous" /><button className="secondary" type="button" onClick={() => void desktopCall<string>("choose_journal_folder").then((path) => path && setEliteDirectory(path))}>Browse…</button></div></label>
          <div className="elite-link-actions">
            {elite.data?.reference_directory && <button className="secondary" onClick={() => setEliteDirectory(elite.data!.reference_directory!)}>Use copied reference data</button>}
            <button className="primary" disabled={saveElite.isPending} onClick={() => { setEliteEnabled(true); saveElite.mutate(true); }}>{saveElite.isPending ? <RefreshCw className="spin" size={17} /> : <Cable size={17} />} Save and activate link</button>
          </div>
        </div>
        <div className="toggle-row">
          <label className="toggle"><input type="checkbox" checked={eliteEnabled} disabled={saveElite.isPending} onChange={(event) => { const enabled = event.target.checked; setEliteEnabled(enabled); saveElite.mutate(enabled); }} /><span className="switch">●</span>Game-file integration active</label>
          <label className="toggle"><input type="checkbox" checked={eliteAutoApply} onChange={(event) => setEliteAutoApply(event.target.checked)} /><span className="switch">●</span>Use game state in planning forms</label>
        </div>
        {elite.data?.state.available && (
          <div className="elite-readout">
            <div><span>Commander</span><strong>{elite.data.state.commander ? `CMDR ${elite.data.state.commander}` : "Unknown"}</strong></div>
            <div><span>Position</span><strong>{elite.data.state.station_name ? `${elite.data.state.station_name}, ` : ""}{elite.data.state.system_name ?? "Unknown"}</strong></div>
            <div><span>Vessel</span><strong>{elite.data.state.ship_name || elite.data.state.ship_model || "Unknown"}</strong></div>
            <div><span>Flight state</span><strong>{elite.data.state.phase.replaceAll("_", " ")}</strong></div>
          </div>
        )}
        {elite.data?.state.warnings.map((warning) => <Notice key={warning} tone="warning">{warning}</Notice>)}
        {saveElite.error && <Notice tone="warning">{saveElite.error.message}</Notice>}
      </section>
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

export function ComputerPage() {
  const queryClient = useQueryClient();
  const status = useQuery({ queryKey: ["computer-status"], queryFn: api.computerStatus });
  const tools = useQuery({ queryKey: ["computer-tools"], queryFn: api.computerTools });
  const controls = useQuery({ queryKey: ["computer-controls"], queryFn: api.computerControls });
  const bindings = useQuery({ queryKey: ["computer-bindings"], queryFn: api.computerBindings });
  const invocations = useQuery({ queryKey: ["computer-invocations"], queryFn: api.computerInvocations });
  const [result, setResult] = useState<ComputerInvocation | null>(null);
  const [bindingsDirectory, setBindingsDirectory] = useState("");
  const save = useMutation({
    mutationFn: api.updateComputerSettings,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["computer-status"] });
      void queryClient.invalidateQueries({ queryKey: ["preferences"] });
      void queryClient.invalidateQueries({ queryKey: ["computer-bindings"] });
    },
  });
  const reset = useMutation({
    mutationFn: api.resetComputerSettings,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["computer-status"] });
      void queryClient.invalidateQueries({ queryKey: ["preferences"] });
      void queryClient.invalidateQueries({ queryKey: ["computer-bindings"] });
    },
  });
  const invoke = useMutation({
    mutationFn: ({ name, args = {} }: { name: string; args?: Record<string, unknown> }) =>
      api.invokeComputerTool(name, args),
    onSuccess: (value) => {
      setResult(value);
      void queryClient.invalidateQueries({ queryKey: ["computer-invocations"] });
    },
  });
  const resolve = useMutation({
    mutationFn: ({ id, approve }: { id: string; approve: boolean }) =>
      api.resolveComputerConfirmation(id, approve),
    onSuccess: (value) => {
      setResult(value);
      void queryClient.invalidateQueries({ queryKey: ["computer-invocations"] });
    },
  });
  const settings = status.data?.settings;
  useEffect(() => {
    if (settings) setBindingsDirectory(settings.bindings_directory);
  }, [settings?.bindings_directory]);
  const patch = (change: Partial<ComputerPreferences>) => {
    if (settings) save.mutate({ ...settings, ...change });
  };
  const setMode = (mode: ComputerPreferences["mode"]) => {
    patch({ mode, enabled: mode !== "off" });
  };
  const toggleAction = (actionId: string, enabled: boolean) => {
    if (!settings) return;
    const actions = enabled
      ? [...new Set([...settings.enabled_game_actions, actionId])]
      : settings.enabled_game_actions.filter((value) => value !== actionId);
    patch({ enabled_game_actions: actions });
  };
  const runArguments: Record<string, Record<string, unknown>> = {
    open_ion_view: { view: "home" },
    show_information_card: {
      title: "Computer link test",
      body: "The policy-gated ION interface channel is responding.",
      tone: "success",
    },
  };
  const bindingByAction = new globalThis.Map<string, BindingCapability>(
    (bindings.data?.capabilities ?? []).map((capability) => [capability.action_id, capability]),
  );
  const runnableWithoutInput = new Set([
    "get_operational_snapshot",
    "get_ship_state",
    "get_navigation_state",
    "get_cargo_manifest",
    "get_control_capabilities",
    "inspect_current_system",
    "get_active_operation",
    "get_next_instruction",
    "open_route_console",
    "show_diagnostics",
    "open_ion_view",
    "show_information_card",
  ]);

  return (
    <div className="page wide computer-page">
      <PageHeader
        eyebrow="ION / Computer"
        title="Computer policy and capability."
        body="Configure the future assistant, exercise safe ION tools, and verify which Elite controls are actually bound. No game input is sent in this release."
      />
      {status.data?.warnings.map((warning) => <Notice key={warning} tone="warning">{warning}</Notice>)}

      <section className="planner-panel computer-settings">
        <div className="results-heading">
          <div><span className="eyebrow">C1 / runtime policy</span><h2>Computer settings</h2></div>
          <button className="secondary" disabled={reset.isPending} onClick={() => reset.mutate()}><RotateCcw size={16} /> Reset safe defaults</button>
        </div>
        <div className="computer-settings-grid">
          <label className="field"><span>Operating mode</span>
            <select value={settings?.mode ?? "off"} onChange={(event) => setMode(event.target.value as ComputerPreferences["mode"])}>
              <option value="off">Off</option>
              <option value="command">Command foundation · tool console</option>
              <option value="lite" disabled>Lite · not installed</option>
              <option value="enhanced" disabled>Enhanced · not installed</option>
              <option value="automatic" disabled>Automatic · not installed</option>
            </select>
          </label>
          <label className="field"><span>Response detail</span>
            <select value={settings?.verbosity ?? "standard"} onChange={(event) => patch({ verbosity: event.target.value as ComputerPreferences["verbosity"] })}>
              <option value="brief">Brief</option><option value="standard">Standard</option><option value="detailed">Detailed</option><option value="silent">Silent</option>
            </select>
          </label>
          <label className="field"><span>Proactivity</span>
            <select value={settings?.proactivity ?? "critical"} onChange={(event) => patch({ proactivity: event.target.value as ComputerPreferences["proactivity"] })}>
              <option value="silent">Silent</option><option value="critical">Critical only</option><option value="operational">Operational</option><option value="conversational">Conversational</option>
            </select>
          </label>
          <label className="field"><span>Confirmation policy</span>
            <select value={settings?.confirmation_policy ?? "recommended"} onChange={(event) => patch({ confirmation_policy: event.target.value as ComputerPreferences["confirmation_policy"] })}>
              <option value="always">Always confirm controls</option><option value="recommended">Recommended</option><option value="minimal">Minimal</option>
            </select>
          </label>
        </div>
        <label className="toggle"><input type="checkbox" checked={settings?.address_as_commander ?? true} onChange={(event) => patch({ address_as_commander: event.target.checked })} /><span className="switch">●</span>Address me as Commander</label>
        <div className="runtime-strip">
          {Object.entries(status.data?.runtimes ?? {}).map(([name, value]) => <div key={name}><span>{name.replaceAll("_", " ")}</span><strong>{value.replaceAll("_", " ")}</strong></div>)}
        </div>
      </section>

      <section className="planner-panel computer-tool-console">
        <div className="results-heading"><div><span className="eyebrow">C2 / audited execution</span><h2>Safe ION tools</h2></div><Terminal size={24} /></div>
        <p className="muted">Every run passes through policy, uses structured arguments and results, and is written to the local audit log.</p>
        <div className="computer-tools">
          {(tools.data ?? []).map((tool) => (
            <article key={tool.name} className={tool.implementation_status === "available" ? "available" : ""}>
              <div><span>{tool.category} · {tool.permission}</span><h3>{tool.name.replaceAll("_", " ")}</h3><p>{tool.description}</p></div>
              <button
                className="secondary"
                disabled={!settings?.enabled || tool.implementation_status !== "available" || !runnableWithoutInput.has(tool.name) || invoke.isPending}
                onClick={() => invoke.mutate({ name: tool.name, args: runArguments[tool.name] })}
              >{tool.implementation_status === "available" ? "Run" : "Planned"}</button>
            </article>
          ))}
        </div>
        {invoke.error && <Notice tone="warning">{invoke.error.message}</Notice>}
        {result && (
          <div className={`computer-result ${result.status}`}>
            <div className="results-heading"><div><span className="eyebrow">Latest invocation</span><h3>{result.tool_name.replaceAll("_", " ")}</h3></div><strong>{result.status.replaceAll("_", " ")}</strong></div>
            {result.error && <Notice tone="warning">{result.error}</Notice>}
            {result.confirmation_id && result.status === "awaiting_confirmation" && <div className="confirmation-actions"><button className="primary" onClick={() => resolve.mutate({ id: result.confirmation_id!, approve: true })}>Confirm</button><button className="secondary" onClick={() => resolve.mutate({ id: result.confirmation_id!, approve: false })}>Reject</button></div>}
            {result.result && <pre>{JSON.stringify(result.result, null, 2)}</pre>}
          </div>
        )}
      </section>

      <section className="planner-panel bindings-panel">
        <div className="results-heading"><div><span className="eyebrow">C3 / read-only discovery</span><h2>Elite control bindings</h2></div><Keyboard size={24} /></div>
        <div className="path-picker">
          <input value={bindingsDirectory} onChange={(event) => setBindingsDirectory(event.target.value)} placeholder="Default Elite Options\\Bindings folder" />
          <button className="secondary" onClick={() => void desktopCall<string>("choose_bindings_folder").then((path) => path && setBindingsDirectory(path))}>Browse…</button>
          <button className="secondary" disabled={!settings || save.isPending} onClick={() => patch({ bindings_directory: bindingsDirectory })}>Apply</button>
          <button className="secondary" onClick={() => void bindings.refetch()}><RefreshCw size={16} /> Refresh</button>
        </div>
        {bindings.data?.warning && <Notice tone="warning">{bindings.data.warning}</Notice>}
        {bindings.data?.available && <p className="muted">Preset <strong>{bindings.data.preset}</strong> · {bindings.data.file_name} · devices: {bindings.data.device_kinds.join(", ") || "none"} · conflicts: {bindings.data.conflict_count}</p>}

        <div className="class-b-master">
          <div><span className="eyebrow">Class B controls</span><h3>Prepare per-action permissions</h3><p>These switches only define future permissions. The Input Bridge is not installed, so ION cannot press a key or control Elite.</p></div>
          <label className="toggle"><input type="checkbox" checked={settings?.class_b_enabled ?? false} onChange={(event) => patch({ class_b_enabled: event.target.checked })} /><span className="switch">●</span>Class B master switch</label>
        </div>
        <div className="control-capabilities">
          {(controls.data ?? []).map((control) => {
            const capability = bindingByAction.get(control.action_id);
            return <ControlCapabilityRow key={control.action_id} control={control} capability={capability} enabled={settings?.enabled_game_actions.includes(control.action_id) ?? false} onToggle={toggleAction} />;
          })}
        </div>
      </section>

      <section className="planner-panel audit-panel">
        <div className="results-heading"><div><span className="eyebrow">Local audit</span><h2>Recent invocations</h2></div><ShieldCheck size={24} /></div>
        {(invocations.data ?? []).length === 0 && <p className="muted">No Computer tools have been invoked.</p>}
        {(invocations.data ?? []).map((invocation) => <div className="audit-row" key={invocation.id}><span>{new Date(invocation.created_at).toLocaleTimeString()}</span><strong>{invocation.tool_name.replaceAll("_", " ")}</strong><b>{invocation.status.replaceAll("_", " ")}</b></div>)}
      </section>
    </div>
  );
}

function ControlCapabilityRow({ control, capability, enabled, onToggle }: { control: { action_id: string; label: string; permission: string; description: string }; capability?: BindingCapability; enabled: boolean; onToggle: (actionId: string, enabled: boolean) => void }) {
  const binding = capability?.secondary ?? capability?.primary;
  return (
    <article className={`control-row ${control.permission === "game_amber" ? "amber" : "green"} ${capability?.status ?? "unbound"}`}>
      <label className="toggle"><input type="checkbox" checked={enabled} onChange={(event) => onToggle(control.action_id, event.target.checked)} /><span className="switch">●</span></label>
      <div><span>{control.permission === "game_amber" ? "AMBER" : "GREEN"} · {capability?.status ?? "unbound"}</span><h3>{control.label}</h3><p>{control.description}</p></div>
      <div className="binding-readout"><strong>{binding?.display ?? "No binding found"}</strong>{capability?.conflicts.length ? <small>Conflicts: {capability.conflicts.join(", ")}</small> : <small>{capability?.elite_binding ?? "Elite action not found"}</small>}</div>
    </article>
  );
}

function SettingsPage() {
  const queryClient = useQueryClient();
  const preferences = useQuery({ queryKey: ["preferences"], queryFn: api.preferences });
  const diagnostics = useQuery({ queryKey: ["diagnostics"], queryFn: api.diagnostics });
  const updates = useQuery({ queryKey: ["update-status"], queryFn: api.updateStatus });
  const checkUpdate = useMutation({ mutationFn: api.checkUpdates, onSuccess: (value) => queryClient.setQueryData(["update-status"], value) });
  const downloadUpdate = useMutation({ mutationFn: api.downloadUpdate, onSuccess: (value) => queryClient.setQueryData(["update-status"], value) });
  const save = useMutation({
    mutationFn: api.updatePreferences,
    onSuccess: (value) => queryClient.setQueryData(["preferences"], value),
  });
  const patch = (change: Partial<Preferences>) => {
    if (preferences.data) save.mutate({ ...preferences.data, ...change });
  };
  const diagnosticGameLink = eliteLinkVisual(diagnostics.data?.game_link);
  return (
    <div className="page narrow">
      <PageHeader eyebrow="ION / system control" title="Desktop settings." body="Control native window behavior, route-console display, local storage, and diagnostics." />
      <section className="planner-panel settings-grid">
        <div>
          <span className="eyebrow">Window lifecycle</span>
          <h2>When the main window closes</h2>
          <select value={preferences.data?.close_behavior ?? "exit"} onChange={(event) => patch({ close_behavior: event.target.value as "exit" | "tray" })}>
            <option value="exit">Exit ION completely</option>
            <option value="tray">Keep running in the system tray</option>
          </select>
          <p className="muted">Tray mode keeps the game link, active operation, and local events running.</p>
        </div>
        <div>
          <span className="eyebrow">Second screen</span>
          <h2>Route console</h2>
          <div className="toggle-row vertical">
            <label className="toggle"><input type="checkbox" checked={preferences.data?.route_fullscreen ?? false} onChange={(event) => { patch({ route_fullscreen: event.target.checked }); void desktopCall("set_route_fullscreen", event.target.checked); }} /><span className="switch">●</span>Open fullscreen</label>
            <label className="toggle"><input type="checkbox" checked={preferences.data?.route_always_on_top ?? false} onChange={(event) => { patch({ route_always_on_top: event.target.checked }); void desktopCall("set_route_always_on_top", event.target.checked); }} /><span className="switch">●</span>Keep above other windows</label>
          </div>
        </div>
      </section>
      <section className="planner-panel diagnostics">
        <div className="results-heading"><div><span className="eyebrow">Local diagnostics</span><h2>ION {diagnostics.data?.version ?? "—"}</h2></div><button className="secondary" onClick={() => void diagnostics.refetch()}><RefreshCw size={16} /> Refresh</button></div>
        <div className="data-cards">
          <article><Database size={21} /><span>Database</span><strong>{diagnostics.data?.database_ok ? "READY" : "ERROR"}</strong></article>
          <article><Gauge size={21} /><span>WebView2</span><strong>{diagnostics.data?.webview2_available === null ? "BROWSER MODE" : diagnostics.data?.webview2_available ? "READY" : "MISSING"}</strong></article>
          <article><Cable size={21} /><span>Game link</span><strong>{diagnosticGameLink.compactLabel}</strong></article>
        </div>
        <div className="runtime-paths">{Object.entries(diagnostics.data?.runtime_paths ?? {}).map(([name, path]) => <div key={name}><span>{name}</span><code>{path}</code></div>)}</div>
        {diagnostics.data?.recent_errors.length ? <Notice tone="warning">{diagnostics.data.recent_errors.at(-1)}</Notice> : <p className="muted">No recent local errors recorded.</p>}
      </section>
      <section className="planner-panel update-panel">
        <div className="results-heading">
          <div><span className="eyebrow">Stable release channel</span><h2>Application updates</h2></div>
          <button className="secondary" disabled={checkUpdate.isPending} onClick={() => checkUpdate.mutate()}><RefreshCw className={checkUpdate.isPending ? "spin" : ""} size={16} /> Check for updates</button>
        </div>
        <p className="muted">Installed version: {updates.data?.installed_version ?? diagnostics.data?.version ?? "—"}</p>
        {updates.data?.status === "current" && <Notice>ION is current.</Notice>}
        {updates.data?.status === "available" && <div className="update-offer"><h3>ION {updates.data.available_version} is available</h3><pre>{updates.data.release_notes || "A verified stable update is ready."}</pre><button className="primary" onClick={() => downloadUpdate.mutate()}>Download verified update</button></div>}
        {updates.data?.status === "downloading" && <div><progress max={1} value={updates.data.progress} /><p className="muted">{Math.round(updates.data.progress * 100)}% downloaded</p></div>}
        {updates.data?.status === "ready" && <Notice>Update verified and ready. <button className="text-button" onClick={() => void desktopCall("begin_update_installation")}>Install and relaunch</button></Notice>}
        {updates.data?.error && <Notice tone="warning">{updates.data.error}</Notice>}
      </section>
    </div>
  );
}
