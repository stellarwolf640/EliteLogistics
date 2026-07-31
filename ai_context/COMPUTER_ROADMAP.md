# ION Computer Integration Roadmap

## Purpose

This roadmap defines the remaining work required to complete ION Computer.
Computer milestones use `C0`, `C1`, and so forth independently of ION
application versions. This avoids conflicts with the existing application
roadmap for relocation intelligence, Trade Routes, and the data platform.

The development order is:

```text
Foundation
    ↓
Safe ION tools
    ↓
Binding discovery
    ↓
Manual game-control bridge
    ↓
Deterministic Computer
    ↓
Voice
    ↓
Proactive assistance
    ↓
Lite and Enhanced AI
    ↓
Public-release hardening
```

## C0 — Contracts and safety foundation

**Status: implemented in draft PR #3**

Completed:

- Tool and Class B control catalogues.
- Permission classes.
- Invocation-source tracking.
- Explicit-intent requirements.
- Per-action opt-in.
- Confirmation policies.
- Computer preference schema.
- Default-disabled controls.
- Read-only status/catalogue APIs.
- Canonical design documentation.
- Authorization tests.

Remaining before completion:

- GitHub checks pass.
- Review and merge PR #3.
- Decide whether the application version remains 0.2.3 or increments.

## C1 — Computer settings and policy interface

**Status: implemented**

Build user-facing configuration without executing tools.

### Features

- Computer settings service inside ION.
- Mode selection:
  - Off
  - Command
  - Lite
  - Enhanced
  - Automatic
- Response verbosity.
- “Address me as Commander.”
- Proactivity setting.
- Confirmation policy.
- Class B master switch.
- Individual control permissions.
- Tool catalogue viewer.
- Clear unavailable-runtime explanations.
- Reset-to-safe-defaults action.

### Safety

- Enabling Computer does not enable Class B controls.
- Enabling Class B does not enable individual actions.
- Amber actions are clearly identified.
- Excluded Class C/D actions never appear as enableable controls.

### Acceptance criteria

- Settings survive restart.
- Schema migration preserves existing ION settings.
- Every game action starts disabled.
- Unknown action IDs are discarded.
- Settings work without Elite installed.
- The UI clearly says execution is not installed.

## C2 — Safe tool-execution runtime

**Status: implemented**

Implement orchestration using only Read and ION tools.

### Components

- `ComputerOrchestrator`.
- Tool-executor interface.
- Policy evaluation.
- Invocation records.
- Immutable confirmation requests.
- Cancellation and timeout handling.
- Structured tool results.
- Computer events over the existing WebSocket.
- Local audit log.

### Initial executable tools

- Operational snapshot.
- Ship state.
- Navigation state.
- Cargo manifest.
- Current system.
- Active operation.
- Next instruction.
- Open ION view.
- Open route console.
- Populate planner.
- Change filters.
- Show information card.
- Diagnostics.

### Required execution path

```text
User request
    ↓
Interpreter
    ↓ proposed invocation
Policy engine
    ↓ authorized invocation
Tool executor
    ↓
Structured result
```

A model or command parser never calls application functions directly.

### Acceptance criteria

- Read and ION tools use one executor.
- Every invocation is logged.
- Timeouts return explicit failures.
- Confirmation tokens cannot approve a different action.
- Proactive events cannot invoke user-only tools.
- No game-input execution exists yet.

## C3 — Elite binding discovery

**Status: implemented**

Understand available bindings before attempting control.

### Features

- Locate the active Elite `.binds` file.
- Parse primary and secondary bindings.
- Detect keyboard, mouse, HOTAS, controller, and unbound actions.
- Normalize Elite binding names into ION action IDs.
- Detect conflicts.
- Watch for binding-file changes.
- Produce a control-capability report.
- Add sanitized fixtures from real configurations.

Example:

```text
Landing gear
Primary: HOTAS Button 14
Secondary: Ctrl + Alt + G
ION status: Ready
Verification: Available
```

or:

```text
Night vision
Binding: None
ION status: Requires secondary keyboard binding
```

### Editing policy

The initial release must not silently rewrite Elite binding files.

ION should:

1. Explain which secondary binding is required.
2. Let the user configure it in Elite.
3. Refresh the capability report.
4. Provide a safe test in a later milestone.

Automatic editing may be considered only after backup and recovery behavior is
proven.

### Acceptance criteria

- Parser supports HOTAS, keyboard/mouse, and mixed fixtures.
- Missing or malformed files fail safely.
- Duplicate bindings are identified.
- Private commander data is not logged.
- Elite updates do not corrupt ION preferences.
- Discovery never sends an input.

## C4 — Local Input Bridge and manual control panel

Prove Class B control safety without language interpretation.

### Initial Green control pack

- Landing gear.
- Cargo scoop.
- Ship lights.
- Night vision.
- Galaxy Map.
- System Map.
- Navigation panel.
- Communications panel.
- Role panel.
- Internal panel.
- Balance power.
- Increase engines, systems, or weapons.

Hardpoints may be included but default to Amber.

### Input Bridge requirements

- Windows-local only.
- Elite must be running.
- Elite must be foreground.
- Only allowlisted action IDs.
- No arbitrary keys.
- One command at a time.
- Rate limits.
- Action timeout.
- Emergency-disable hotkey.
- Visible activity indicator.
- Local audit log.
- No public network listener.

### Manual control panel

The first operational controls should be buttons:

```text
[ GEAR DOWN ] [ SCOOP DEPLOY ] [ LIGHTS ON ]
[ GALAXY MAP ] [ SYSTEM MAP ]  [ BALANCE POWER ]
```

This validates the complete control path without speech or AI.

### Desired-state verification

For supported stateful controls:

1. Read current state.
2. Skip if already correct.
3. Send the configured binding.
4. Wait for telemetry confirmation.
5. Report verified, sent, or timed out.

### Acceptance criteria

- Disabled actions cannot execute.
- Unbound actions cannot execute.
- An unfocused game receives no input.
- Double-clicking cannot toggle a state twice.
- Timeouts do not cause automatic retries.
- Emergency disable stops pending actions.
- Manual controls work with AI disabled.

## C5 — Deterministic Computer Command Mode

Add the first functional Computer without a language model.

### Initial input methods

- Typed command console.
- Optional ION hotkey to focus input.
- Suggested-command buttons.

### Example intents

- “Brief me.”
- “Where am I?”
- “What is my next stop?”
- “Open route console.”
- “Find a round trip within 100 light-years.”
- “Exclude planetary stations.”
- “Landing gear down.”
- “Lights on.”
- “Balance power.”

### Behavior

- Rule-based intent recognition.
- Explicit synonyms.
- Number and filter extraction.
- Controlled follow-up context.
- Template responses.
- Confidence threshold.
- Clarification on ambiguity.

Example:

> “Find a round trip within 100 light-years.”
>
> “Remove fleet carriers.”
>
> “Show the safest result.”
>
> “Activate it.”

### Acceptance criteria

- Supported phrases behave deterministically.
- Unsupported requests clearly fail.
- Ambiguous controls request clarification.
- Background text cannot execute controls.
- Command Mode performs well on low-end hardware.
- The same tools remain usable by future AI modes.

## C6 — Voice output

Add speech before speech recognition.

### Features

- Offline Windows/Edge voice baseline.
- Selectable voice.
- Volume and speech rate.
- Brief, standard, and detailed responses.
- Speech queue.
- Critical-alert priority.
- Interrupt and dismiss controls.
- Suppression of ordinary speech during critical flight states.

### Acceptance criteria

- Text remains available.
- Speech failure does not block tools.
- Critical alerts interrupt normal dialogue.
- Repeated events do not create an announcement backlog.
- Command Mode can use voice output without AI.

## C7 — Speech recognition and wake word

Add voice commands only after manual and typed controls are stable.

### Input modes

- Push-to-talk.
- Wake word.
- Voice disabled.

Push-to-talk is the safest default.

### Voice pipeline

```text
Microphone
    ↓
Voice activity detection
    ↓
Wake word or push-to-talk gate
    ↓
Speech recognition
    ↓
Command/intent interpreter
    ↓
Policy and confirmation
```

### Safety

- Background conversation cannot bypass activation.
- Low-confidence Class B requests are rejected.
- Recognized text is displayed.
- Amber actions follow confirmation policy.
- The user selects the microphone.
- Listening and mute states are visible.

### Acceptance criteria

- False-activation testing covers music, game audio, and conversation.
- Low-confidence speech cannot execute controls.
- Emergency mute works immediately.
- Audio processing remains local by default.
- Microphone failures degrade to text mode.

## C8 — Planning and operation tool completion

Connect the remaining ION features.

### Planning tools

- One-way trades.
- Round trips.
- Trade Routes.
- Profitable Transit.
- Sell current cargo.
- Source commodity.
- Compare plans.
- Reachability.
- Replan from current state.

### Operation tools

- Activate operation.
- Advance or reverse progress.
- Pause or resume.
- Skip a stop.
- Replace route.
- Cancel route.

### Confirmation behavior

Searching does not require confirmation.

Confirmation is required for:

- Activating a route.
- Replacing a route.
- Cancelling a route.
- Changing protected reserves.
- Persistently changing preferences.

### Acceptance criteria

- Computer results match normal ION planner results.
- Business logic remains in the backend engine.
- Explanations include assumptions and confidence.
- The Computer cannot bypass reserves or access filters.
- Route activation survives restart.

## C9 — Proactive operational assistant

Build a deterministic alert engine before generative proactive behavior.

### Candidate alerts

- Fuel risk.
- No upcoming scoopable star.
- Dangerous hull or canopy.
- Cargo mismatch.
- Passed destination.
- Market data expiring before arrival.
- Insufficient destination demand.
- Reduced laden range.
- Unreachable active route.
- Completed operation step.
- Game-link disconnection.
- Nearby refuel or repair opportunity.

### Architecture

The deterministic alert engine decides:

- Whether an alert exists.
- Severity.
- Structured facts.
- Cooldown.
- Whether interruption is permitted.

A language layer may phrase an alert but cannot raise its severity.

### Acceptance criteria

- No duplicate alert spam.
- Alerts explain why they fired.
- Cooldowns and snoozing work.
- Proactive alerts cannot execute Class B controls.
- Every noncritical category can be disabled.
- Critical alerts remain concise.

## C10 — Computer Lite

Add the first optional local language model.

### Responsibilities

- Natural-language interpretation.
- Follow-up context.
- Concise explanations.
- Structured tool selection.
- Clarification questions.

### Restrictions

- No direct database access.
- No unbounded game-state context.
- No direct game control.
- No permission modification.
- No fabricated tool results.
- Every invocation still passes through the policy engine.

### Runtime targets

- CPU compatible.
- Quantized 1–3B model.
- Optional downloadable component.
- Approximately 2–4 GB memory target.
- Deterministic fallback.

### Acceptance criteria

- Works without a GPU.
- The model can be removed independently.
- Command Mode remains available.
- Tool-call accuracy meets a defined evaluation threshold.
- Unsupported requests fail safely.
- Hardware impact appears in diagnostics.

## C11 — Computer Enhanced

Add an optional larger local model.

### Improvements

- Better ambiguous-request handling.
- Richer comparisons.
- Longer conversational context.
- Better multi-action proposals.
- More natural system briefings.

### Runtime targets

- Quantized 7–14B class model.
- GPU acceleration where available.
- Configurable context and memory limits.
- Hardware benchmark before activation.

Enhanced receives the same permissions and tools as Lite.

### Acceptance criteria

- Automatic mode selects a safe runtime.
- The user can override or disable it.
- RAM/VRAM exhaustion falls back safely.
- Enhanced cannot bypass confirmation.
- Model updates are independently versioned and verified.

## C12 — Public-release hardening

### Technical work

- Crash recovery.
- Model-download verification.
- Corrupt-model recovery.
- Microphone diagnostics.
- Binding backup and recovery.
- Input latency and timeout telemetry.
- Accessibility review.
- Installer/component selection.
- Upgrade and migration tests.
- Privacy documentation.
- Local-data deletion controls.
- Security review for future remote devices.

### Policy work

Before publicly releasing generative Computer features using live Elite data:

- Request written clarification from Frontier concerning its AI-related EULA
  language.
- Document the one-shot input boundary.
- Confirm that no feature constitutes unattended automation.
- Keep generative AI separable from Command Mode and manual controls.

Frontier EULA:

https://www.frontier.co.uk/legal/eula

## Recommended delivery order

1. Merge PR #3. **Complete**
2. Build C1 settings. **Complete**
3. Build C2 safe ION tool execution. **Complete**
4. Build C3 binding discovery. **Complete**
5. Build C4 manual Input Bridge.
6. Build C5 deterministic text Computer.
7. Add C6 voice output.
8. Add C7 speech input.
9. Complete planning tools in C8.
10. Add deterministic alerts in C9.
11. Add Lite and Enhanced models last.
12. Complete public-release and policy review.

Every layer should remain useful independently. If local AI is too resource
intensive or policy-sensitive, ION still retains a deterministic Computer,
voice commands, and HOTAS-friendly control panel.

## Definition of complete integration

Computer integration is complete when:

- Command Mode works on every supported system.
- Lite and Enhanced are optional.
- Text, voice, and manual controls share one tool executor.
- ION and Class B controls use one policy engine.
- All controls are allowlisted and auditable.
- No raw input or autonomous gameplay exists.
- Active context and planner tools work reliably.
- Proactive alerts are deterministic and configurable.
- AI/audio/input failures fall back safely.
- Privacy, hardware use, and permissions are transparent.
- Frontier policy concerns are resolved before public generative release.
