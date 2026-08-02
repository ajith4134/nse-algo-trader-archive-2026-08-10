# VII — power budgets (🟡→🟢 upgrade)  ·  research/120

**Trunk VII CONSCIENCE, branch: power budgets.** Design doc (Rule D).

## The idea & the upgrade
A "power budget" in AI safety is an explicit cap on how much an agent can affect the world — its
"power" — regardless of goal. Today this branch is 🟡: `trading_control_config` holds max
risk/capital *per trade*, a fragment. The upgrade to 🟢 is a real **power-budget organ** that meters
the agent's CUMULATIVE DAILY power expenditure and enforces an explicit budget.

The chosen power axis: **daily action throughput** — the number of orders (market interventions) the
agent places per day. This is the cleanest goal-independent measure of "how much the agent is acting
on the world," it resets daily, and it is distinct from the two neighbours:
- **Instrumental-convergence limiter** caps CONCURRENT exposure sprawl (a snapshot).
- **SEBI order-rate throttle** caps orders per SECOND (a micro-rate).
- **Power budget** caps orders per DAY (cumulative daily footprint) — a different axis: an agent can
  churn thousands of intraday round-trips at low concurrency and low per-second rate yet still exert
  enormous daily market power. The daily budget bounds that.

## Component parts (`conscience/power_budget.py`, pure)
- **`PowerBudget`** (frozen) — `max_orders_per_day` (a real backstop above normal daily load).
- **`PowerBudgetVerdict`** (frozen) — `permit`, `breached`, `reason`.
- **`assess_power_budget(orders_placed_today, budget)`** — blocks when the daily action budget is
  exhausted; else permits.

## Wiring (Rule G/N — wired-into-decisions)
`LiveUniversePaperState.power_budget_permits_order(now)` — a daily-resetting counter
(`power_budget_orders_today`, `power_budget_day`); resets on a new date, blocks + counts when the
budget is spent, else increments and permits. Called at ALL 4 entry sites after the convergence
limiter. Dashboard surface `power_budgets` (orders today / budget, blocks). Rule N.

## Verification
- **Hermetic (Rule J):** under budget → permit + increments; at budget → block + count; a new day →
  the counter resets and permits again.
- **Real-data (Rule F):** the live service composes the gate; on the real service state normal load
  is under the daily budget (permit), and an exhausted budget blocks — over the real state.

## Backlog (Rule K)
- 🔵 **Capital-deployed-fraction axis** (a 2nd power meter: fraction of account capital at risk) —
  needs open-notional grouping threaded from the entry sites; the daily-action budget ships first.

## Atlas impact
power budgets 🟡→🟢. VII CONSCIENCE 12🟢→13🟢. Overall partial 60→59, built 39→40 / 197 (20.3%).
