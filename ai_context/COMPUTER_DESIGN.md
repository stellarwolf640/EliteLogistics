# ION Computer Design

## Status

ION Computer is a planned operational copilot. The current code provides only
its typed preferences, tool/control catalogues, permission policy, read-only
catalogue APIs, and authorization tests. It does **not** yet include a language
model, speech recognition, text-to-speech, wake word, raw input bridge, or tool
execution.

The backend source of truth is:

```text
backend/src/elite_logistics/computer.py
```

## Identity

The Computer is embedded throughout ION rather than presented as a separate
chatbot page. Its intended loop is:

> Observe commander state → understand a request or event → use an approved
> ION tool → present or perform a useful action.

Useful outcomes include opening an ION service, populating a planner, comparing
routes, activating an operation, reading the next instruction, displaying a
briefing, or executing one explicitly approved Elite binding.

The default personality is professional, calm, concise, and optionally
addresses the user as “Commander.” It should be terse while flying and may be
more conversational while docked.

## Intelligence modes

All modes use the same structured tools and permission system.

- **Off:** Computer disabled; normal ION remains fully functional.
- **Command:** deterministic phrases and templates; no generative model.
- **Lite:** small quantized local model with deterministic fallback.
- **Enhanced:** larger local model with better interpretation and explanation.
- **Automatic:** ION recommends a locally supported runtime.

Hardware changes interpretation quality, not access to more dangerous tools.

## Capability scope

The Computer is planned to support:

- Commander, ship, location, cargo, navigation, and operation briefings.
- Contextual system, station, service, commodity, and route questions.
- One-way, round-trip, Trade Route, and Profitable Transit planning.
- Cargo selling, commodity sourcing, reachability, and route comparison.
- Active-operation instructions, progress, pause/resume, and replanning.
- ION navigation, planner population, filter changes, and route-console control.
- Configurable operational and critical alerts.
- Visible, editable commander preferences.
- Explicit one-shot Elite bindings for HOTAS accessibility and immersion.

It is not an autopilot, trading bot, combat bot, mining bot, AFK system, or
general-purpose operating-system agent.

## Control classes

- **Class A:** reversible ION application controls.
- **Class B:** explicit, one-shot, allowlisted Elite Dangerous bindings.
- **Class C:** multi-step game-interface automation; excluded.
- **Class D:** autonomous gameplay; excluded.

Class B actions exist so a HOTAS commander can operate less-accessible controls
without reaching for the keyboard. They must not make gameplay decisions.

## Class B rules

The agent never receives arbitrary keyboard access. It receives semantic
actions such as:

```text
set_ship_system(landing_gear, deployed)
open_game_interface(galaxy_map)
set_power_distribution(engines)
```

Where telemetry exposes state, ION uses desired-state operations instead of
blind toggles. If landing gear is already down, no input is sent. Verified
state changes may be reported as completed; unverifiable inputs are reported
only as “Command sent.”

ION should inspect the active Elite binding file and use a commander-assigned
secondary keyboard binding. It should guide users through missing bindings
rather than silently rewriting binding files in the first release.

### Initial control candidates

- Landing gear
- Cargo scoop
- Hardpoints
- Ship lights
- Night vision
- Galaxy and System Maps
- Navigation, communications, role, and internal panels
- Bounded power-distribution inputs

### Later protected candidates

- Target selection
- FSD actions
- Throttle presets
- Fire-group cycling
- Chaff, heat sink, shield-cell bank, and ECM

### Excluded controls

- Weapon firing
- Boost
- Cargo jettison
- Self-destruct
- Automated menu procedures
- Automated steering or throttle
- Repeated or unattended gameplay

## Permission model

- **Read:** state, knowledge, explanations, and calculations.
- **ION:** reversible application navigation or display actions.
- **Game Green:** direct, enabled, one-shot game action.
- **Game Amber:** protected game action requiring confirmation by default.
- **Confirm:** persistent or operation-replacing action requiring approval.

The Computer and Class B controls are disabled by default. Every game action
requires individual opt-in. Proactive events cannot execute game controls.
Multi-action sequences may be proposed but require approval before execution.

Every future tool invocation must record:

- Tool and action identifiers
- Invocation source
- Permission decision
- Confirmation state
- Preconditions
- Start and completion time
- Verification result or timeout
- Failure reason

## Safety requirements

The future Input Bridge must enforce:

- Elite is running and foreground.
- Only allowlisted semantic actions are accepted.
- One bounded action sequence runs at a time.
- Timeouts and rate limits.
- Voice confidence threshold and ambiguity rejection.
- Emergency disable hotkey.
- Visible activity and permanent local audit log.
- Immediate stop when expected state is uncertain.
- Authenticated pairing for any future remote device.
- No public-internet input endpoint.
- No game-memory injection or client hooking.

## Foundation APIs

```text
GET /api/computer/status
GET /api/computer/tools
GET /api/computer/controls
```

These endpoints are deliberately read-only. The status endpoint reports that
execution is unavailable until explicit runtime and Input Bridge work is
implemented.

Preferences schema 3 includes a nested `computer` record with:

- Enabled state
- Mode
- Commander address preference
- Response verbosity
- Proactivity level
- Class B master switch
- Individually enabled game actions
- Confirmation policy

Schema-2 preferences migrate to schema 3 with the Computer disabled.

## Initial tool priorities

The first intended tool group includes:

1. Operational, ship, navigation, cargo, and control-capability state.
2. Current-system, station, service, and recommendation inspection.
3. Existing trade, round-trip, Trade Route, and Profitable Transit planners.
4. Cargo-sale and plan-comparison tools.
5. Active-operation state, next instruction, activation, and progress.
6. ION view and route-console controls.
7. Ship-system and power-distribution Class B contracts.

The full tool and control backlog is versioned in `computer.py`. Tool names
must remain stable once an execution adapter ships.

## Proactive behavior

Candidate alerts include:

- Fuel risk relative to the route
- Missing upcoming scoopable stars
- Dangerous hull or canopy condition
- Cargo/manifest mismatch
- Passed destination
- Arrival-adjusted stale market data
- Insufficient destination demand
- Changed laden range
- Unreachable active route
- Completed route step
- Disconnected game link
- Useful refuel or repair stop

Proactivity levels are Silent, Critical, Operational, and Conversational.
Safety alerts may interrupt; market suggestions should not.

## Policy boundary

Frontier's current EULA contains restrictions concerning automation and broadly
worded restrictions concerning use of the Game or Online Features in AI tools:

https://www.frontier.co.uk/legal/eula

Before public release of a generative Computer that consumes live Elite data,
ISL should seek written clarification from Frontier. Deterministic Command Mode
and the manual Class B control panel must remain technically separable from a
generative model.

This document records product design and is not legal advice.

## Next implementation steps

1. Binding-file discovery and normalized action mappings.
2. Read-only control-capability report using real/sanitized binding fixtures.
3. Deterministic Command Mode parser for a small phrase set.
4. ION-only tool executor and immutable confirmation records.
5. Local Input Bridge behind the existing authorization policy.
6. Safe test panel for initial Green controls.
7. State verification and command audit events.
8. Speech and local-model adapters only after deterministic controls are stable.
