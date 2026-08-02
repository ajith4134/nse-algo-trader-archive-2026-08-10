# B18 — SPEC: index-options strategy ensemble + adaptive meta-selector

Step 4 of `idea-to-institutional-spec`. **This is the contract the build is graded against.**

- Clarify (operator decisions): `index_options_profitability_clarify_decisions_2026-07-27.md`
- Research (SOTA + sourcing): `b18_index_options_ensemble_research_2026-07-27.md`
- Cost model (the denominator): `b28_indian_trading_cost_model_design_2026-07-27.md`

---

## 1 · Intent, and the decision it changes

Today the engine holds **0 index-option positions** while running 5 index underlyings, and routes
them through an ADX switch built for cash equity: trending → buy an ATM option on a spot ORB
breakout; range-bound → credit spread; ADX 20–25 → stand aside. That router knows nothing about
implied volatility, term structure, expiry proximity, or theta — the things that actually determine
whether an index-option trade has edge.

**The decision this engine changes:** for each index, at each look, *which strategy is deployed at
all, and at what size* — replacing a fixed ADX branch with a selector that learns from realised,
cost-adjusted outcomes which arm is working for that index in that regime, and reallocates.

**Why a thin version fails the intent.** A thin version is "add an IV-rank check to the existing
router". That would still be one hand-fixed policy; it could never answer the operator's actual
requirement — *"AI chooses which algorithm to follow based on their performance as more trades are
opened and closed"* — because there would be nothing learning from performance. The engine's whole
reason to exist is the feedback loop, and the feedback loop is the hard part (§4).

---

## 2 · Scope (Rule L) and the arms

**All 5 indices**, each gated by a per-index liquidity guard that ABSTAINS with a counted reason
rather than routing into a chain too thin to fill (operator decision D4).

The operator asked for "all algorithms". Research changed that to **three**, and the fourth is
rejected on arithmetic, not preference:

| arm | verdict | why |
|---|---|---|
| **A1 · IV-rank + term structure** | BUILD | IVR/IVP per tastytrade definitions; sell premium when IV rich, buy debit when cheap. SOTA analog **ORATS**. |
| **A2 · ADX regime router (repaired)** | BUILD | Already in-repo; close the 20–25 dead band, per-index thresholds. |
| **A3 · Trained direction + variance-risk-premium** | BUILD, activation-gated | GBM on engineered features; VRP via Carr & Wu; **Yang-Zhang** realized-vol estimator (handles NSE's pre-open/GIFT-Nifty gaps). SOTA analog **Qlib**. |
| **A4 · Delta-neutral / gamma scalping** | **REJECT** | Structurally multi-day: one session yields a single noisy realized-vol draw, while Indian per-rehedge costs (§B28, ~0.75% of turnover round trip) are paid on **every** rehedge with no amortisation. Recorded as a researched rejection, not a silent omission. |

**Hard constraints from research that the arms must obey:**
- **0-DTE logic is NIFTY-only.** Only NIFTY still has weekly expiries; the other four went
  monthly-only on 2024-11-20.
- **IV-rank must ABSTAIN for the four monthly-only indices until ~Sept 2026** — a 252-day IV
  lookback spanning the weekly→monthly transition compares unlike with unlike. Abstain, never emit a
  confident-looking rank over a structural break.
- Term-structure calendar spreads are **signal-only** — they cannot be executed under a forced
  intraday square-off.

---

## 3 · I/O contracts

**Arm input (per index, per look):** spot bars (5m, ≥28 for ADX warm-up), the per-underlying option
ladder (B9), live premiums per token, ATM IV (existing BS inversion), IV history for IVR/IVP,
per-index liquidity metrics (spread, OI, volume), and the B28 cost estimate for the candidate.

**Arm output — `ArmProposal`:** `arm_name` · `structure` (defined-risk only) · `legs` ·
`risk_amount_inr` · `expected_edge_inr` (**net of B28 costs**) · `confidence` · `abstained_reason`.
An arm that cannot form a view **abstains with a reason**; it never emits a neutral proposal that
looks like a decision.

**Selector input:** the candidate `ArmProposal`s + a context vector (index identity, ADX bucket,
IV-rank bucket, minutes-to-expiry, liquidity tier).
**Selector output — `ArmSelection`:** `chosen_arm` · `posterior_mean_edge` · `posterior_variance` ·
`effective_sample_count` · `was_forced_exploration` · `selection_reason`. Every field is required
because the dashboard must be able to explain *why* an arm was chosen (operator's auditability need).

**Reward (closed trade):** `realized_pnl − total_fees` (B28), converted to a **CVaR/mean-variance
adjusted** statistic before it updates any posterior — a premium-selling arm's rare large loss must
not be averaged away before enough tail events exist.

---

## 4 · The meta-selector — the hard part

**The finding that dictates the design:** every textbook family hits the same wall. The edge is
5–20% of per-trade noise SD at ~2.5–7.5 closed trades/day/arm, needing an effective memory of
**weeks to years**, while intraday-options regimes turn over in **days to ~2 weeks**. Plain Thompson
Sampling needs ~390 trades/arm for a 10-point gap (~4 months) and ~4,360 for a 3-point gap
(~3.5 years). No single algorithm satisfies both constraints.

**Therefore: a composite, not a library call.**
**Hierarchical (empirical-Bayes), discounted, contextual Thompson Sampling, with a permanent
forced-exploration floor and asynchronous delayed-reward updates.**

Four mandatory components, all concurrent:

1. **Hierarchical shrinkage** — each (arm × index × regime) cell's posterior mean is shrunk toward
   the arm's global mean and the grand mean, strength inverse to that cell's sample count. This is
   what keeps per-cell sample needs in the *weeks* regime rather than *years*, and it is how cold
   start is solved: a new cell inherits a population hyper-prior, never a flat one. (James-Stein;
   Dimmery-Bakshy-Sekhon KDD 2019, validated on 17 Facebook experiments — benefit *grows* with arm count.)
2. **Exponential discounting** of sufficient statistics, effective memory ~4–8 weeks. **Not**
   change-point detection: research shows CUSUM/BOCPD detection delay is inversely proportional to
   the same tiny signal plain comparison already struggles with — strictly harder, not easier.
3. **Burn-in gate** — no arm exceeds a near-uniform share of a context's traffic until it has
   **≥15–20 closed trades in that context**.
4. **Permanent ε-floor (10–15%)**, never phased out — so a temporarily-losing arm is never starved
   of the data needed to prove whether it was actually bad or merely unlucky.

**Delayed reward is solved, not hand-waved.** Joulani et al. (ICML 2013): in the stochastic setting
delay inflates regret only **additively**, and any non-delayed algorithm works unmodified via a
black-box reduction. Implementation: log `(arm, context, open_ts, trade_id)` as pending on open;
apply the posterior update whenever the trade closes; **never block selection on open trades**.

**Explicitly rejected, with reasons:** Bayesian Model Averaging (this is the M-open case — no arm is
"the truth" — where BMA provably collapses to a single candidate; Domingos ICML 2000 shows 120:1
weight ratios from *pure noise*), EXP3/EXP4 (bound not tight at realistic counts; needs edge larger
than we have), Hedge/MWU (needs full information — a shadow-fill model whose bias leaks silently
into the guarantee), NeuralUCB/TS (needs 2–11 years of data at this trade rate).

---

## 5 · ACCEPTANCE CRITERIA (pass/fail — this is what the build is graded on)

**Engine-grade (Rule P):**
1. Each arm is a real algorithm with carried state and a raw-input pipeline — not a scalar over a
   table. A1 computes IVR/IVP from a real IV history store; A3 trains a real model with a persisted
   artefact; the selector maintains real per-cell posteriors in a store that survives restart.
2. Output **changes behaviour**: `ArmSelection` determines which order is placed and at what size,
   at the live option entry sites. A display-only selector is a FAIL (Rule K).

**Correctness:**
3. **Every `expected_edge_inr` is net of B28 costs.** A gross-edge comparison is an automatic FAIL.
4. Reward is CVaR/mean-variance adjusted, not raw mean P&L.
5. The selector's posterior is **monotone in evidence**: a losing arm's share must not increase
   absent new favourable evidence (property test over randomised outcome sequences).
6. The ε-floor holds forever: over any long run, every arm in every context receives ≥ the floor
   share. No arm can be permanently starved.
7. Burn-in holds: with < 15 closed trades in a context, no arm exceeds the near-uniform cap.
8. IV-rank **abstains** for the four monthly-only indices while their lookback spans the
   weekly→monthly break; A1 emits `abstained_reason`, never a number.
9. The liquidity guard abstains with a counted reason on thin chains; MIDCPNIFTY/NIFTYNXT50 are
   never sized like NIFTY/BANKNIFTY.
10. 0-DTE-specific logic is unreachable for non-NIFTY underlyings.

**The profit bar (operator decision D3):**
11. **Positive net expectancy per trade after B28 costs**, over a minimum sample, per arm per
    context. Until that sample accrues the engine reports `gathering` and trades small — it never
    claims an edge it has not earned (Rule Q). `have N / need M` is shown per cell.

**Verification:**
12. Real-data (Rule F) pass on the live market; hermetic sim (Rule J) for the paths the market
    cannot exercise, with the real-data gap logged as an open blocker rather than waved through.

---

## 6 · Verification plan

- **Property tests:** ε-floor never violated over 10k simulated selections; posterior monotone in
  evidence; burn-in cap respected; shrinkage strictly reduces error vs raw per-cell means on
  synthetic cells with known truth (the James-Stein claim, tested rather than asserted).
- **Hermetic sim (Rule J):** inject synthetic closed-trade streams with a KNOWN best arm and assert
  the selector converges to it within a stated number of trades — and, critically, that it does
  **not** converge on a stream with no true edge (the overfitting test).
- **Rule F real-data:** an index-option position opens, lands in one of the 3 prediction tables, and
  its cost-adjusted outcome updates the selector posterior visibly on the dashboard.
- **Open blocker:** cost-adjusted expectancy cannot be evaluated until enough closed index-option
  trades exist. That is an accrual gap (the one permissible Rule-K blocker), not a reason to ship a
  selector that pretends to know.

---

## 7 · Depth justification (what a thin version would omit)

A thin version would: use one global ADX branch instead of per-(index × regime) cells; compare gross
edge; use raw mean P&L instead of a tail-aware statistic; have no burn-in, no shrinkage, no ε-floor
(and so lock onto a noise winner within days); treat delayed rewards by batching at end-of-day; and
emit a chosen arm with no posterior/variance/sample-count, making it unauditable. Each omission maps
to a specific failure the research documented — this is why the size is real function, not padding.

---

## 8 · Decomposition (build order)

1. `strategy_engine/implied_volatility_rank.py` — IVR/IVP + IV history store + the abstain rule.
2. `strategy_engine/option_strategy_arms.py` — A1/A2/A3 behind one `ArmProposal` contract.
3. `paper_trading/option_liquidity_guard.py` — per-index spread/OI/volume gate with counted abstains.
4. `paper_trading/arm_selection_posterior_store.py` — per-cell sufficient statistics, discounting,
   restart-durable.
5. `paper_trading/adaptive_arm_selector.py` — hierarchical shrinkage + contextual TS + burn-in +
   ε-floor + async delayed-reward updates.
6. Integration at the option entry sites; `ArmSelection` recorded on the trade (feeds B27).
7. Dashboard surface `arm_selector` (Rule N): per-cell posterior mean ± variance, effective sample
   count, `have N / need M`, chosen-arm share, forced-exploration rate, and per-arm cost-adjusted
   expectancy.

**OSS to integrate (sourced, verified):** `PyBandits` or `river` as the posterior core;
`vollib`/`QuantLib` for greeks/IV; LightGBM for A3. The shrinkage/discount/floor/async wrapper is
in-repo — bounded custom code, not reimplementing bandit math.

---

## 9 · Prerequisites and open blockers (Rule K)

| item | state |
|---|---|
| **B9** per-underlying expiry | ✅ DONE 2026-07-27 (four indices would otherwise vanish 3 weeks in 4) |
| **B28** cost model | ✅ DONE 2026-07-27 — the denominator of criterion 3 |
| **B30** historical options data vendor for A3 | ⛔ OPEN — Kite flushes option tokens each expiry, so multi-year option-level training data is infeasible through the broker alone. A3 must either wait, or train on spot+IV features only as an explicitly recorded decision. |
| **B29** stop-fill realism | ⛔ OPEN — SL-M is banned on NSE options; a triggered stop can fail to fill. Expectancy assuming certain fills is optimistic. |
| **B16** index entries still gated | ⛔ OPEN — positioning veto, high-stakes oversight, and the ADX 20–25 dead band still block index entries regardless of which arm is selected. **B18 cannot produce a single index trade until these are addressed** — this is the most important open item on the whole spec. |

---

## 10 · The one residual choice for the operator

Given the sample-rate wall (§4), the selector will spend its **first several weeks in burn-in**,
allocating near-uniformly across arms while evidence accrues. That is the honest consequence of
tens of trades per day — not a defect. The choice: accept that (recommended — it is what makes the
eventual selection trustworthy), or bias early allocation toward A2, the only arm with existing
live history. I recommend accepting burn-in; biasing toward the incumbent is exactly how a noise
winner gets locked in.
