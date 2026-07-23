# 29 — Prediction-Labeled Trade Tables: the Falsification-Driven Paper Lab

**Origin:** user's core concept (2026-07-23, before Layer 7): the paper
AI runs multiple open-trades tables — one for trades it is confident
will WIN, one for trades it deliberately opens because it predicts they
will LOSE (with reasons, not coin-flips), plus a third table of my
design — so that outcomes verify or falsify the AI's causal
understanding of profit and loss. This document maps the full space of
that idea and fixes the design that Layers 7 and 10 will implement.

**Status: DESIGN ADOPTED into PLAN §9. Nothing implemented yet.**

---

## 1. The idea, one level up

A single open-trades table records *what the bot did*. Prediction-labeled
tables record *what the bot believed* — and grade those beliefs against
reality. That turns paper trading from a rehearsal into a laboratory:

> Every trade is an experiment. Every experiment states its predicted
> outcome and its reasons BEFORE entry. Reality then scores the
> prediction, and the learning loop trains on prediction-error — a far
> richer signal than P&L alone.

The deliberate-LOSS table is the masterstroke of the user's idea: in
science, a theory that can only predict successes is unfalsifiable. An
AI that can *construct* failures on demand — "this trade will lose,
because X" — and be right, demonstrably understands the causal
structure of losing. If its predicted losers don't lose, that error is
exactly as informative as a failed winner.

## 2. The full taxonomy

### 2a. What every open trade must declare (the PredictionRecord)
| Tier | Field |
|---|---|
| ⭐ user's core | predicted outcome: WIN / LOSS |
| ⭐ user's core | direction & legs (CE/PE, buy/sell, entry, stop, target) |
| ⭐ user's core | the REASONS: named, machine-readable factors (indicator values, regime, IV rank, PCR, session time, ban/OI context) with each reason's claimed contribution |
| ✅ sibling | win probability as a calibrated % (not just a label) |
| ✅ sibling | expected P&L / R-multiple if right, expected loss if wrong |
| 🚀 advanced | predicted exit cause: target / stop / time-decay / square-off |
| 🚀 advanced | predicted path bounds: max favorable/adverse excursion |
| 🌌 ultra | full P&L distribution forecast (quantiles), regime-conditional |

### 2b. The tables (experiment arms)
| Tier | Table | Purpose |
|---|---|---|
| ⭐ | **CONFIDENT-WIN** | trades predicted profitable; the deployable-edge candidate pool |
| ⭐ | **CONFIDENT-LOSS** | trades deliberately opened to lose, each with failure reasons; proves causal understanding of losing; must NOT be inverse-of-win coin flips — each targets a specific failure mechanism (bad regime for the strategy, theta against a long option, entering against Supertrend, IV-crush ahead, chasing an exhausted breakout, ban-list-adjacent squeeze risk...) |
| ✅ third table (user invited) | **UNCERTAIN / FRONTIER** | trades where the model's win probability is nearest 50% or its reason-set is novel — active learning: the trades whose outcomes teach the most; graduation source for both other tables |
| 🚀 | **RANDOM-CONTROL** | small arm of coin-flip trades under identical costs — the scientific null baseline; WIN must beat it, LOSS must lose to it, else the "understanding" is an illusion; doubles as the null distribution for the Deflated-Sharpe gate |
| 🚀 | **SHADOW-REJECTED** | virtual (never-executed) tracking of trades the Layer 5 risk gate refused — measures the cost/benefit of the guardrails with evidence; systematically-winning rejections = risk config too tight |
| 🌌 | **ADVERSARIAL** | a second policy searches for trades the WIN-policy would score high-confidence that then fail — self-play attack on the confidence model (GAN-style); every adversarial success becomes a memory of a blind spot |
| 🌌 | **INVERSE-HARVEST** | auto-generated mirrors of well-calibrated LOSS-table trades (where inversion is meaningful — directional trades invert; theta/spread losers often don't) — turns verified failure-knowledge directly into candidate alpha |

### 2c. Scoring machinery (how beliefs get graded)
- ✅ per-table hit rate: % of predictions that came true (WIN table target: high; LOSS table target: high — its trades LOSING means its predictions WON).
- ✅ **Brier score / log loss** on win-probabilities — punishes both wrong and over/under-confident predictions; the single headline calibration number.
- 🚀 **reliability curves** per strategy / regime / underlying bucket ("when the AI says 70%, does it win 70% of the time?").
- 🚀 **reason ledger**: every named reason accumulates its own record — how often trades citing it had correct predictions; reasons rise and fall on evidence, independent of the strategies that cite them.
- 🌌 **interventional experiments**: LOSS-table trades constructed to differ from a WIN-table trade by exactly ONE reason — single-variable causal isolation, the trading equivalent of a controlled experiment.
- 🌌 CRPS (continuous ranked probability score) once distributional forecasts exist.

### 2d. Learning-loop integration (the "links to everything" the user asked for)
- Every closed trade → a **memory node** (Layer 10 temporal knowledge graph): prediction, reasons, outcome, error, regime — queryable "show me situations like this and how my predictions fared."
- Nightly **reflection diff**: which reasons' ledgers improved/decayed — decaying reasons = possible regime shift; surfaced as a reviewable diff per the existing Layer 10 rule.
- **Promotion ladder** (mirrors research/12's external-claim pipeline, now applied to the bot's own ideas): new reason/strategy starts in UNCERTAIN → earns WIN-table (or LOSS-table!) placement only through calibration evidence → Deflated-Sharpe/CPCV gate before any live-capital consideration. Demotion works the same in reverse.
- The **hypothesis-validation pipeline** (research/12) gains a trade-level executor: an external claim ("delivery-% spikes precede up-moves") is tested by BOTH trading it (WIN candidate) and trading its negation (LOSS candidate) — double-sided evidence, faster and stronger than single-sided testing.
- The **council-of-models** (Plan 2) votes per table: disagreement between council members automatically routes a candidate to UNCERTAIN, agreement-to-lose routes to CONFIDENT-LOSS.

## 3. Combinations worth calling out
1. **LOSS × INVERSE-HARVEST** — understanding failure becomes a
   generator of success candidates (with the inversion-validity check).
2. **UNCERTAIN × memory graph** — choose uncertain trades that maximize
   information about the most-load-bearing *unverified* reason in the
   knowledge graph: the bot allocates its experiment budget like a
   scientist allocating lab time.
3. **RANDOM-CONTROL × DSR gate** — the control arm generates the null
   distribution the promotion gate needs; the lab produces its own
   statistical baseline.
4. **SHADOW-REJECTED × Layer 5** — risk parameters stop being static
   config and start being evidence-tuned (loosen/tighten proposals come
   with measured counterfactual cost).

## 4. The three tiers (build order inside Layers 7/10)

**Base tier (Layer 7 paper engine, build first):**
three tables — CONFIDENT-WIN, CONFIDENT-LOSS, UNCERTAIN — plus the
PredictionRecord on every trade (outcome, win-probability, expected R,
reasons, predicted exit cause), outcome verification at close, and a
per-table scoreboard (hit rate + Brier score). All in the trade-log
schema (research/14 extended).

**Advanced tier 🚀 (Layer 7.5, after the base runs for real):**
RANDOM-CONTROL and SHADOW-REJECTED arms; reliability curves per
regime/strategy; the reason ledger; promotion/demotion between tables;
INVERSE-HARVEST generation.

**Ultra tier 🌌 (Layer 10, where it fuses with memory/reflection):**
ADVERSARIAL self-play arm; single-reason interventional trade
construction; memory-graph nodes per closed experiment with nightly
reflection diffs; the research/12 pipeline running double-sided
(claim + negation) trade tests; distributional forecasts + CRPS.

## 5. Guardrails (non-negotiables inherited)
- ALL tables are paper-only constructs. Only CONFIDENT-WIN trades that
  additionally pass the full promotion ladder (calibration + DSR/CPCV +
  human sign-off) can EVER be candidates for the live account. The
  LOSS/RANDOM/ADVERSARIAL arms are permanently barred from live.
- Every table's trades still pass the Layer 5 risk gate with paper
  budgets (deliberate losers are still defined-risk, sized, ban-checked
  — the lab burns virtual money in controlled amounts, never unbounded).
- Predictions are immutable once the trade opens (no retro-editing);
  records append-only, per Rule B's spirit.

## 6. What this changes in the roadmap
- **Layer 7** scope grows: the paper engine is not one portfolio but an
  **experiment allocator** across prediction-labeled tables (base tier
  above), with the PredictionRecord in the trade-log schema from day one.
- **Layer 10** gains its primary training signal: prediction-error
  streams per table/reason, not raw P&L.
- PLAN §9 (new) is the canonical spec; this file is the design rationale.
