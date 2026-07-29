# AI-Facing Changelog

This changelog records product and architectural changes that future agents need to understand. It is not limited to public release notes.

## Unreleased

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
