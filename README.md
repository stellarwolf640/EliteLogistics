# Elite Logistics

Elite Logistics is a Windows-friendly local companion for Elite Dangerous cargo operations. It includes one-way trades, round trips, immersion-oriented multi-stop Trade Routes, profitable transit, full-screen flight manifests, ship profiles, and ship optimization planning.

The interface follows an Elite-style service hierarchy: begin at the home console, enter Trade Operations, Navigation, Fleet Management, or the Data Network, then select the individual planning service. Ship optimization includes complete core, optional, utility, and hardpoint recommendations for Cargo, Range, Safety, and Balanced roles.

The optional Elite game link reads the local journal, status, cargo, market, and
navigation files. It can populate planning state, import the market currently
visited in-game, and track an accepted route on the flight console. When the
game link is unavailable, the same left-side route rail remains usable as a
manual step-by-step guide.

## Start

Double-click **Elite Logistics** in the project folder, or run `start.ps1` in
PowerShell. The launcher prepares the local environment when needed and opens
Elite Logistics as a native Windows window. The local FastAPI service and
web-based renderer remain internal implementation details; no browser or
visible PowerShell window is required during normal use.

The desktop shell uses the installed Microsoft Edge WebView2 runtime. Windows
10 and 11 normally include it. A second launch focuses the existing Elite
Logistics window instead of starting another local service.

The first online search uses Spansh to cache the selected system and nearby market candidates. The Data page offers compact live lookup, regional sector caches, or the much larger full-galaxy pack. Full-pack downloads show size, speed, progress, and ETA.

To connect Elite, open **Data Network → Elite Dangerous game link**, select the
game's journal directory, enable the link, and save. The normal Windows
directory is:

```text
C:\Users\<you>\Saved Games\Frontier Developments\Elite Dangerous
```

Automatic form updates are a separate option. Leaving that option off preserves
fully manual planning while still allowing the route console to display live
positioning.

## Development

- Backend: Python 3.12+, FastAPI, SQLAlchemy, Alembic, SQLite
- Frontend: React, TypeScript, Vite, TanStack Query
- `dev.ps1`: local development servers
- `start.ps1 -SmokeTest`: short native-window launcher check
- `python -m pytest backend/tests`: backend test suite
- `npm --prefix frontend test`: frontend tests
- `npm --prefix frontend run build`: production interface

Market data is community-observed and can change before arrival. Every recommendation therefore includes freshness- and liquidity-based confidence.

See [ROADMAP.md](ROADMAP.md) for planned releases.

AI agents should begin with [ai_context/AI_README.md](ai_context/AI_README.md).
