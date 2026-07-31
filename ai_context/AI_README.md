# AI Agent Onboarding

This folder is the fast-start context for AI agents working on ION — the
IntraStellar Operations Network. Read these files before changing code:

1. `AI_README.md` — product intent, architectural rules, and working practices.
2. `PROJECT_CONTENTS.md` — repository map, routes, APIs, data flow, and important files.
3. `CHANGELOG.md` — implemented changes and current release state.
4. `COMPUTER_DESIGN.md` — agreed Computer capabilities, controls, and safety boundaries.
5. `/ROADMAP.md` — planned release sequence.
6. `/elite_logistics_initial_design.md` — original detailed design and mathematical assumptions.

## Product

ION is a Windows-first operations companion for Elite Dangerous, offered and
produced by IntraStellar Logistics (ISL). It should feel like an in-universe
extension of the game rather than a generic trading website. The repository and
some internal package/storage identifiers retain the original `elite-logistics`
name for compatibility; user-facing identity is ION.

Its current capabilities are:

- One-way commodity trade discovery.
- Profitable round trips.
- Multi-stop, immersion-oriented Trade Routes.
- Profitable Transit between arbitrary destinations.
- Full-screen and second-screen cargo manifests.
- Manual commander, location, balance, reserve, and ship state.
- Ship profiles and role-specific module recommendations.
- Live Spansh lookup, regional caching, and an optional full-galaxy import.
- Optional Elite journal/game-file state, current-market synchronization, and
  live route progress.

## Product priorities

Use this priority order when requirements compete:

1. Give the commander a practical, understandable flight plan.
2. Protect rebuy and cash reserves.
3. Be honest about stale, incomplete, or community-observed market data.
4. Account for travel time and distance, not only nominal profit.
5. Preserve immersion and the Elite-style operational-console experience.
6. Keep manual state fully functional when Elite Dangerous is closed or absent.
7. Prefer explainable recommendations over opaque scoring.

Trade Routes are intended to become the flagship feature. Unlike Best Trades, they should emphasize continuous hauling, varied cargo, route identity, duration, and group play—not just maximum CR/hour.

## Non-negotiable architecture

- Manual player state is canonical.
- Game-file integration may populate the same editable state, but must never become required.
- Market-provider details stay behind provider-neutral boundaries.
- Every market observation retains its provider and observation timestamp.
- Missing or stale data must never be silently presented as current.
- SQLite is the local current-state store.
- Do not add cloud hosting, user accounts, or Docker as requirements for normal use.
- Production-local mode is a native pywebview/Edge WebView2 window with an
  in-process FastAPI service serving the compiled frontend and API.
- The native desktop service uses stable localhost port `8766` by default so
  the WebView profile retains the same origin between launches.
- Installed builds use `%LOCALAPPDATA%\IntraStellar Logistics\ION` and must
  never inspect or migrate repository data/browser state.
- `start.ps1` is source/development convenience. Normal users install and run
  `ION.exe` without Python, Node, or PowerShell.
- REST owns commands/snapshots. `WS /api/events` owns change notification and
  progress. Do not reintroduce frontend polling for Elite or jobs.
- Persist route-like work through the generic `active_operations` record, not
  browser storage or a trade-specific singleton.

## Current interface hierarchy

The application deliberately uses nested service menus:

```text
Home
├── Trade Operations
│   ├── Best Trades
│   ├── Round Trips
│   └── Trade Routes
├── Navigation
│   └── Profitable Transit
├── Fleet Management
│   ├── Ship Profiles
│   └── Ship Optimizations
├── Data Network
└── ION Settings
```

Do not reintroduce a generic permanent website sidebar without an explicit product decision. New major capabilities should normally be placed inside the appropriate service submenu.

## Visual direction

- Dark near-black background.
- Elite-style orange/amber focus color.
- Geometric panels, clipped corners, scan-line texture, compact uppercase labels.
- Strong keyboard/focus states.
- Information should resemble station services or an operations terminal.
- Avoid decorative cockpit clutter that makes planning information harder to read.
- Flight boards must remain suitable for a dedicated second screen.

## Routing and recommendation rules

- Preserve rebuy and extra cash reserves.
- Use laden jump range.
- Treat travel time as an estimate.
- Include station arrival distance and planetary approach costs.
- Apply supply, demand, access, pad, market-age, and confidence checks independently.
- Trade search is centered on where the commander is and may find route starts inside the selected radius.
- Profitable Transit always includes a direct baseline.
- Direct travel remains valid when no trustworthy cargo corridor can be formed.
- The in-game Galaxy Map handles the exact star-by-star hyperspace path.

The versioned formulas and defaults live in the backend schemas and route engine. Do not duplicate business logic in React.

## Data behavior

- Spansh is the current remote/bootstrap provider.
- Searches normalize and cache useful system, station, commodity, and market records.
- Regional caches are radius-based working datasets.
- The full `galaxy_stations.json.gz` archive is optional and may be very large.
- Interrupted full downloads use a `.part` file and resume with HTTP range requests.
- EDDN ingestion is planned but not yet implemented.
- Local game journal integration is implemented through
  `backend/src/elite_logistics/elite_data.py`.

### Local Elite reference data

The workspace may contain a private, ignored `/referenceData/` directory copied
from a computer with Elite Dangerous installed. It is the preferred real-world
reference for future journal/game-file adapter work when this development
computer does not have the game installed.

The current reference set includes journal logs plus `Status.json`,
`Cargo.json`, `Market.json`, `NavRoute.json`, `Shipyard.json`,
`Outfitting.json`, `Backpack.json`, and `ShipLocker.json`.

Rules for using it:

- Treat the files as read-only source examples.
- Never assume the folder exists in production, tests, or another checkout.
- Never make application startup or manual planning depend on it.
- Do not commit the directory or quote commander-private values in logs,
  documentation, fixtures, screenshots, or test output.
- Derive small sanitized deterministic fixtures when automated tests need
  representative events.
- The game-file adapter accepts an explicit directory path so it can point
  either to the real Saved Games directory or this reference copy.

Never commit:

- `data/`
- `referenceData/`
- SQLite databases
- `.part` archives
- `.venv/`
- `frontend/node_modules/`
- `frontend/dist/`
- credentials, tokens, or commander-private data

## Ship optimization behavior

The current ship catalogue and loadout recommendations are planning aids. Each profile produces:

- Core internal choices.
- Optional internal choices.
- Utility choices.
- Hardpoint guidance.
- Estimated cargo and laden range.

Cargo, Range, Safety, and Balanced profiles must produce meaningfully different module combinations. Exact module compatibility, engineering, power, heat, and final jump calculations are future work; the UI should continue telling users to verify the final build in-game.

## Development workflow

Backend:

```powershell
$env:ELITE_LOGISTICS_DATA_DIR="C:\VSCodeStuff\TDE\data"
.\.venv\Scripts\python.exe -m pytest backend
```

Frontend:

```powershell
npm --prefix frontend test -- --run
npm --prefix frontend run build
npm --prefix frontend run test:e2e
```

Source launch:

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

Native-window smoke test:

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1 -SmokeTest
```

Development launch:

```powershell
.\dev.ps1
```

## Change discipline

- Preserve user data and unrelated working-tree changes.
- Use Alembic for persistent database schema changes.
- Add deterministic tests for route-engine behavior.
- Provider tests must use sanitized fixtures and must not require live Spansh.
- Add or update interface tests for important user-visible behavior.
- Rebuild the production frontend after interface changes.
- Keep `/README.md`, `/ROADMAP.md`, and this folder current when architecture or release scope changes.
- The GitHub repository is `stellarwolf640/EliteLogistics`.
- Publish completed work through a feature branch and pull request when a normal base branch exists.

## Known limitations

- Profitable Transit quality depends on corridor market coverage.
- Regional caching is not an official pre-split Spansh sector archive.
- Live mode is currently on-demand lookup, not continuous EDDN streaming.
- Ship module recommendations are not a full Coriolis/EDSY-grade outfitting simulator.
- Trade Routes do not yet persist campaigns or synchronize group progress.
- Price history is not retained in v1.
- The application binary is not Authenticode signed for the friends release,
  so Windows may show an unknown-publisher warning.
- The release signing private key is local/secret material and must exist as
  GitHub Actions secret `ION_UPDATE_SIGNING_KEY`; only its public key is committed.
- Windows Snap Layout integration is deferred; normal native edge resizing works.
- The future Linux service, accounts/company administration, and other
  professions remain unimplemented.
- Computer tool/control contracts and preferences exist, but model, voice,
  wake-word, binding discovery, and game-input execution do not.
