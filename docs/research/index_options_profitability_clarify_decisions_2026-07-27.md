# Index-options profitability — CLARIFY decisions (2026-07-27)

Step 2 of `idea-to-institutional-spec`. These are the operator's answers to the forced MCQ; they are
the contract the spec (step 4) will be written against. **No code has been written to this yet.**

## The idea, restated

Make NSE index options (NIFTY, BANKNIFTY, FINNIFTY, MIDCPNIFTY, NIFTYNXT50) trade **profitably** —
not merely place orders. Grounded in live measurement 2026-07-27: `index_option` open = 0 all
session, while `stock_option` = 15 and `cash` = 51.

Three problems were tangled in the request; only the third is a design question:

| # | Problem | Kind |
|---|---|---|
| a | Organism-vitality gate returns size multiplier **0.0** → vetoes EVERY entry, both segments | defect |
| b | Scanner livelocked at 231/9,292 (B1 bond deadlock) + options seeded once per process (B8) | defect |
| c | **Index options have no strategy designed for them** — they ride a cash-equity ADX router | **design** |

On (c): the current router is ADX-only — trending → buy an ATM option on a spot ORB breakout;
range-bound → credit spread; 20–25 → stand aside. It ignores everything specific to index options
(weekly expiries, IV rank, term structure, 0-DTE behaviour, theta bleed on a bought ATM option in an
intraday-only system). Making orders *go through* would not make them profitable.

## Decisions

### D1 · Sequencing — **outage + starvation first**
Fix the vitality zero-veto, B1 (bond deadlock) and B8 (option re-seeding) BEFORE spec'ing the index
engine. Rationale: this restores trading across cash + ~210 stock-option underlyings + ~2,000 cash
names, and produces **real index-option trades to design against** instead of designing against zero
observations.

### D2 · Algorithm class — **ALL of them, with an adaptive meta-selector** (operator's own answer)
> *"all algorithms and AI chooses which algorithm to follow based on all these algorithms'
> performance as more trades are opened and closed"*

This is materially different from picking one strategy. The engine is a **strategy ensemble + an
online meta-allocator** that learns, from realized closed-trade performance, which arm to deploy per
index and per regime. Arms to build (all of them, not a subset):

1. **IV-rank + term-structure** — sell defined-risk premium when IV is rich vs its own history; buy
   debit/directional structures when IV is cheap; expiry-aware.
2. **ADX regime router (repaired)** — the existing path with the 20–25 stand-aside dead band closed
   and per-index thresholds.
3. **Trained model** — predicts index direction and realized-vs-implied vol; sizes by predicted edge.
4. **Delta-neutral / gamma scalping** — delta-hedged position scalping gamma intraday.

The selector must be a real online-learning allocator over arms (contextual bandit / regret-minimising
family), NOT a hand-tuned if/else. It must handle the cold start honestly: with no closed trades it
cannot know which arm is best, so it explores under the Rule-Q maturity ladder rather than committing.

**Existing machinery to compose with (do NOT reimplement — Rule P.3 / Rule G):**
`llm_strategy/meta_strategy_allocator.py`, `paper_trading/champion_challenger_orb_evaluator.py`,
`paper_trading/strategy_promotion_gate.py`, the `prediction_lab` scoreboard, and
`memory_reflection` (which already supplies per-mechanism recalibration + antibody vetoes).

### D3 · Profit bar — **positive net expectancy per trade, with a maturity ladder**
Expectancy after realistic brokerage + slippage + spread cost must be > 0 over a minimum sample. Until
that sample accrues, the engine reports `gathering` and trades small — it never fakes an edge it has
not earned (Rule Q). This is the pass/fail acceptance gate the built engine is graded against.

### D4 · Index scope — **all 5, with a per-index liquidity guard**
Full universe per Rule L. Each index must pass a spread / OI / volume test before an entry; when the
chain is too thin the engine **abstains with a counted, surfaced reason** rather than routing an order
into a chain where slippage would silently eat the edge. No index is dropped silently.

## Decided WITHOUT asking (settled by the repo or the rules)
- Intraday-only, forced square-off before close — non-negotiable, project-wide.
- Defined-risk structures only — existing v1 risk policy.
- Every index trade lands in one of the 3 prediction tables (confident_win / confident_loss /
  uncertain) like every other trade — the operator confirmed this expectation.
- How to repair the vitality gate — a defect, not a design choice.

## Still to do (Rule K — queued, not silently skipped)
- **Step 3 RESEARCH** — `deep-research` the real algorithms + a named SOTA analog for each of the 4
  arms AND for the meta-selector; `sourcing-oss-parts` per part with every rejection surfaced.
  **NOT YET RUN.**
- **Step 4 SPEC** — the institutional spec with I/O contracts, acceptance criteria, verification plan,
  depth justification, decomposition, dashboard surface.
- **Step 5/6** — confirm, then hand off to `building-engine-grade-features`.

Deferred behind D1 (the outage + starvation fixes). Tracked in `docs/BACKLOG.md` as B18.
