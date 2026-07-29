# Elite Logistics Roadmap

## Desktop application transition

### Phase 1 — Native Windows shell (complete)

- Native Edge WebView2 application window
- Hidden in-process FastAPI service on localhost
- Existing React interface reused without a rewrite
- Single-instance behavior that focuses the open window
- Persistent desktop browser profile
- Clean service shutdown when the window closes
- Console-free project launcher with native startup errors

### Phase 2 — Desktop-owned state

- Move essential draft and active-route persistence from browser local storage
  into the local API/SQLite store
- Add native window geometry and display preferences
- Add application icon, executable metadata, and installer-ready assets

### Phase 3 — Native window workflows

- Dedicated second-screen flight-console window controlled by the desktop shell
- Native file/folder pickers for imports and Elite journal selection
- Native update and diagnostic surfaces
- Packaged Windows executable and installer

## v1.0 — Local logistics foundation

- One-way trades and round trips
- Profitable Transit
- Immersive multi-stop Trade Routes
- Full-screen and second-screen cargo manifests
- Manual commander and ship state
- Spansh-backed live, regional, and full-galaxy data modes
- Ship profiles and role-based module loadouts
- Elite-style hierarchical service console

## v1.1 — Game link and active route console

- Elite journal, Status, Cargo, Market, and NavRoute adapters
- Optional automatic location, balance, vessel, cargo, range, and rebuy state
- Current station market import into the normalized local cache
- Live system, station, flight-phase, navigation-target, cargo, and market-event tracking
- Left-side route progress rail with live and manual guide modes
- Assigned landing-pad and remaining plotted-jump readouts

## v1.2 — Stabilization and route reliability

- Progressive long-distance corridor discovery
- Persisted and resumable active routes across application restarts
- Better sorting, filtering, and no-route explanations
- Data download pause, cancellation, cleanup, and coverage reporting
- Performance improvements for large local datasets

## v1.3 — Relocation intelligence

- Current-route versus target-route comparison
- Opportunity cost and break-even calculations
- Planned session duration
- Expected session earnings
- Arrival-adjusted market risk

## v1.4 — Trade Routes

- Local circuits, long-haul corridors, expeditions, and open-ended trucking
- Desired duration, distance, stop count, and cargo variety
- Saved route campaigns and operation manifests
- Shareable route files or codes
- Wing cargo allocation and combined group progress

## v1.5 — Data platform and EDDN

- Continuous EDDN ingestion
- Source reconciliation and freshness tracking
- Incremental regional datasets
- Storage budgets and retention controls
- Coverage visualization and limited price history

## v1.6 — Exact outfitting and deeper game integration

- ModulesInfo and engineering adapters
- Exact module statistics and engineering effects
- Exportable outfitting plans

## v2.0 — Colonization logistics

- Material requirements and delivery progress
- Multi-run sourcing and mixed loads
- Cost, time, and completion estimates
- Fleet and wing workload division

## Later career modes

- Passenger operations
- Exploration and exobiology support
- Fleet-carrier and Community Goal logistics
- Mining sale assistance
