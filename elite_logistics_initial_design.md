# Elite Logistics — Initial Design Specification

**Status:** Initial design / pre-implementation
**Primary target:** Local web application
**Primary use case:** Elite Dangerous trade, travel, and logistics planning
**Initial development environment:** Local PC, Codex-assisted development

---

## 1. Product Vision

Elite Logistics is a personal Elite Dangerous logistics companion focused on answering practical questions that existing trade tools do not always answer well.

The core question is:

> Given where I am, what I am flying, how much cargo and money I have, and where I want to go, what is the best thing for me to do next?

The application should combine useful concepts from tools such as Inara and Spansh while placing greater emphasis on:

- Route practicality rather than raw profit alone.
- Travel time and station distance.
- Market-data freshness and confidence.
- Round-trip profitability.
- Opportunity cost when relocating to a better trade route.
- Profitable travel between two arbitrary locations.
- Future expansion into colonization logistics, passenger planning, and exploration support.

The application is intended to be useful as a standalone planning tool even when Elite Dangerous is not running or installed on the current computer.

---

## 2. Core Design Principles

### 2.1 Manual state is canonical

The application must always work with manually entered data.

Examples:

- Current system
- Current station
- Ship
- Cargo capacity
- Laden jump range
- Available credits
- Pad requirement

Optional Elite Dangerous integration may auto-fill these values later, but game integration must never be required for core functionality.

### 2.2 Optimize for useful routes, not just maximum CR/t

A route with the highest apparent profit may be worse because it:

- Requires many jumps.
- Has a long supercruise distance.
- Uses old market data.
- Has weak supply or demand.
- Requires relocation before trading begins.
- Has a destination unlikely to remain profitable by the time the player arrives.

The planner should rank routes using multiple dimensions.

### 2.3 Show trade-offs instead of pretending there is one perfect answer

Where appropriate, provide multiple options such as:

- Fastest
- Balanced
- Most profitable

This is especially important for profitable transit planning.

### 2.4 Local-first architecture

The application should run locally and store its main state locally.

Recommended stack:

- Frontend: React + TypeScript + Vite
- Backend: Python + FastAPI
- Database: SQLite
- Local API: REST initially; WebSocket support when live game-state or market updates are added

---

## 3. Major Features

### 3.1 Best Trades

Find profitable one-way commodity trades based on player and ship constraints.

Inputs may include:

- Current system or station
- Cargo capacity
- Laden jump range
- Available credits
- Maximum jumps
- Maximum route distance
- Maximum station distance from arrival star
- Minimum supply
- Minimum demand
- Maximum market-data age
- Required landing-pad size
- Surface-station toggle
- Fleet-carrier toggle
- Odyssey-settlement toggle

Sorting/ranking modes:

- Recommended
- Maximum trip profit
- Profit per tonne
- Profit per jump
- Estimated credits per hour
- Convenience

Expected route output:

- Source station/system
- Destination station/system
- Commodity
- Buy price
- Sell price
- Profit per tonne
- Purchasable tonnes
- Expected trip profit
- Number of jumps
- Total system distance
- Destination distance from star
- Market data age
- Supply/demand
- Confidence rating
- Estimated trip time
- Estimated CR/hour

---

### 3.2 Round Trips

Find profitable two-way loops where the player carries useful cargo in both directions.

Example:

A -> B: Gold, +1.5M CR
B -> A: Consumer Technology, +1.0M CR

Total round-trip profit: +2.5M CR

The planner should calculate:

- Outbound commodity and profit
- Return commodity and profit
- Total cycle time
- Total round-trip profit
- Estimated CR/hour
- Supply/demand confidence on both legs

Round-trip mode is considered a core feature, not an optional extension.

---

### 3.3 Profitable Transit Planner

This is a first-class feature and one of the main differentiators of Elite Logistics.

#### Purpose

Allow the player to travel from an origin to a destination while making money along the way.

Typical scenarios:

1. The player finds a very profitable trade route that is hundreds of light-years away.
2. The player needs to travel somewhere for another reason and wants to offset travel time with cargo profits.
3. The player wants a route that is not strictly shortest-distance, but balances progress and earnings.

#### Inputs

- Origin system/station
- Destination system/station
- Ship profile
- Cargo capacity
- Laden jump range
- Available credits
- Maximum station distance
- Market-age limit
- Supply/demand minimums
- Pad requirement
- Maximum acceptable detour
- Travel preference

Travel preference should support at least:

- Fast
- Balanced
- Profit

A continuous slider may later map between these profiles.

#### Output

Provide at least three route options when possible:

**Fast**
- Minimal deviation
- Takes trades only when they add little travel time

**Balanced**
- Default mode
- Meaningful profit while maintaining strong progress toward destination

**Profit**
- Allows larger detours if additional expected earnings justify them

Each option should show:

- Total travel distance
- Estimated number of jumps
- Estimated time
- Number of trade stops
- Expected transit profit
- Extra time versus direct travel
- Additional earnings versus direct travel
- Market confidence

Example summary:

Direct route:
- 270 ly
- 18 jumps
- ~27 min
- 0 CR earned

Balanced profitable transit:
- ~295 ly total
- 4 trade legs
- ~41 min
- +3.5M CR

Difference:
- +14 min
- +3.5M CR earned during relocation

#### Progress constraint

The route must not optimize profit by sending the player arbitrarily far away from the destination.

A configurable detour constraint should be supported, for example:

- 10%
- 20%
- 40%
- Unlimited

Default recommendation: approximately 20%.

The planner should reward movement toward the destination and penalize excessive lateral or backward travel.

#### Route-planning approach

Do not require a globally optimal solution in the first implementation.

Recommended initial approach:

1. Build a travel corridor between origin and destination.
2. Identify candidate stations/systems within that corridor.
3. Generate profitable cargo legs between candidates.
4. Reject candidates exceeding the detour limit.
5. Score each leg using profit, progress, time, freshness, and risk.
6. Use a constrained heuristic or beam-search approach to build several good routes.
7. Compare each profitable route against the direct-travel baseline.

Future alternatives may include:

- A* variants
- Multi-objective Dijkstra
- Pareto-frontier route search
- More advanced beam search

---

### 3.4 Opportunity-Cost / Relocation Analysis

When a trade route is far away, the application should evaluate whether moving there is actually worthwhile.

Inputs may include:

- Current route CR/hour
- Target route expected CR/hour
- Distance to target route
- Direct travel time
- Profitable-transit time and earnings
- Planned play/session duration
- Market-data age

The application should estimate:

- Lost income during relocation
- Income recovered during profitable transit
- Estimated break-even time after arrival
- Expected total earnings over the planned session

Example:

Nearby route:
- 6M CR/hour
- 5 minutes away

Distant route:
- 10M CR/hour
- 40 minutes away

For a 1-hour session, the nearby route may be better.
For a 4-hour session, the distant route may be better.

Planned playtime options may include:

- 30 minutes
- 1 hour
- 2 hours
- 4 hours
- No limit

---

### 3.5 Sell My Cargo

Given cargo already onboard, determine the best practical place to sell it.

Inputs:

- Current cargo manifest
- Current system
- Ship constraints
- Maximum travel distance
- Market-age limits

Output:

- Best combined destination(s)
- Expected sale value
- Estimated profit if purchase prices are known
- Jumps/time
- Confidence

Future game integration may auto-populate the cargo manifest from Cargo.json.

---

### 3.6 Source Commodity

Given one or more required commodities, identify good places to buy them.

Useful for:

- Missions
- Colonization
- Community Goals
- Personal logistics

Output should prioritize:

- Availability
- Supply
- Price
- Travel time
- Station access
- Data freshness

---

## 4. Route Scoring Concepts

### 4.1 Basic trade math

Profit per tonne:

profit_per_ton = destination_sell_price - source_buy_price

Purchasable tonnes:

purchasable_tons = min(
    cargo_capacity,
    source_supply,
    floor(available_credits / buy_price)
)

Trip profit:

trip_profit = profit_per_ton * purchasable_tons

### 4.2 Recommended-route score

Do not define the exact final formula yet.

Conceptually:

Route Score =

- Profit reward
- Destination-progress reward
- Data-confidence reward
- Supply/demand confidence reward
- Travel-time penalty
- Jump-count penalty
- Supercruise-distance penalty
- Detour penalty
- Stale-data penalty

The exact weights should remain configurable during development and testing.

### 4.3 Estimated credits per hour

Estimated CR/hour should account for more than hyperspace distance.

Time model may initially include:

- Average hyperspace jump duration
- Supercruise time
- Docking time
- Station departure time
- Planetary approach penalty
- Number of stops

Initial static estimates are acceptable.

Future optional personalization can calculate actual averages from Elite journal timestamps.

---

## 5. Market Confidence

Every route should communicate how trustworthy its profit estimate is.

Suggested confidence inputs:

- Age of source market data
- Age of destination market data
- Source supply relative to required cargo
- Destination demand relative to required cargo
- Estimated time until arrival
- Fleet carrier versus permanent station

Example ratings:

### High confidence
- Updated recently
- Supply/demand far exceeds cargo amount
- Short arrival time

### Medium confidence
- Moderate age
- Adequate but not abundant supply/demand

### Low confidence
- Old data
- Supply/demand near cargo requirement
- Long travel time

Users should be able to hide low-confidence routes.

A distant route should receive additional risk if its price data may be stale by the estimated time of arrival.

---

## 6. Ship Profiles

Ship data should be stored separately from route searches.

Suggested fields:

- Profile name
- Ship model
- Cargo capacity
- Unladen jump range
- Laden jump range
- Required landing-pad size
- Shielded/unshielded
- Fuel scoop available
- Optional notes

Examples:

- Cobra Mk III — General
- Type-6 — Cargo
- Dolphin — Passenger
- Asp Explorer — Exploration
- Type-9 — Bulk

Manual values must always be editable.

Optional game integration may create or update profiles automatically later.

---

## 7. Credit / Risk Controls

The route planner should not assume all credits are available to purchase cargo.

Support:

- Current balance
- Rebuy reserve
- Optional extra cash reserve

Suggested setting:

**Never spend rebuy reserve**

Available trading capital:

available_trade_credits =
    total_credits
    - rebuy_reserve
    - user_cash_reserve

This setting should default to enabled once rebuy data is available.

---

## 8. Data Sources

### 8.1 Spansh

Use as the initial external data source because it provides accessible station/system data and lowers the complexity of the first implementation.

Purpose in early phases:

- System lookup
- Station lookup
- Market information where available
- Bootstrap/reference data

The application should isolate Spansh access behind a data-provider interface so it can later be supplemented or replaced without changing route logic.

### 8.2 EDDN

Add later as a live community-data source.

Purpose:

- Commodity updates
- Station market updates
- System/station updates
- Other relevant community observations

Recommended model:

Spansh -> bootstrap/reference data
EDDN -> fresh updates
Local SQLite -> application query source

### 8.3 Elite Dangerous local files — optional

Potential sources:

- Journal.*.log
- Status.json
- Cargo.json
- Market.json
- Shipyard.json

Potential auto-detected state:

- Commander
- Credits
- Current system
- Current station
- Current ship
- Cargo
- Destination
- Current market
- Fuel
- Jump range where derivable

Important architectural constraint:

**No core feature may depend on these files being present.**

They are an optional input adapter only.

---

## 9. Suggested Internal Architecture

```text
Frontend (React / TypeScript)
        |
        | REST initially
        v
Backend (FastAPI)
        |
        +-- Route Engine
        +-- Trade Scoring
        +-- Transit Planner
        +-- Data Provider Layer
        |      +-- Spansh Provider
        |      +-- EDDN Provider [later]
        |      +-- Local Game Adapter [later]
        |
        +-- SQLite Repository
```

Future WebSocket usage:

- Local game-state updates
- EDDN updates
- Long-running route searches if necessary

---

## 10. Suggested Database Model

### systems

- id64
- name
- x
- y
- z
- permit_required
- updated_at

### stations

- market_id
- system_id64
- name
- station_type
- distance_to_star_ls
- largest_pad
- planetary
- fleet_carrier
- odyssey
- updated_at

### commodities

- commodity_id
- name
- category

### market_prices

- market_id
- commodity_id
- buy_price
- sell_price
- supply
- demand
- timestamp
- source

### ship_profiles

- id
- name
- ship_model
- cargo_capacity
- unladen_jump_range
- laden_jump_range
- pad_size
- has_fuel_scoop
- shielded
- notes

### user_preferences

Examples:

- max_market_age
- max_station_distance
- min_supply_multiplier
- min_demand_multiplier
- include_surface
- include_fleet_carriers
- detour_limit
- preferred_route_mode
- preserve_rebuy

### player_state

Optional/cache-like state:

- current_system
- current_station
- selected_ship_profile
- credits
- cargo_used
- source
- updated_at

---

## 11. Primary UI Structure

### Dashboard

Display current/manual player state and shortcuts.

Suggested actions:

- Best Trade
- Round Trip
- Sell My Cargo
- Source Commodity
- Profitable Transit

### Trade

- Best Trades
- Round Trips
- Sell Cargo
- Source Commodity

### Travel

- Profitable Transit
- Route Comparison

### Colonization

- Logistics Planner [later]

### Passengers

- Future

### Exploration

- Future

### Ships

- Manage ship profiles

### Settings

- Market freshness
- Supply/demand thresholds
- Station filters
- Detour defaults
- Reserve settings
- Optional game integration

---

## 12. Dashboard Concept

Example:

```text
ELITE LOGISTICS

Current state
Type-6 Transporter
Ohm City - LHS 20
104 t capacity
18.7 ly laden
12.4M CR available

[ Best Trade ]
[ Round Trip ]
[ Sell My Cargo ]
[ Source Commodity ]
[ Profitable Transit ]

Recommended nearby trade
Ohm City -> Example Station
Silver - 104 t
+1.47M CR
2 jumps
~7m 20s
~12M CR/hour
High confidence
```

The home screen should be action-oriented rather than a generic commodity database.

---

## 13. Colonization Expansion

Colonization is not part of the first MVP, but the architecture should support it later.

Future Colonization Logistics mode should accept a required-material list and optimize acquisition/delivery rather than profit.

Example:

```text
Required
Aluminium          2,400 / 8,000
Steel              5,100 / 12,000
Power Generators     800 / 3,000
```

Planner output may include:

- Best source stations
- Best sequence of pickup runs
- Mixed-load recommendations
- Expected number of trips
- Travel time
- Cost
- Completion percentage

The same system/station/commodity routing engine should be reused.

---

## 14. Passenger and Exploration Expansion

Not required initially.

Potential future modes:

### Passenger planner

- Passenger cabin compatibility
- Mission destination planning
- Sightseeing itinerary optimization
- Route length
- Passenger restrictions

### Exploration support

- Route planning
- Destination selection
- Profitable/scenic detours
- Exobiology integration
- Fuel-scoop/star-type constraints

These features should reuse the shared system graph rather than becoming separate applications.

---

## 15. Development Phases

### Phase 1 — Core Trade Finder

Goal: prove that useful trade ranking works.

Build:

- Local frontend
- FastAPI backend
- SQLite
- Spansh integration
- Manual current location
- Manual ship profiles
- One-way trade search
- Basic filters
- Basic sorting
- Market data age display

### Phase 2 — Trade Optimization

Add:

- Round trips
- Estimated CR/hour
- Route-quality score
- Supply/demand safeguards
- Confidence scoring
- Rebuy reserve support
- Convenience ranking

### Phase 3 — Profitable Transit

Add:

- Origin/destination planner
- Direct route baseline
- Trade corridor
- Detour constraint
- Fast/Balanced/Profit profiles
- Multi-leg cargo route planning
- Estimated transit profit
- Extra-time comparison
- Standalone travel mode
- "Trade My Way There" action from distant trade routes

### Phase 4 — Relocation Intelligence

Add:

- Current versus target route comparison
- Opportunity cost
- Break-even calculation
- Planned session duration
- Estimated session earnings
- Arrival-time-adjusted market risk

### Phase 5 — Optional Elite Integration

Add:

- Journal watcher
- Status.json support
- Cargo.json support
- Automatic location
- Automatic balance
- Automatic ship/profile selection
- Automatic cargo state

Manual mode remains fully functional.

### Phase 6 — EDDN

Add:

- Live EDDN listener
- Market update ingestion
- Local cache freshness
- Source tracking

### Phase 7 — Colonization Logistics

Add:

- Material requirements
- Commodity sourcing
- Multi-run planning
- Completion tracking

### Phase 8 — Passenger / Exploration Support

Optional future work.

---

## 16. Initial Non-Goals

Do not include these in the first implementation unless they become necessary:

- Full 3D galaxy map
- Full Inara replacement
- Commander social/profile features
- Engineering planner
- Combat planner
- Fleet management beyond ship profiles
- Perfect globally optimal transit routing
- Mandatory live Elite integration
- Cloud hosting/accounts
- Multi-user synchronization

Tables and route cards are preferred over a complex map in the early versions.

---

## 17. Open Design Questions for Codex / Implementation Planning

These should be finalized before or during Phase 1 implementation.

1. Exact Spansh endpoints and caching strategy.
2. Whether market data should be queried on demand or periodically cached locally.
3. Initial system/station search radius strategy.
4. Exact route-score weights.
5. Initial travel-time estimation model.
6. Whether route calculations run synchronously or as background backend jobs.
7. Maximum candidate count for trade and transit searches.
8. Initial confidence-rating thresholds.
9. Exact SQLite schema and indexes.
10. Whether ship profiles should include module-level detail or only derived values.
11. Whether frontend state should use a dedicated state-management library or remain simple React state initially.
12. How to represent multiple data sources when Spansh and EDDN disagree.
13. Whether historical market snapshots should be retained for trend/confidence analysis.

---

## 18. Initial Success Criteria

The first useful version should let a player:

1. Manually select current location.
2. Select or create a ship profile.
3. Enter available credits.
4. Find profitable nearby trades.
5. Filter out impractical stations and stale markets.
6. Compare trade options by profit, time, and confidence.
7. Find profitable round trips.
8. Plan a profitable journey toward a chosen destination.
9. Compare that journey against direct travel.

If those workflows are reliable, the project already provides meaningful value before any live game integration or EDDN ingestion is added.

---

## 19. Product Identity

Working name: **Elite Logistics**

Possible later alternatives:

- Elite Logistics Copilot
- TradeNav
- CargoNav
- RouteRunner
- Stellar Logistics

The working name should not block implementation.

---

## 20. Summary

Elite Logistics should not be designed as another commodity-price database.

Its core strength should be **decision support**:

- What trade is best for my actual ship?
- Is a distant high-profit route really worth relocating to?
- Can I make money while traveling there?
- How much extra time am I spending for that profit?
- How confident should I be that the market will still be useful when I arrive?

The initial implementation should favor clear, useful trade and travel decisions over feature breadth.
