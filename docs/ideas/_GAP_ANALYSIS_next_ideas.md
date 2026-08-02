# Gap analysis — the seed ideas you're MISSING (2026-08-02)

**Method:** map the 7 captured ideas against the complete 13-layer institutional feature atlas
(`../REDESIGN_feature_atlas_v1.md`). Ideas #1–7 concentrate on the ALPHA/PERCEPTION/BRAIN layers; the
SURVIVAL/DISCIPLINE/PLUMBING layers are un-dissected — and the whole session's evidence says *those*
decide whether the alpha makes money (SEBI: 91–93% lose, costs+absent-risk-rails are why; crypto-bot:
"ops floor is where documented losses occur"; validation is "what killed the prior attempt").

## Coverage map
| Atlas layer | Covered by | Status |
|---|---|---|
| 1 Market data · 2 Signals · 3 Models · 4 Strategies | #1 brain, #2 radar, #3 option-scope, #4 bots, #6 global, #7 tips | ✅ heavy |
| 11 Intelligence (memory/learning/cognition) | #5 catalog, #4 bots | ✅ |
| 6 Options/Greeks-IV | prereq only (in #1/#3) | 🟡 partial |
| **5 Execution** | — | 🔴 **MISSING** |
| **7 Risk management** | prereq mention only | 🔴 **MISSING** |
| **8 Portfolio & capital allocation** | prereq mention only | 🔴 **MISSING** |
| **9 Validation & research integrity** | prereq mention only | 🔴 **MISSING** |
| **10 Operations & infra** | — | 🔴 **MISSING** |
| **12 Governance & compliance (SEBI)** | — | 🔴 **MISSING** |
| **13 Dashboard & observability** | — | 🔴 **MISSING** (user explicitly wanted a clear one) |

## The next 3 seed ideas (highest-leverage missing, evidence-ranked)

### Idea #8 — Validation & promotion-pipeline engine (search integrity) 🥇
**Why it's #1:** it decides whether ANY of ideas #1–7 is real edge or overfit noise. This is *literally
what killed the prior attempt* (nse-crypto-bot-final's Mackey-Glass overfit) and what the 7,846-rule /
Deflated-Sharpe research is about. Every bot, radar signal, tipster source, and engine is a **candidate
that must pass this gate before it touches capital.** Contents: honest **trial registry** (cumulative N
incl. discards) · **holdout custodian** (refuses queries) · **Deflated Sharpe as in-loop fitness** ·
**CPCV** (vendor cpcv.py) · MinBTL · PBO/CSCV · BH-FDR · purged/embargoed CV · **the promotion pipeline**
research→paper→shadow→reduced-live→full-live with regime-coverage + mechanism-declaration gates.

### Idea #9 — Risk + capital-allocation & position-sizing engine (survival + how-much) 🥈
**Why:** SEBI's own data — absent risk rails + over-sizing are why retail loses; "nothing bypasses the
risk gate" (SEC 15c3-5 analog). None of #1–7 IS the risk engine. Contents: **pre-trade risk gate**
(notional/leverage/rate/price-collar/**max-daily-loss**/**drawdown-kill**, exercised in every env) ·
graduated **drawdown ladder** · **watchdog + kill switch** · portfolio **Greeks/VaR + correlation
breaker** (RMT-denoised) · **MWPL/F&O-ban/circuit** guards · **sizing**: vol-target primary + **fractional-
Kelly ceiling** + **discounted-bandit allocation across strategies** + **CVXPY** constrained optimizer.

### Idea #10 — Ops-reliability + execution + governance engine ("where losses actually occur") 🥉
**Why:** crypto-bot's research: documented losses happen in the OPS layer, not the model. + SEBI Feb-2025
algo framework is *mandatory* (Algo-ID, ≤10 orders/s). Contents: **order-intent WAL** · **state
reconciliation from broker truth on restart** · idempotent client-order-IDs · partial-fill tracking ·
**cross-strategy netting** · rate-limit budgeter · cold-start behaviour · disaster-recovery · smart
execution (maker/taker, slippage-abort, signal-expiry) · **SEBI Algo-ID tagging + audit trail + kill
authority** (governance).

## Honorable mentions (also missing — pick if you prefer)
- **Dashboard & observability (L13)** — the "clear dashboard" you named: P&L attribution by cost
  component, per-engine health, promotion state, cockpit verdict, "why did it trade?" timeline.
- **Self-evolution / autonomous research loop (L11-ultra)** — the organism DISCOVERS + improves its own
  strategies (FunSearch/gplearn/OpenEvolve gated by idea #8's hard evaluator; meta-model over the ledger).
  The purest "self-learning organism" — but only safe ON TOP of #8/#9.
- **Bitemporal truth store (L0)** · **cost engine (L1)** · **Greeks/IV engine (L6)** — already named as
  shared prereqs; could each be their own dissection.

## Recommendation
Take **#8 → #9 → #10** as the next three seeds — they convert the alpha/brain you've designed into a
system that can actually *survive and be trusted with money*. Run the standard pipeline (expand→research→
save) on each. #8 first: it's the gate everything else feeds.
