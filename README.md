# Elite Logistics

Elite Logistics is a Windows-friendly local companion for Elite Dangerous cargo operations. It includes one-way trades, round trips, immersion-oriented multi-stop Trade Routes, profitable transit, full-screen flight manifests, ship profiles, and ship optimization planning.

The interface follows an Elite-style service hierarchy: begin at the home console, enter Trade Operations, Navigation, Fleet Management, or the Data Network, then select the individual planning service. Ship optimization includes complete core, optional, utility, and hardpoint recommendations for Cargo, Range, Safety, and Balanced roles.

## Start

Run `start.ps1` in PowerShell. The launcher prepares the local environment, builds the interface when needed, starts the app at `http://127.0.0.1:8765`, and opens it in your browser.

The first online search uses Spansh to cache the selected system and nearby market candidates. The Data page offers compact live lookup, regional sector caches, or the much larger full-galaxy pack. Full-pack downloads show size, speed, progress, and ETA.

## Development

- Backend: Python 3.12+, FastAPI, SQLAlchemy, Alembic, SQLite
- Frontend: React, TypeScript, Vite, TanStack Query
- `dev.ps1`: local development servers
- `python -m pytest backend/tests`: backend test suite
- `npm --prefix frontend test`: frontend tests
- `npm --prefix frontend run build`: production interface

Market data is community-observed and can change before arrival. Every recommendation therefore includes freshness- and liquidity-based confidence.

See [ROADMAP.md](ROADMAP.md) for planned releases.

AI agents should begin with [ai_context/AI_README.md](ai_context/AI_README.md).
