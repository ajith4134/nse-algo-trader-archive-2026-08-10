# Slice 3 — Terminal-distribution model + Structure Payoff Optimizer (option_alpha)

The ultra-tier of the redesign + the user's explicit ask: the bot should **come up with its own trade ideas**
— synthesize the structure that maximizes expected value for the forecast, from the REAL live chain, rather
than pick from a fixed template library. This is a distributional payoff optimizer over real strikes/prices.

## Two engines
### A. `terminal_distribution_model.py` — regime-conditioned terminal price distribution
From the volatility-regime engine's forecast σ (annualized) + the directional verdict (drift) + the tenor to
expiry, build a Monte-Carlo sample of the underlying's price AT EXPIRY:
`S_T = S_0 · exp((μ − ½σ²)·T + σ·√T·Z)`, `Z ~ Student-t(ν)` (fat tails, ν from the regime — calm→high ν,
stressed→low ν). Drift μ from the arbiter conviction (0 when NEUTRAL). A mixture over the regime posterior
(calm/elevated/stressed each contribute their σ, weighted by probability) makes it regime-conditioned, not a
single lognormal. Output: an array of terminal prices + the tenor.

### B. `structure_payoff_optimizer.py` — synthesize the max-EV defined-risk structure
Given the LIVE chain (real strikes + CE/PE LTP + OI), the terminal distribution, the target profit-engine
(from the scorer), and constraints, ENUMERATE candidate structures built from real strikes and pick the best:
- **Candidate generation** per engine: Θ → short verticals / iron condors / short strangles across strike
  widths around ATM; Δ → debit spreads (long ATM, short OTM) in the trend direction; ν/Γ → long straddle/
  strangle; RV → skewed (broken-wing) condors. Each candidate is CONCRETE legs (real strike, right, buy/sell,
  live price).
- **Pricing each candidate over the distribution**: entry cashflow = Σ (sell premium − buy premium) from the
  live LTP; terminal value = Σ leg intrinsic at each `S_T` sample; per-sample P&L = terminal − entry (× lot).
  Compute **E[P&L]**, **max loss** (worst sample / defined-risk width), **CVaR₅**, **P(profit)**.
- **Objective**: maximize E[P&L] (or E[P&L] / |CVaR| — risk-adjusted) subject to (1) DEFINED RISK (max loss ≤
  a cap fraction of capital), (2) LIQUIDITY (every leg's OI/volume ≥ a floor), (3) the engine's greek sign
  (e.g. Θ must be net-short-vega/positive-theta). Return the winning structure as an `OptionStructurePlan`
  with real strikes + its E[P&L]/CVaR/P(profit) provenance.
This is the bot INVENTING the trade: it searches the real strike grid and composes the structure — including
non-template ones like a broken-wing condor skewed to the drift — that the distribution says pays best.

## Why engine-grade (not a scalar)
Real Monte-Carlo simulation (regime-mixture Student-t), a combinatorial search over the real strike grid,
real option pricing from live premiums, real risk metrics (CVaR, max-loss, P(profit)), hard constraints, and
a decision output that is the ACTUAL structure the bot trades. SOTA analog: a scenario-based option-portfolio
optimizer (Riskfolio / a payoff-space EV maximizer). It changes what every option trade IS.

## Integration
The bots (both) run the optimizer for the scorer's `best_engine` on the live chain in `_build_proposal`,
replacing the fixed moneyness-offset template with the synthesized real-strike structure. The selector's
`select_for_engine` stays as the fast fallback when the optimizer can't (no live chain / too few strikes).
The chosen structure's E[P&L]/CVaR/P(profit) flow into the proposal provenance + the win-prob head features.

## Verification (Rule F, live)
On the live NIFTY/BANKNIFTY chain: build the distribution from the real regime σ; run the optimizer for Θ and
Δ; confirm it returns CONCRETE real strikes, positive E[P&L] candidates exist, defined-risk + liquidity
constraints hold, and the synthesized structure differs sensibly by engine + drift. Eyeball the numbers
(E[P&L], max loss, P(profit)). Hermetic test (Rule J): a small synthetic chain + fixed distribution → the
optimizer picks the known-best structure; degenerate inputs are safe.

## Sourcing (Rule I)
Integrate `numpy`/`scipy.stats` (Student-t sampling, percentiles for CVaR) — already deps. `cvxpy`/`pymoo`
are available but the candidate set is small + discrete (real strikes), so a direct enumerate-and-score is
exact and faster than a solver here; a solver is warranted only if the leg space explodes (queued). Bespoke
payoff math (intrinsic value per leg) is small + exact. Logged.

## Backlog (Rule K)
- Solver-based search (pymoo/CVXPY) if the candidate space grows (multi-expiry calendars, ratios).
- Real per-leg exit marking (slice 4) uses the same intrinsic/premium math.
- Greeks from a pricing model (vollib) for a greek-target refinement of the objective.
