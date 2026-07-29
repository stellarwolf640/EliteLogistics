# Project Contents

## Repository overview

```text
EliteLogistics/
├── ai_context/                     AI-agent onboarding and history
├── backend/                        FastAPI application and route engine
│   ├── migrations/                 Alembic migrations
│   ├── src/elite_logistics/        Backend package
│   └── tests/                      Deterministic backend tests and fixtures
├── frontend/                       React/TypeScript interface
│   ├── src/
│   └── package.json
├── data/                           Local runtime data; ignored by Git
├── referenceData/                  Private copied Elite files; ignored by Git
├── start.ps1                       Production-local launcher
├── dev.ps1                         Development launcher
├── README.md                       User/developer introduction
├── ROADMAP.md                      Planned releases
└── elite_logistics_initial_design.md
```

## Backend

### `backend/src/elite_logistics/main.py`

- Creates the FastAPI application.
- Registers the API router.
- Initializes the database.
- Serves `frontend/dist` in production-local mode.
- Falls back to `index.html` for frontend routes.
- Starts Uvicorn on `127.0.0.1:8765`.

### `backend/src/elite_logistics/api.py`

Public local API and orchestration layer.

Important endpoints:

```text
GET    /api/health
GET    /api/data/status
GET    /api/data/spansh-pack-info
GET    /api/locations/search
GET    /api/elite/status
PUT    /api/elite/settings

GET    /api/ship-profiles
POST   /api/ship-profiles
PUT    /api/ship-profiles/{profile_id}
DELETE /api/ship-profiles/{profile_id}

GET    /api/preferences
PUT    /api/preferences

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

Keep scoring implementation details out of public contracts unless the UI needs them to explain a recommendation.

### `backend/src/elite_logistics/jobs.py`

Background work:

- Profitable Transit jobs.
- Full Spansh archive download/import.
- Job progress and failure recording.
- SQLite write retry behavior.
- Download speed, byte count, ETA, and phase metadata.
- Resumable `.part` downloads.

### `backend/src/elite_logistics/config.py`

Environment and runtime paths.

Important variables:

```text
ELITE_LOGISTICS_DATA_DIR
ELITE_LOGISTICS_DATABASE_URL
SPANSH_BASE_URL
ELITE_LOGISTICS_OPEN_BROWSER
```

### Backend tests

- `test_engine.py` covers trade math, reserves, confidence, round trips, immersive routes, and transit constraints.
- `test_provider.py` covers dump parsing and newest-observation precedence.
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

- Stores the last valid manual planning state in browser local storage.
- Manual state remains canonical.

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

### Frontend tests

`components.test.tsx` currently covers:

- Cargo instruction visibility.
- Confidence presentation.
- Current-location/radius controls.
- Location clearing behavior.
- Distinct slot-by-slot ship optimization profiles.

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

Default runtime directory:

```text
./data/
```

Expected files may include:

```text
elite-logistics.db
elite-logistics.db-wal
elite-logistics.db-shm
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
```

At the time this context was created:

- Backend: 11 tests passing.
- Frontend: 8 tests passing.
- Production frontend build passing.
