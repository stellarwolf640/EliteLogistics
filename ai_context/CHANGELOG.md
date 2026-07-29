# AI-Facing Changelog

This changelog records product and architectural changes that future agents need to understand. It is not limited to public release notes.

## 0.2.0 — 2026-07-29

### CI correction

- The first post-implementation GitHub Actions run (`30485946586`) passed
  backend tests, frontend tests, and the production frontend build, then failed
  while starting the Playwright acceptance-test server.
- Cause: `frontend/playwright.config.ts` assumed the repository-local Windows
  virtual environment existed. GitHub's clean runner installs Python globally
  for the job and does not create `.venv`.
- Playwright now accepts `ION_PYTHON_EXECUTABLE`, otherwise uses the local
  `.venv` interpreter when present and falls back to `python` from `PATH`.
- The Windows workflow explicitly passes the absolute GitHub-provided Python
  interpreter path to the acceptance tests.
- Updated the official GitHub setup actions to their Node 24-based v7 releases,
  removing the unrelated Node 20 retirement warnings from the failed run.
- This was a build-automation portability defect, not an ION application or
  installer runtime failure.

### Desktop-owned state

- Moved search drafts and data mode from browser local storage into schema-v2
  backend preferences.
- Added close behavior, main/route window geometry, route fullscreen/topmost,
  and update-check preferences.
- Added the generic singleton `active_operations` record and active-operation API.
- Active cargo manifests now persist before display and restore after restart.
- Installed builds use a clean `%LOCALAPPDATA%\IntraStellar Logistics\ION`
  profile with `ion.db`, cache, downloads, logs, updates, and webview folders.

### Native workflows

- Replaced the standard title bar with the custom ION frame.
- Added native minimize, maximize/restore, close, folder selection, route
  console, fullscreen, always-on-top, tray, and updater bridge actions.
- Replaced the browser pop-out with one true secondary pywebview route window.
- Added monitor-aware window-bound restoration and clamping.
- Added complete-exit and minimize-to-tray behavior.
- Added diagnostics for version, paths, SQLite, WebView2, game link, and errors.

### Event transport

- Added ordered `WS /api/events` envelopes, a bounded replay buffer, and snapshot fallback.
- Added the background Elite-file monitor and typed location, cargo,
  navigation, market, operation, job, and update events.
- Removed repeated Elite and job polling from React.
- Added one reconnecting frontend event client and authoritative REST snapshots.

### Packaging and updates

- Centralized version `0.2.0`.
- Added Python 3.14/PyInstaller 6.21 one-folder packaging.
- Added ION executable/tray/installer icon resources.
- Added a current-user x64 Inno Setup installer, shortcuts, Add/Remove Programs
  entry, profile preservation, and conditional WebView2 Evergreen installation.
- Added signed stable GitHub Release update checks, release-note approval,
  download progress, Ed25519 manifest verification, size/SHA-256 validation,
  and silent upgrade handoff.
- Added stable-tag-only GitHub Actions publishing and installed-application smoke tests.
- Added 22 backend tests, 8 component tests, and 4 Playwright acceptance scenarios.
- Locally validated source, frozen, native-window, install, installed-run,
  uninstall, profile-preservation, and signed-manifest workflows.

## Earlier unreleased work

- Rebranded the user-facing application as **ION — IntraStellar Operations
  Network**, offered and produced by **IntraStellar Logistics (ISL)**.
- Added the approved ION orbital-network logo to the home operations console
  and introduced a compact ION identity in persistent navigation.
- Updated the native window, startup errors, document metadata, and project
  documentation while retaining internal storage/package identifiers for
  compatibility.
- Made route-engine test observations relative to the test run so deterministic
  fixtures do not expire as their original capture date ages.
- Added desktop-transition Phase 1: a native pywebview/Edge WebView2 application
  shell around the existing React and FastAPI application.
- Added a hidden in-process local service, stable desktop origin, persistent
  WebView profile, single-instance focusing, health-checked startup, and clean
  service shutdown.
- Changed normal `start.ps1` launches to open the native application with no
  browser or visible console.
- Added native startup-error handling, dependency/build freshness checks, and a
  full native-window launcher smoke test.
- Replaced deprecated FastAPI startup hooks with an application lifespan.
- Added `ai_context/` onboarding documentation.
- Documented the local-only `referenceData/` Elite journal and snapshot set.
- Ignored `referenceData/` so private commander and location data cannot be
  committed accidentally.
- Added the optional Elite game-file adapter for journal, status, cargo, market,
  navigation route, ship, commander, and transaction state.
- Added game-link configuration and optional automatic planning-state updates.
- Added current in-game station market synchronization using the
  `EliteJournal` provider label.
- Added a left route-progress rail to the full flight console.
- Added live event-driven route positioning, cargo load/sale completion,
  navigation targets, remaining plotted jumps, and assigned landing pads.
- Added manual Previous/Advance route-guide controls when live data is absent.
- Added sanitized Elite file fixtures and raised the validation baseline to 10
  backend and 7 frontend tests.
- Updated `start.ps1` to rebuild the interface when pulled source files are
  newer than the existing compiled frontend.
- Fixed interrupted import jobs remaining marked as active after an application
  restart and blocking later Spansh hydration.
- Added visible online-refresh/cache-fallback notices to trade searches.
- Made non-current breadcrumb hierarchy segments clickable.

## v1.1 — 2026-07-28

### Interface

- Replaced the flat website-style dashboard/sidebar with an Elite-inspired hierarchical service console.
- Added nested Home, Trade Operations, Navigation, Fleet Management, and Data Network menus.
- Rebuilt the visual system with orange/amber focus states, geometric panels, clipped corners, compact labels, and terminal-style information hierarchy.
- Preserved full-screen route manifests and second-screen pop-out mode.

### Ship planning

- Changed ship selection to a catalogue-backed dropdown.
- Expanded optimization from headline cargo/range estimates into slot-by-slot loadouts.
- Added different Core, Optional, Utility, and Hardpoint combinations for:
  - Cargo first
  - Range first
  - Safety first
  - Balanced
- Added explicit warnings that loadouts are planning recommendations rather than exact engineered builds.

### Routing and trade presentation

- Added explicit commodity names to purchase and sale instructions.
- Added expandable route dashboards with complete cargo manifests.
- Fixed location inputs so manually clearing a field keeps it empty and clears the underlying selected ID.
- Added distance-to-route and first-trip rate handling.
- Added the first immersion-oriented Trade Routes generator.
- Kept Direct, Fast, Balanced, and Profit transit profiles distinct even when their paths match.
- Allowed Profitable Transit to position empty to a nearby viable loading station.
- Added forced first-corridor market refresh and clearer direct-only guidance.

### Data

- Enabled SQLite WAL mode, longer busy waits, safe rollback, and job-write retries.
- Prevented live refresh work from conflicting with active full imports.
- Added live, regional, and full-galaxy data modes.
- Added regional radius caching.
- Added full-pack size, progress, speed, phase, and ETA information.
- Added resumable `.part` downloads using HTTP range requests.

### Project

- Initialized and published `stellarwolf640/EliteLogistics`.
- Added the persistent project roadmap.
- Validation baseline: 8 backend tests, 5 frontend tests, and a successful production build.

## v1.0 — 2026-07-28

### Foundation

- Created the Windows-first local React/FastAPI application.
- Added a single PowerShell production launcher and a development launcher.
- Added SQLite models and Alembic migration support.
- Added Spansh remote lookup and streaming full-pack import.
- Added provider-neutral market concepts.

### Trading

- Added one-way trade search.
- Added reserve-protected affordability calculations.
- Added supply, demand, pad, access, station-distance, and market-age filters.
- Added deterministic travel-time estimates.
- Added confidence scoring and explainable warnings.
- Added profitable round trips with post-sale balance recalculation.

### Travel

- Added Profitable Transit with a direct baseline.
- Added ellipsoidal corridor filtering and beam search.
- Added Fast, Balanced, and Profit scoring profiles.
- Added detour, stop-count, and trade-leg limits.

### Fleet and data

- Added editable ship profiles.
- Added manual state persistence.
- Added asynchronous jobs for transit and data imports.
- Added local-cache fallback when Spansh is unavailable.

## Original design baseline

Before implementation, the project established these principles:

- Manual state is canonical.
- Elite game integration is optional.
- Spansh provides bootstrap/current-state data.
- EDDN is a later live-update source.
- Trade recommendations must account for travel cost and confidence.
- Profitable Transit is a first-class feature.
- Colonization, passengers, and exploration are later shared-engine modes.

The full original design remains in `/elite_logistics_initial_design.md`.
