# ION Project Contents

## Repository overview

```text
EliteLogistics/                    Repository name retained for compatibility
├── ai_context/                     AI-agent onboarding and history
│   └── COMPUTER_DESIGN.md          Computer capability and safety contract
│   └── COMPUTER_ROADMAP.md         Computer C0–C12 delivery roadmap
├── backend/                        FastAPI application and route engine
│   ├── migrations/                 Alembic migrations
│   ├── src/elite_logistics/        Backend package
│   └── tests/                      Deterministic backend tests and fixtures
├── frontend/                       React/TypeScript interface
│   ├── public/branding/ion-logo.png Approved ION brand lockup
│   ├── src/
│   └── package.json
├── data/                           Local runtime data; ignored by Git
├── referenceData/                  Private copied Elite files; ignored by Git
├── assets/                         ION emblem, ICO family, update public key
├── installer/ION.iss               Per-user Inno Setup definition
├── scripts/                        Version, icon, manifest, and key tooling
├── .github/workflows/windows.yml   Windows tests/build/release automation
├── build.ps1                       Executable and installer build
├── start.ps1                       Source checkout launcher
├── dev.ps1                         Development launcher
├── README.md                       User/developer introduction
├── ROADMAP.md                      Planned releases
└── elite_logistics_initial_design.md
```

## Backend

### `backend/src/elite_logistics/main.py`

- Creates the FastAPI application.
- Registers the API router.
- Initializes the database through the FastAPI lifespan.
- Starts/stops the background Elite monitor.
- Hosts `WS /api/events`, including replay and snapshot fallback.
- Serves `frontend/dist` in production-local mode.
- Falls back to `index.html` for frontend routes.
- Retains a browser-oriented Uvicorn entry point for development/legacy use.

### `backend/src/elite_logistics/desktop.py`

Native Windows host:

- Enforces a single running desktop instance.
- Starts FastAPI/Uvicorn in a background thread on `127.0.0.1:8766`.
- Waits for `/api/health` before opening the interface.
- Hosts the compiled React application in Edge WebView2 through pywebview.
- Exposes the trusted `DesktopBridge`.
- Owns custom-frame controls, folder selection, the second route window,
  window restoration, tray behavior, and update installation.
- Uses the source `data/` profile or installed Local AppData profile.
- Stops the local service and monitor on full exit.
- Provides service-only and native-window smoke-test modes.

### `backend/src/elite_logistics/api.py`

Public local API and orchestration layer.

Important endpoints:

```text
GET    /api/health
GET    /api/diagnostics
WS     /api/events
GET    /api/data/status
GET    /api/data/spansh-pack-info
GET    /api/locations/search
GET    /api/elite/status
PUT    /api/elite/settings
GET    /api/computer/status
GET    /api/computer/tools
GET    /api/computer/controls
PUT    /api/computer/settings
POST   /api/computer/settings/reset
POST   /api/computer/tools/invoke
GET    /api/computer/invocations
POST   /api/computer/invocations/{invocation_id}/cancel
POST   /api/computer/confirmations/{confirmation_id}
GET    /api/computer/bindings

GET    /api/ship-profiles
POST   /api/ship-profiles
PUT    /api/ship-profiles/{profile_id}
DELETE /api/ship-profiles/{profile_id}

GET    /api/preferences
PUT    /api/preferences
GET    /api/operations/active
PUT    /api/operations/active
DELETE /api/operations/active

GET    /api/updates/status
POST   /api/updates/check
POST   /api/updates/download

POST   /api/trades/search
POST   /api/round-trips/search
POST   /api/trade-routes/search
POST   /api/transit/plans

GET    /api/jobs/{job_id}
POST   /api/data/regions/cache
POST   /api/data/spansh-imports
DELETE /api/data/spansh-pack
```

This module also:

- Applies shared assumptions to responses.
- Refreshes Spansh market candidates when appropriate.
- Avoids live refresh writes while a full import is active.
- Rolls back failed SQLAlchemy transactions before using cached fallback data.

### `backend/src/elite_logistics/engine.py`

Core business logic.

Contains:

- Distance and conservative jump calculations.
- Supercruise and leg-duration estimates.
- Station-access filtering.
- Confidence scoring.
- Trade-leg construction.
- One-way trade ranking.
- Round-trip generation.
- Immersive Trade Route generation.
- Profitable Transit beam search.

Important concepts:

- `build_trade_leg` is the shared trade-validation and calculation function.
- `find_trades` treats the selected location as the center of a route-search radius.
- `find_round_trips` recalculates capital after the outbound sale.
- `find_immersive_trade_routes` prioritizes continuity and cargo variety.
- `plan_transit` compares Direct, Fast, Balanced, and Profit profiles.

### `backend/src/elite_logistics/providers.py`

Market-provider implementations and normalization.

- `MarketProvider` defines the current provider boundary.
- `SpanshRemoteProvider` handles location search, system dumps, and trade-candidate hydration.
- `SpanshDumpProvider` streams local JSON/gzip records into normalized tables.
- New provider work should normalize into the existing database models.

### `backend/src/elite_logistics/elite_data.py`

Optional local Elite adapter:

- Reconstructs current commander, location, ship, cargo, navigation, and flight
  state from the newest journal.
- Reads `Status.json`, `Cargo.json`, `Market.json`, and `NavRoute.json`.
- Captures recent buy/sell events for route-leg completion.
- Distinguishes live journal activity from historical copied reference data.
- Normalizes the current station's `Market.json` into the shared SQLite market
  tables using provider `EliteJournal`.

### `backend/src/elite_logistics/computer.py`

Provider-neutral ION Computer foundation:

- Versioned tool and Class B control catalogues.
- Read, ION, Game Green, Game Amber, and Confirm permissions.
- Explicit-user, confirmed-proposal, manual-control, and proactive sources.
- Default-deny authorization for Computer and game actions.
- Per-action opt-in and Amber confirmation requirements.
- Stable executable-tool allowlist for the C2 policy runtime.
- No model, speech, raw keyboard, or game-input adapter.

### Computer runtime and binding modules

- `computer_runtime.py`: the single policy-gated executor for Read and ION
  tools, immutable confirmation proposals, timeout/cancellation handling,
  structured results, WebSocket events, and the local invocation audit.
- `elite_bindings.py`: read-only active `.binds` discovery, XML parsing,
  primary/secondary binding normalization, device classification, conflict
  detection, capability reporting, and file-change monitoring.
- Neither module sends keyboard, mouse, HOTAS, or other game input.

### `backend/src/elite_logistics/database.py`

SQLAlchemy models and database configuration.

Current tables:

- `systems`
- `stations`
- `commodities`
- `market_observations`
- `ship_profiles`
- `preferences`
- `data_imports`
- `jobs`
- `active_operations`
- `computer_invocations`
- `computer_confirmations`

SQLite uses:

- WAL mode.
- A 60-second busy timeout.
- Normal synchronous mode.
- Thread-safe connections for local background jobs.

### `backend/src/elite_logistics/schemas.py`

Pydantic API contracts.

Key request/response types:

- `PlayerState`
- `ShipConstraints`
- `SearchFilters`
- `TradeSearchRequest`
- `TradeLeg`
- `RoundTrip`
- `TransitRequest`
- `TransitSummary`
- `ImmersiveTradeRoute`
- `ComputerPreferences`

Preferences schema 3 adds nested Computer settings. Schema-2 profiles migrate
with Computer and Class B controls disabled.

Keep scoring implementation details out of public contracts unless the UI needs them to explain a recommendation.

### `backend/src/elite_logistics/jobs.py`

Background work:

- Profitable Transit jobs.
- Full Spansh archive download/import.
- Job progress and failure recording.
- SQLite write retry behavior.
- Download speed, byte count, ETA, and phase metadata.
- Resumable `.part` downloads.
- Event publication for progress, completion, and failure.

### Desktop/event/update modules

- `events.py`: bounded sequence buffer and thread-safe subscribers.
- `elite_monitor.py`: background journal/file monitor and typed Elite events.
- `elite_bindings.py`: background read-only bindings monitor and capability
  change events.
- `updater.py`: stable-release discovery, Ed25519 manifest verification,
  streamed installer download, size/hash validation, and handoff to the shell.
- `version.py`: the canonical `0.2.3` application version.

### `backend/src/elite_logistics/config.py`

Environment and runtime paths.

Important variables:

```text
ELITE_LOGISTICS_DATA_DIR
ELITE_LOGISTICS_DATABASE_URL
SPANSH_BASE_URL
ELITE_LOGISTICS_OPEN_BROWSER
```

Installed runtime paths:

```text
%LOCALAPPDATA%\IntraStellar Logistics\ION\
├── ion.db
├── cache\
├── downloads\
├── logs\
├── updates\
└── webview\
```

### Backend tests

- `test_engine.py` covers trade math, reserves, confidence, round trips, immersive routes, and transit constraints.
- `test_provider.py` covers dump parsing and newest-observation precedence.
- `test_desktop.py` covers port selection, server URLs, and Windows single-instance behavior.
- `test_desktop_phases.py` covers typed preference recovery, active operations,
  event replay, window clamping, semantic versions, and Ed25519 verification.
- `test_computer.py` covers unique allowlisted contracts, default-deny
  behavior, explicit intent, per-action opt-in, and Amber confirmation.
- `fixtures/tiny_spansh.json` is the deterministic market fixture.

## Frontend

### `frontend/src/App.tsx`

Top-level application shell and pages.

Current route hierarchy:

```text
/                       Home console
/operations             Trade Operations submenu
/trade                  Best Trades
/round-trips            Round Trips
/trade-routes           Trade Routes
/navigation             Navigation submenu
/transit                Profitable Transit
/fleet                  Fleet Management submenu
/ships                  Ship Profiles
/ship-optimizations     Ship Optimizations
/data                   Data Network
/computer               Computer settings, safe tools, bindings, and audit
/settings               Desktop settings, updater, and diagnostics
/flight-board           Standalone second-screen manifest
```

The app uses a small History API router rather than React Router.

### `frontend/src/components.tsx`

Shared interface elements:

- Trade cards.
- Transit cards.
- Full-screen/second-screen flight board.
- Left-side live/manual route progress rail.
- Location autocomplete.
- Shared search fields.
- Confidence and metric components.
- Empty and warning states.

### `frontend/src/api.ts`

- Typed frontend API client.
- Converts `SearchDraft` into backend request contracts.
- Centralizes filters and state serialization.

### `frontend/src/types.ts`

Frontend representations of API responses and locally persisted planning state.

### `frontend/src/useSearchDraft.ts`

- Hydrates and debounces the typed backend preference record.
- Manual state remains canonical.

### `frontend/src/events.ts` and `desktopBridge.ts`

- One reconnecting WebSocket client per renderer.
- Cache invalidation from typed event envelopes.
- Feature components remain transport-neutral.
- Native calls are available only when pywebview injects its trusted bridge.

### `frontend/src/shipCatalog.ts`

- Freight-oriented ship catalogue.
- Core and optional slot metadata.
- Cargo, Range, Safety, and Balanced module recommendation generation.
- Planning estimates for cargo and laden range.

Do not present these recommendations as exact engineered builds until a full module-stat calculation engine exists.

### `frontend/src/styles.css`

Single global visual system:

- Elite-style hierarchical service console.
- Orange/amber focus color.
- Geometric panels and clipped corners.
- Nested service-menu tiles.
- Trade and transit displays.
- Module manifests.
- Responsive layouts.
- Full-screen flight board.
- ION masthead and compact persistent-navigation identity.

### Frontend tests

`components.test.tsx` currently covers:

- Cargo instruction visibility.
- Confidence presentation.
- Current-location/radius controls.
- Location clearing behavior.
- Distinct slot-by-slot ship optimization profiles.
- Computer safety messaging, binding capability display, and stable manual
  clearing of the bindings-directory field.

## Data flow

```text
Manual planning state ◄──── optional Elite game-file state
        │
        ▼
React search form
        │
        ▼
FastAPI endpoint
        │
        ├── Spansh refresh when needed
        │
        ▼
Normalized SQLite market state
        │
        ▼
Route engine
        │
        ▼
Explainable route response
        │
        ▼
Cards / flight board / second-screen console
```

## Runtime data

Source runtime directory:

```text
./data/
```

Expected files may include:

```text
ion.db
ion.db-wal
ion.db-shm
galaxy_stations.json.gz
galaxy_stations.json.gz.part
```

All runtime data is ignored by Git.

## Private game-file reference set

`/referenceData/` is a local-only copy of files produced by Elite Dangerous on
another computer. It currently provides real examples of:

```text
Journal.*.log
Status.json
Cargo.json
Market.json
NavRoute.json
Shipyard.json
Outfitting.json
Backpack.json
ShipLocker.json
```

Use this directory to understand real event and snapshot shapes while designing
the optional game-file adapter. Code and tests must continue working when it is
absent. Do not commit these files: journal and state records can contain
commander identity, location history, and other private gameplay data. Tests
should use narrowly scoped, sanitized fixtures derived from the relevant
structures instead.

## Validation

Expected checks before publishing:

```powershell
.\.venv\Scripts\python.exe -m pytest backend
npm --prefix frontend test -- --run
npm --prefix frontend run build
npm --prefix frontend run test:e2e
.\build.ps1
```

At the time this context was created:

- Backend: 42 tests passing.
- Frontend: 11 tests passing.
- End-to-end: 4 scenarios passing.
- Production frontend build passing.
- Source, frozen, native-window, installer, installed-app, and uninstall smoke tests passing.
