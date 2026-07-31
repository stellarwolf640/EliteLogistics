import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowRight,
  Cable,
  Check,
  Clock3,
  Coins,
  Database,
  Gauge,
  MapPin,
  Package,
  RefreshCw,
  Route,
  Search,
  ShieldCheck,
  Sparkles,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "./api";
import { desktopCall, isDesktop } from "./desktopBridge";
import type { Confidence, EliteLiveState, LocationResult, SearchDraft, TradeLeg, TransitSummary } from "./types";

export function formatCredits(value: number) {
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 1, notation: "compact" }).format(value) + " CR";
}

export function formatTime(seconds: number) {
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `~${minutes} min`;
  return `~${Math.floor(minutes / 60)}h ${minutes % 60}m`;
}

export function ConfidenceBadge({ value, score }: { value: Confidence; score?: number }) {
  return (
    <span className={`confidence confidence-${value.toLowerCase()}`}>
      <span className="confidence-dot" />
      {value}{score !== undefined ? ` · ${score}` : ""}
    </span>
  );
}

export function Metric({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof Coins;
  label: string;
  value: string;
}) {
  return (
    <div className="metric">
      <Icon size={17} />
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
      </div>
    </div>
  );
}

export function TradeCard({ leg, onTransit, onOpen }: { leg: TradeLeg; onTransit?: (leg: TradeLeg) => void; onOpen?: (leg: TradeLeg) => void }) {
  return (
    <article className="trade-card">
      <div className="trade-card-top">
        <div>
          <div className="eyebrow">{leg.commodity} · {leg.quantity} t</div>
          <h3>
            {leg.source_system} <ArrowRight size={17} /> {leg.destination_system}
          </h3>
          <p>
            {leg.source_station} to {leg.destination_station}
            {leg.distance_to_route_ly > 0 && ` · starts ${leg.distance_to_route_ly} ly from you`}
          </p>
        </div>
        <div className="profit">
          <strong>+{formatCredits(leg.trip_profit)}</strong>
          <span>
            {formatCredits(leg.distance_to_route_ly > 0 ? leg.first_trip_credits_per_hour : leg.credits_per_hour)}/hr
            {leg.distance_to_route_ly > 0 ? " first trip" : ""}
          </span>
        </div>
      </div>
      <div className="trade-metrics">
        <Metric icon={Route} label="Route" value={`${leg.jumps} jumps · ${leg.system_distance_ly} ly`} />
        <Metric icon={Clock3} label="Estimated" value={formatTime(leg.estimated_seconds)} />
        <Metric icon={Gauge} label="Margin" value={`${leg.profit_per_ton.toLocaleString()} CR/t`} />
        <div className="metric">
          <ShieldCheck size={17} />
          <div>
            <span>Confidence</span>
            <ConfidenceBadge value={leg.confidence} score={leg.confidence_score} />
          </div>
        </div>
      </div>
      <div className="trade-footer">
        <span className="cargo-order"><b>BUY</b> {leg.quantity} t {leg.commodity} at {leg.buy_price.toLocaleString()} CR/t</span>
        <span><b>SELL</b> {leg.commodity} at {leg.sell_price.toLocaleString()} CR/t</span>
        {onOpen && <button className="text-button" onClick={() => onOpen(leg)}>Open flight board</button>}
        {onTransit && (
          <button className="text-button" onClick={() => onTransit(leg)}>
            Trade my way there <ArrowRight size={14} />
          </button>
        )}
      </div>
    </article>
  );
}

export function LocationPicker({
  label,
  value,
  onSelect,
  onClear,
  placeholder = "Search a system or station",
}: {
  label: string;
  value: string;
  onSelect: (result: LocationResult) => void;
  onClear?: () => void;
  placeholder?: string;
}) {
  const [query, setQuery] = useState(value);
  useEffect(() => setQuery(value), [value]);
  const activelySearching = query.trim().length >= 2 && query !== value;
  const locations = useQuery({
    queryKey: ["locations", query],
    queryFn: () => api.locations(query),
    enabled: activelySearching,
  });
  return (
    <label className="field location-field">
      <span>{label}</span>
      <div className="search-input">
        <Search size={16} />
        <input
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            if (!event.target.value) onClear?.();
          }}
          placeholder={placeholder}
          autoComplete="off"
        />
      </div>
      {activelySearching && (
        <div className="location-results">
          {locations.isLoading && <span className="location-note">Searching local data…</span>}
          {locations.data?.map((item) => (
            <button
              key={`${item.kind}-${item.id}`}
              type="button"
              onClick={() => {
                onSelect(item);
                setQuery(item.kind === "station" ? `${item.name}, ${item.system_name}` : item.name);
              }}
            >
              <MapPin size={15} />
              <span><strong>{item.name}</strong><small>{item.subtitle}</small></span>
            </button>
          ))}
          {!locations.isLoading && locations.data?.length === 0 && (
            <span className="location-note">No local match. Import a data pack to add locations.</span>
          )}
        </div>
      )}
    </label>
  );
}

export function SearchFields({
  draft,
  update,
  transit = false,
}: {
  draft: SearchDraft;
  update: (patch: Partial<SearchDraft>) => void;
  transit?: boolean;
}) {
  const elite = useQuery({
    queryKey: ["elite-status"],
    queryFn: api.eliteStatus,
  });
  const [lastFilledAt, setLastFilledAt] = useState<string | null>(null);
  const [autoFilling, setAutoFilling] = useState(false);
  const canAutoFill = Boolean(elite.data?.enabled && elite.data.state.available);
  const autoFill = async () => {
    setAutoFilling(true);
    try {
      const result = await elite.refetch();
      if (!result.data?.enabled || !result.data.state.available) return;
      const patch = elitePlanningPatch(result.data.state, transit);
      if (!Object.keys(patch).length) return;
      update(patch);
      setLastFilledAt(new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }));
    } finally {
      setAutoFilling(false);
    }
  };
  return (
    <>
      <div className="live-data-fill">
        <div>
          <span>Elite game link</span>
          <small>
            {lastFilledAt
              ? `Planning fields updated at ${lastFilledAt}`
              : canAutoFill
                ? "Live commander, vessel, and position data is ready."
                : "Activate the game link to populate these fields."}
          </small>
        </div>
        <button
          className="secondary"
          type="button"
          disabled={!canAutoFill || autoFilling}
          title={canAutoFill ? "Replace supported fields with the latest Elite data" : "Live Elite data is not currently available"}
          onClick={() => void autoFill()}
        >
          {autoFilling ? <RefreshCw className="spin" size={16} /> : <Cable size={16} />}
          {autoFilling ? "Reading live data…" : "Auto-fill with live data"}
        </button>
      </div>
      <div className="form-grid two">
        <LocationPicker
          label={transit ? "Where are you now?" : "Where are you?"}
          value={draft.originLocationLabel || (draft.originSystemId64 ? `System ID ${draft.originSystemId64}` : "")}
          onSelect={(item) =>
            update({
              originSystemId64: String(item.system_id64),
              originStationMarketId: item.kind === "station" ? String(item.id) : "",
              originLocationLabel: item.kind === "station" ? `${item.name}, ${item.system_name}` : item.name,
            })
          }
          onClear={() => update({ originSystemId64: "", originStationMarketId: "", originLocationLabel: "" })}
        />
        {transit && (
          <LocationPicker
            label="Where do you need to go?"
            value={draft.destinationLocationLabel || (draft.destinationSystemId64 ? `System ID ${draft.destinationSystemId64}` : "")}
            onSelect={(item) =>
              update({
                destinationSystemId64: String(item.system_id64),
                destinationStationMarketId: item.kind === "station" ? String(item.id) : "",
                destinationLocationLabel: item.kind === "station" ? `${item.name}, ${item.system_name}` : item.name,
              })
            }
            onClear={() => update({ destinationSystemId64: "", destinationStationMarketId: "", destinationLocationLabel: "" })}
          />
        )}
        {!transit && (
          <NumberField
            label="Look for routes within"
            suffix="ly"
            step={1}
            value={draft.maxSystemDistanceLy}
            onChange={(v) => update({ maxSystemDistanceLy: v })}
          />
        )}
      </div>
      <div className="form-grid four">
        <NumberField label="Cargo capacity" suffix="t" value={draft.cargoCapacity} onChange={(v) => update({ cargoCapacity: v })} />
        <NumberField label="Laden range" suffix="ly" step={0.1} value={draft.ladenJumpRange} onChange={(v) => update({ ladenJumpRange: v })} />
        <NumberField label="Available balance" suffix="CR" value={draft.credits} onChange={(v) => update({ credits: v })} />
        <label className="field">
          <span>Landing pad</span>
          <select value={draft.padSize} onChange={(event) => update({ padSize: event.target.value as "S" | "M" | "L" })}>
            <option value="S">Small</option>
            <option value="M">Medium</option>
            <option value="L">Large</option>
          </select>
        </label>
      </div>
      <details className="advanced">
        <summary>Route limits and risk controls</summary>
        <div className="form-grid four">
          <NumberField label="Rebuy reserve" suffix="CR" value={draft.rebuyReserve} onChange={(v) => update({ rebuyReserve: v })} />
          <NumberField label="Extra cash reserve" suffix="CR" value={draft.cashReserve} onChange={(v) => update({ cashReserve: v })} />
          <NumberField label="Maximum market age" suffix="hours" value={draft.maxMarketAgeHours} onChange={(v) => update({ maxMarketAgeHours: v })} />
          <NumberField label="Maximum station distance" suffix="ls" value={draft.maxStationDistanceLs} onChange={(v) => update({ maxStationDistanceLs: v })} />
        </div>
        <div className="toggle-row">
          <Toggle label="Fleet carriers" checked={draft.includeFleetCarriers} onChange={(v) => update({ includeFleetCarriers: v })} />
          <Toggle label="Planetary stations" checked={draft.includePlanetary} onChange={(v) => update({ includePlanetary: v })} />
          <Toggle label="Odyssey settlements" checked={draft.includeOdyssey} onChange={(v) => update({ includeOdyssey: v })} />
          <Toggle label="Hide low confidence" checked={draft.hideLowConfidence} onChange={(v) => update({ hideLowConfidence: v })} />
        </div>
      </details>
    </>
  );
}

export function elitePlanningPatch(state: EliteLiveState, transit = false): Partial<SearchDraft> {
  const patch: Partial<SearchDraft> = {};
  if (state.system_id64) {
    patch.originSystemId64 = String(state.system_id64);
    patch.originStationMarketId = state.docked && state.station_market_id ? String(state.station_market_id) : "";
    patch.originLocationLabel = state.docked && state.station_name
      ? `${state.station_name}, ${state.system_name ?? "Unknown system"}`
      : state.system_name ?? `System ID ${state.system_id64}`;
  }
  if (state.cargo_capacity !== null && state.cargo_capacity > 0) patch.cargoCapacity = state.cargo_capacity;
  if (state.max_jump_range !== null && state.max_jump_range > 0) patch.ladenJumpRange = state.max_jump_range;
  if (state.credits !== null) patch.credits = state.credits;
  if (state.rebuy !== null) patch.rebuyReserve = state.rebuy;

  if (transit) {
    const routeDestination = state.nav_route.at(-1);
    const destinationId = state.target_system_id64 ?? routeDestination?.system_id64;
    const destinationName = state.target_system_name ?? routeDestination?.system_name;
    if (destinationId) {
      patch.destinationSystemId64 = String(destinationId);
      patch.destinationStationMarketId = "";
      patch.destinationLocationLabel = state.target_station_name && destinationName
        ? `${state.target_station_name}, ${destinationName}`
        : destinationName ?? `System ID ${destinationId}`;
    }
  }
  return patch;
}

function NumberField({
  label,
  suffix,
  value,
  onChange,
  step = 1,
}: {
  label: string;
  suffix: string;
  value: number;
  onChange: (value: number) => void;
  step?: number;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      <div className="number-input">
        <input type="number" min="0" step={step} value={value} onChange={(e) => onChange(Number(e.target.value))} />
        <small>{suffix}</small>
      </div>
    </label>
  );
}

function Toggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (value: boolean) => void }) {
  return (
    <label className="toggle">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span className="switch"><Check size={12} /></span>
      {label}
    </label>
  );
}

export function EmptyState({
  title,
  body,
  icon: Icon = Database,
}: {
  title: string;
  body: string;
  icon?: typeof Database;
}) {
  return (
    <div className="empty-state">
      <div className="empty-icon"><Icon size={24} /></div>
      <h3>{title}</h3>
      <p>{body}</p>
    </div>
  );
}

export function TransitCard({ option, featured = false, onOpen }: { option: TransitSummary; featured?: boolean; onOpen?: (option: TransitSummary) => void }) {
  return (
    <article className={`transit-card ${featured ? "featured" : ""}`}>
      <div className="transit-heading">
        <div>
          <span className="eyebrow">{option.profile} route</span>
          <h3>{option.expected_profit ? `+${formatCredits(option.expected_profit)}` : "Direct travel"}</h3>
        </div>
        {featured && <span className="recommended"><Sparkles size={13} /> Recommended</span>}
      </div>
      <div className="transit-stats">
        <Metric icon={Clock3} label="Estimated" value={formatTime(option.estimated_seconds)} />
        <Metric icon={Route} label="Distance" value={`${option.total_distance_ly} ly`} />
        <Metric icon={Package} label="Trade stops" value={String(option.legs.length)} />
      </div>
      {option.profile !== "Direct" && (
        <div className="delta">
          <span>Costs {formatTime(option.extra_seconds_vs_direct)} extra</span>
          <ConfidenceBadge value={option.confidence} />
        </div>
      )}
      {option.positioning_station && (
        <div className="positioning-note">POSITION FIRST · {option.positioning_station}, {option.positioning_system}</div>
      )}
      <div className="transit-legs">
        {option.legs.map((leg, index) => (
          <div className="transit-leg" key={`${leg.destination_market_id}-${index}`}>
            <span>{index + 1}</span>
            <div>
              <strong>{leg.commodity} · {leg.quantity} t</strong>
              <small>{leg.source_station} → {leg.destination_station}</small>
            </div>
            <b>+{formatCredits(leg.trip_profit)}</b>
          </div>
        ))}
        {!option.legs.length && <p className="muted">No cargo stops. Plot the route in-game.</p>}
      </div>
      {onOpen && <button className="secondary board-button" onClick={() => onOpen(option)}>Open route console</button>}
    </article>
  );
}

export function FlightBoard({
  title,
  legs,
  summary,
  preflight,
  activatedAt: suppliedActivatedAt,
  initialManualStep = 0,
  allowPopout = true,
  onClose,
}: {
  title: string;
  legs: TradeLeg[];
  summary: { profit: number; seconds: number; distance?: number; jumps?: number };
  preflight?: string;
  activatedAt?: string;
  initialManualStep?: number;
  allowPopout?: boolean;
  onClose: () => void;
}) {
  const [activatedAt] = useState(suppliedActivatedAt ?? new Date().toISOString());
  const [manualStep, setManualStep] = useState(initialManualStep);
  const elite = useQuery({
    queryKey: ["elite-status"],
    queryFn: api.eliteStatus,
  });
  useEffect(() => {
    void api.setActiveOperation({
      operation_type: "cargo_manifest",
      schema_version: 1,
      title,
      route_payload: { title, legs, summary, preflight },
      activated_at: activatedAt,
      manual_progress: manualStep,
      status: "active",
    });
  }, [title, activatedAt, manualStep]);
  const live = Boolean(elite.data?.enabled && elite.data.state.game_running);
  const activeStep = live
    ? calculateLiveRouteStep(legs, elite.data!.state, activatedAt)
    : Math.min(manualStep, Math.max(0, legs.length * 2 - 1));
  return (
    <div className="flight-board-backdrop" role="dialog" aria-modal="true" aria-label={title}>
      <section className="flight-board">
        <header>
          <div><span className="eyebrow">Active cargo manifest</span><h2>{title}</h2></div>
          <button className="icon-button" aria-label="Close flight board" onClick={onClose}><X size={22} /></button>
        </header>
        <div className="board-summary">
          <Metric icon={Coins} label="Expected profit" value={`+${formatCredits(summary.profit)}`} />
          <Metric icon={Clock3} label="Flight time" value={formatTime(summary.seconds)} />
          {summary.distance !== undefined && <Metric icon={Route} label="Distance" value={`${summary.distance} ly`} />}
          {summary.jumps !== undefined && <Metric icon={Gauge} label="Estimated jumps" value={String(summary.jumps)} />}
        </div>
        {preflight && <div className="positioning-note">{preflight}</div>}
        <div className="flight-board-body">
          <RouteProgressRail
            title={title}
            legs={legs}
            activeStep={activeStep}
            live={live}
            state={elite.data?.state}
            onPrevious={() => setManualStep((value) => Math.max(0, value - 1))}
            onNext={() => setManualStep((value) => Math.min(Math.max(0, legs.length * 2 - 1), value + 1))}
          />
          <div className="manifest">
          {legs.map((leg, index) => {
            const legState = activeStep > index * 2 + 1 ? "complete" : activeStep >= index * 2 ? "active" : "pending";
            return (
            <article className={`manifest-leg ${legState}`} key={`${leg.source_market_id}-${leg.destination_market_id}-${leg.commodity_id}-${index}`}>
              <div className="manifest-index">{String(index + 1).padStart(2, "0")}</div>
              <div className="manifest-route">
                <span>LOAD AT</span>
                <h3>{leg.source_station}</h3>
                <p>{leg.source_system} · {leg.distance_to_route_ly ? `${leg.distance_to_route_ly} ly from current position` : "current route position"}</p>
              </div>
              <div className="manifest-cargo">
                <span>COMMODITY ORDER</span>
                <strong>{leg.quantity} t · {leg.commodity}</strong>
                <p>Buy {leg.buy_price.toLocaleString()} CR/t · Total {(leg.buy_price * leg.quantity).toLocaleString()} CR</p>
              </div>
              <div className="manifest-route">
                <span>DELIVER TO</span>
                <h3>{leg.destination_station}</h3>
                <p>{leg.destination_system} · {leg.jumps} jumps · {leg.system_distance_ly} ly</p>
              </div>
              <div className="manifest-profit">
                <span>SALE / PROFIT</span>
                <strong>{leg.sell_price.toLocaleString()} CR/t</strong>
                <b>+{formatCredits(leg.trip_profit)}</b>
              </div>
            </article>
          )})}
          {!legs.length && <EmptyState title="Direct flight" body="There are no cargo orders on this plan. Plot the destination in the in-game galaxy map." icon={Route} />}
          </div>
        </div>
        <footer>
          <span>COMMUNITY MARKET DATA · VERIFY PRICE BEFORE PURCHASE</span>
          <div className="board-actions">
            {allowPopout && <button className="secondary" onClick={() => {
              void api.setActiveOperation({
                operation_type: "cargo_manifest",
                schema_version: 1,
                title,
                route_payload: { title, legs, summary, preflight },
                activated_at: activatedAt,
                manual_progress: manualStep,
                status: "active",
              }).then(() => isDesktop()
                ? desktopCall("open_route_console")
                : window.open("/flight-board", "ion-route-console", "width=1500,height=900"));
            }}>Open on second screen</button>}
            <button className="primary" onClick={onClose}>{allowPopout ? "Return to planner" : "Close console"}</button>
          </div>
        </footer>
      </section>
    </div>
  );
}

function commodityMatches(left: string, right: string) {
  const normalize = (value: string) => value.toLocaleLowerCase().replace(/^\$/, "").replace(/_name;$/, "").replace(/[^a-z0-9]/g, "");
  return normalize(left) === normalize(right);
}

function calculateLiveRouteStep(
  legs: TradeLeg[],
  state: import("./types").EliteLiveState,
  activatedAt: string,
) {
  const started = Date.parse(activatedAt);
  let completed = 0;
  for (const leg of legs) {
    const sold = state.transactions.some((transaction) =>
      transaction.kind === "sell"
      && transaction.market_id === leg.destination_market_id
      && commodityMatches(transaction.commodity, leg.commodity)
      && (!transaction.timestamp || Date.parse(transaction.timestamp) >= started)
    );
    if (!sold) break;
    completed += 1;
  }
  if (completed >= legs.length) return legs.length * 2;
  const leg = legs[completed];
  const cargoLoaded = state.cargo.some((item) => commodityMatches(item.commodity, leg.commodity) && item.count > 0)
    || state.transactions.some((transaction) =>
      transaction.kind === "buy"
      && transaction.market_id === leg.source_market_id
      && commodityMatches(transaction.commodity, leg.commodity)
      && (!transaction.timestamp || Date.parse(transaction.timestamp) >= started)
    );
  const atDestination = state.station_market_id === leg.destination_market_id
    || (state.system_id64 === leg.destination_system_id64 && !state.docked);
  return completed * 2 + (cargoLoaded || atDestination ? 1 : 0);
}

function RouteProgressRail({
  title,
  legs,
  activeStep,
  live,
  state,
  onPrevious,
  onNext,
}: {
  title: string;
  legs: TradeLeg[];
  activeStep: number;
  live: boolean;
  state?: import("./types").EliteLiveState;
  onPrevious: () => void;
  onNext: () => void;
}) {
  return (
    <aside className="route-progress">
      <div className="progress-link-state">
        <span className={live ? "online" : ""} />
        <div><b>{live ? "LIVE ROUTE TRACKING" : "ROUTE GUIDE"}</b><small>{live ? state?.phase.replaceAll("_", " ") : "MANUAL PROGRESS"}</small></div>
      </div>
      <h3>{title}</h3>
      {state?.available && (
        <div className="live-position">
          <span>Current position</span>
          <strong>{state.station_name || state.system_name || "Unknown"}</strong>
          {state.station_name && <small>{state.system_name}</small>}
          {state.target_system_name && <p>Target: {state.target_system_name}</p>}
          {state.nav_route.length > 1 && <p>{state.nav_route.length - 1} plotted jumps remaining</p>}
        </div>
      )}
      <div className="progress-steps">
        {legs.flatMap((leg, legIndex) => [
          <div className={`progress-step ${activeStep === legIndex * 2 ? "current" : activeStep > legIndex * 2 ? "complete" : ""}`} key={`load-${legIndex}`}>
            <span>{activeStep > legIndex * 2 ? <Check size={12} /> : String(legIndex + 1).padStart(2, "0")}</span>
            <div><small>LOAD</small><strong>{leg.quantity} t {leg.commodity}</strong><p>{leg.source_station}<br />{leg.source_system}</p></div>
          </div>,
          <div className={`progress-step ${activeStep === legIndex * 2 + 1 ? "current" : activeStep > legIndex * 2 + 1 ? "complete" : ""}`} key={`deliver-${legIndex}`}>
            <span>{activeStep > legIndex * 2 + 1 ? <Check size={12} /> : "→"}</span>
            <div><small>DELIVER</small><strong>{leg.destination_station}</strong><p>{leg.destination_system} · {leg.jumps} jumps</p></div>
          </div>,
        ])}
        {!legs.length && <p className="muted">Direct navigation has no cargo milestones.</p>}
      </div>
      {!live && legs.length > 0 && (
        <div className="manual-progress-controls">
          <button className="secondary" onClick={onPrevious} disabled={activeStep === 0}>Previous</button>
          <button className="primary" onClick={onNext} disabled={activeStep >= legs.length * 2 - 1}>Advance</button>
        </div>
      )}
      {live && state?.landing_pad !== null && state?.landing_pad !== undefined && <div className="landing-pad">ASSIGNED PAD <strong>{state.landing_pad}</strong></div>}
    </aside>
  );
}

export function Notice({ children, tone = "info" }: { children: React.ReactNode; tone?: "info" | "warning" }) {
  return <div className={`notice ${tone}`}><AlertTriangle size={17} />{children}</div>;
}
