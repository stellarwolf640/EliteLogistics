# ION — IntraStellar Operations Network

ION is a Windows-first operations companion for Elite Dangerous, offered and
produced by **IntraStellar Logistics (ISL)**. It turns commander state, market
intelligence, navigation data, and future organizational objectives into
practical routes, alerts, assignments, and operational guidance.

ION 0.2.0 includes one-way trades, round trips, immersion-oriented
multi-stop Trade Routes, profitable transit, full-screen flight manifests,
ship profiles, and ship optimization planning.

The interface follows an Elite-style service hierarchy: begin at the home console, enter Trade Operations, Navigation, Fleet Management, or the Data Network, then select the individual planning service. Ship optimization includes complete core, optional, utility, and hardpoint recommendations for Cargo, Range, Safety, and Balanced roles.

The optional Elite game link reads the local journal, status, cargo, market, and
navigation files. It can populate planning state, import the market currently
visited in-game, and track an accepted route on the flight console. When the
game link is unavailable, the same left-side route rail remains usable as a
manual step-by-step guide.

## Install and start

Download `ION-Setup-x64-0.2.0.exe`, install it for your Windows account, and
launch **ION** from the Start Menu. The installed application includes Python,
the backend, the interface, and all normal dependencies. Python, Node.js,
PowerShell, and a source checkout are not required.

Source checkouts retain `start.ps1` for development convenience.

The installer checks for Microsoft Edge WebView2 and installs the Evergreen
runtime when it is missing. A second launch focuses the existing ION window.
Application state lives under
`%LOCALAPPDATA%\IntraStellar Logistics\ION`; uninstalling ION preserves that
profile.

The custom ION window includes a native second-screen route console, monitor
position restoration, folder selection, and optional system-tray behavior.
Search drafts and the active operation survive restarts. The interface receives
game, operation, job, market, and update changes over a local event stream
instead of repeatedly polling the backend.

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

- Backend: Python 3.14 x64, FastAPI, SQLAlchemy, Alembic, SQLite
- Frontend: React, TypeScript, Vite, TanStack Query
- `dev.ps1`: local development servers
- `start.ps1 -SmokeTest`: short native-window launcher check
- `python -m pytest backend/tests`: backend test suite
- `npm --prefix frontend test`: frontend tests
- `npm --prefix frontend run build`: production interface
- `npm --prefix frontend run test:e2e`: browser acceptance suite
- `build.ps1`: PyInstaller one-folder application and Inno Setup installer

Stable update checks use signed manifests from GitHub Releases. Release
maintainers must configure the `ION_UPDATE_SIGNING_KEY` repository secret; see
`scripts/configure_release_key.py`.

Market data is community-observed and can change before arrival. Every recommendation therefore includes freshness- and liquidity-based confidence.

See [ROADMAP.md](ROADMAP.md) for planned releases.

AI agents should begin with [ai_context/AI_README.md](ai_context/AI_README.md).
