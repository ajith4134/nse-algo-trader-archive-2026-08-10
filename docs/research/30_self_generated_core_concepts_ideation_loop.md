# 30 — Self-Generated Core Concepts: the Ideation Loop

**Origin:** user request (2026-07-23): after their falsification-lab
concept (research/29), generate MY OWN genuinely novel core concepts at
full capability, critique them honestly, then iterate generate→critique
in a loop. This file records the loop verbatim — including the ideas I
killed and why — because the rejects teach as much as the survivors.

**Status: ideation adopted into PLAN §10 (shortlist only). Nothing
implemented.**

---

## ROUND 1 — broad generation (ten concepts)

**R1.1 Mechanism-Verified Wins ("right for the right reason").**
The PredictionRecord (§9) says WHAT will happen; this adds HOW. Every
prediction names its mechanism ("win via post-breakout momentum
continuation"), and at close the bot grades the *path*, not just the
P&L sign: did price actually trend after entry, or chop sideways and
gap into profit? A win whose predicted mechanism never manifested is
relabeled **lucky-win** and treated as a miss for calibration purposes.
Kills the biggest silent poison in self-learning traders: reinforcing
accidents.

**R1.2 Whose-Money Opponent Ledger.** No trade opens without naming the
counterparty thesis: who is on the other side, and why are they wrong?
("retail chasing the third gap-up in a row", "option writers defending
max-pain", "forced hedging flow"). NSE publishes participant-wise
derivatives positions daily (FII / DII / Pro / Client long-short) — so
counterparty hypotheses are *checkable against real flow data*, not
vibes. If you can't name the loser at the table, you're the loser.

**R1.3 Loss Epidemiology (structured trade autopsies).** Every losing
trade gets a death certificate from a fixed cause-of-death taxonomy:
bad thesis / right thesis, wrong timing / right trade, wrong size /
slippage-killed / regime flip mid-trade / execution defect / black
swan. Epidemiology over certificates ("what killed us this month, and
is it one disease or five?") turns diffuse losing streaks into
diagnosable outbreaks with targeted fixes.

**R1.4 Ghost Portfolio Family (decision-dimension counterfactuals).**
Beyond §9's shadow-rejected arm: a family of always-on counterfactual
selves, each differing from the real bot along exactly ONE decision
dimension — the self that always inverts the regime call, the self at
2x size, the self with no stops, the self that enters 15 minutes later.
Performance gaps between the real self and each ghost attribute P&L to
individual decision dimensions, continuously.

**R1.5 World-Model Scoreboard (perception vs action split).** The bot
makes trade-independent market forecasts on a fixed cadence (next-hour
realized vol, session range, breadth direction, expiry pin distance) and
scores them like a weather station — separately from trading. When
performance degrades, this isolates WHERE it broke: does the bot
misread the world (perception error) or read it right and trade it
badly (action error)? Two different diseases, two different medicines.

**R1.6 Profit Provenance (P&L decomposed like an audit).** Every rupee
of realized P&L decomposed against the §9 control arms: edge vs luck vs
costs vs regime tailwind vs timing. "We made ₹12,400: ₹9,100 is
explained by the vol regime any random entry enjoyed, ₹4,800 by entry
timing, -₹1,500 costs" — the bot always knows where its money actually
comes from, so it notices when the source dries up BEFORE the total
does.

**R1.7 Trading Immune System.** Disasters distill into *antibodies*:
tiny, cheap, always-on pattern-matchers (much simpler than strategies)
that veto trades matching a past catastrophe's signature. Antibodies
strengthen on re-exposure, decay if never triggered, and are audited so
scar tissue doesn't strangle the system. Memory (Layer 10) is slow and
rich; immunity is fast and dumb — both are needed.

**R1.8 Per-Trade Pre-Mortem (individual Monte Carlo at entry).** Before
any WIN-table trade opens, replay THIS specific setup through dozens of
regime-matched historical paths from the replay store → an outcome
distribution for this exact trade. The trade must survive its own
pre-mortem (e.g. P5 loss within budget, win-rate consistent with the
claimed probability). Every trade is backtested individually, at entry
time, not just its strategy class in aggregate.

**R1.9 Internal Prediction Market (council votes with skin in the
game).** The council-of-models (Plan 2) stops voting democratically:
members bet virtual bankrolls on each prediction in an internal betting
market; market-clearing odds become the ensemble confidence; chronically
wrong members go bankrupt and lose their voice until they re-earn it on
UNCERTAIN-table calls. Confidence weighting with consequences, not
averaging.

**R1.10 The Referee (continuous decision-reproduction audits).** An
independent process re-derives yesterday's decisions from logged inputs
with the documented logic and flags every divergence between what the
code *should have decided* and what it *actually did* — catching silent
bugs, config drift, and doc-vs-code divergence. The lab is only
trustworthy if its instruments are calibrated; this audits the
instruments.

---

## ROUND 1 CRITIQUE — my honest opinion of my own ideas

**Keepers, ranked:**
1. **R1.1 Mechanism-Verified Wins** — the single best one; it deepens
   the user's own falsification concept at its weakest point (outcome
   grading alone can't tell skill from luck) and costs little: path
   statistics + a mechanism taxonomy. Adopt into §9 directly.
2. **R1.3 Loss Epidemiology** — cheap, immediately actionable, and the
   perfect data producer for R1.7's antibodies and Layer 10 reflection.
3. **R1.5 World-Model Scoreboard** — architecturally deep; the
   perception/action split is diagnostic gold and trivially scoreable.
4. **R1.2 Opponent Ledger** — the most *tradeable* new information
   source (participant-wise OI is real, daily, and unused in our
   plan!). Slight risk of narrative-invention; must stay tied to the
   flow data.
5. **R1.6 Profit Provenance** — strong, but depends on the §9 control
   arms existing first; sequence it after them.
6. **R1.8 Pre-Mortem** — high value per trade, moderate compute; needs
   the replay store, so it's naturally Layer 7.5.
7. **R1.10 Referee** — unglamorous, highest safety value per line of
   code; should exist from Layer 7 day one.

**Killed, and why:**
- **R1.4 Ghost Family** — seductive but explodes combinatorially (every
  dimension × every day × full universe); §9's shadow arm + R1.6's
  decomposition capture 80% of it for 20% of the cost. Revisit only if
  a specific attribution question demands it.
- **R1.9 Prediction Market** — the bankroll mechanism is real (it's
  online learning with multiplicative weights wearing a costume), but
  as a *feature* it's premature until there IS a council of models
  (Layer 10). Parked, not killed — re-evaluate at Layer 10.
- **R1.7 Immune System** — kept conceptually but demoted: v1 is just
  "auto-generated veto rules distilled from death certificates," which
  is R1.3's output plus a rule engine. The biology metaphor is nicer
  than the mechanism is novel. Folded into R1.3's roadmap.

**What the critique reveals (fuel for round 2):** the survivors share
one shape — they all make an *implicit* quantity *explicit and scored*
(mechanism, cause of death, world-belief, counterparty, provenance).
The frontier question is therefore: what ELSE does the bot implicitly
rely on that is never stated or scored?

---

## ROUND 2 — generation from the critique's insight

**R2.1 Assumption Registry (the bot's constitution, continuously
audited).** Every strategy/feature declares the assumptions it silently
rests on ("VWAP mean-reversion assumes no trending regime", "spread
margins assume exchange spread benefit", "replay realism assumes
low impact of my own size"). Each assumption gets a monitor — a cheap
statistical tripwire that fires when reality stops satisfying it. When
an assumption breaks, everything downstream of it is flagged, sized
down, or paused — BEFORE the P&L shows it. This is R1.5 generalized
from market beliefs to *all* beliefs.

**R2.2 Skill-vs-Luck Court (mechanism verification + provenance
unified).** R1.1 and R1.6 merge into one verdict pipeline: every closed
trade is tried — outcome, mechanism-manifestation, provenance
decomposition — and receives one of four verdicts: SKILL-WIN,
LUCKY-WIN, UNLUCKY-LOSS, DESERVED-LOSS. The learning loop then trains
ONLY on the diagonal (skill-wins reinforced, deserved-losses corrected)
and quarantines the off-diagonal (lucky wins never reinforced; unlucky
losses never over-corrected). This single change fixes the deepest flaw
in naive P&L-driven learning.

**R2.3 Information Diet Accounting.** Every input stream (each
indicator, each NSE report, each flow series) carries a running measure
of how much it actually changed decisions and whether those changes
helped (marginal value of information). Streams that never move the
needle get demoted from the hot path; streams whose removal degrades
paper performance get redundancy. The bot knows what it's *worth
knowing* — and research effort (Layer 11) gets pointed at the
highest-value information gaps.

**R2.4 Expiry-Day Species Problem → Calendar-Conditioned Everything.**
Not one bot that trades every day, but explicit calendar conditioning:
expiry days, event days (RBI/Fed/results), first/last session of
series, ban-heavy days are *different games with different physics*.
Every table, ledger, and calibration curve in §9 gets partitioned by
calendar-context, and strategies must qualify PER CONTEXT (a strategy
can be WIN-table on normal days and barred on expiry days). Cheap to
implement (it's a partition key), large error-prevention value on NSE
specifically, where expiry mechanics dominate certain sessions.

**R2.5 Position-Level Kill Criteria (pre-committed falsification per
open trade).** Beyond stop-losses: every open trade carries the
pre-stated evidence that would prove its thesis dead ("if price
re-enters the range for 3 bars, the breakout thesis is falsified —
exit regardless of P&L"). Exits become thesis-driven, not only
price-driven; and "thesis died but stop not hit" stops bleeding money
in slow-motion losers. The PredictionRecord gains a `kill_criteria`
field, and the Referee audits that kills actually execute.

---

## ROUND 2 CRITIQUE

- **R2.2 Skill-vs-Luck Court: adopt, top priority.** It is the payoff
  matrix of the entire §9 lab; without it the lab still trains on
  contaminated labels. Verdicts are computable from data the lab
  already collects.
- **R2.1 Assumption Registry: adopt.** Highest ceiling of all — it
  extends falsification from trades to the SYSTEM ITSELF. Start tiny
  (each strategy ships with 2-3 declared assumptions + monitors).
- **R2.5 Kill Criteria: adopt immediately** — smallest of all to build
  (one field + exit hook), classic professional practice, strengthens
  §9's immutable predictions.
- **R2.4 Calendar Conditioning: adopt as a partition key from day one**
  (cheap now, painful to retrofit); full per-context qualification can
  mature later.
- **R2.3 Information Diet: adopt at Layer 10**, where decision logs
  exist to compute marginal value; premature before that. Parked with a
  build trigger, not killed.

---

## ROUND 3 — synthesis: the Self-Auditing Scientific Institution

The loop converged on a unifying frame. The bot is not "a strategy with
AI features" — it is an **institution of adversarial departments**, each
keeping the others honest:

| Department | Concept | Keeps honest |
|---|---|---|
| Laboratory | §9 prediction-labeled tables (user's) | strategies' claims |
| Pathology | Loss Epidemiology (R1.3) + antibodies | the lab's failures |
| Court | Skill-vs-Luck verdicts (R2.2) | the learning signal |
| Weather station | World-Model Scoreboard (R1.5) | perception vs action |
| Intelligence desk | Opponent Ledger (R1.2) | the "who loses?" question |
| Constitution office | Assumption Registry (R2.1) | the system's foundations |
| Audit office | The Referee (R1.10) | the code itself |
| Treasury | Profit Provenance (R1.6) | where money comes from |

One department alone is a feature; the institution is a bot that cannot
easily fool itself — which is the real failure mode of every
self-learning trader.

## ADOPTED SHORTLIST (into PLAN §10)
Build-order mapped:
- **With Layer 7 base:** Kill Criteria (R2.5) · calendar partition key
  (R2.4) · Referee v0 (R1.10) · mechanism field groundwork (R1.1).
- **Layer 7.5 (after control arms):** Skill-vs-Luck Court (R2.2) ·
  Loss Epidemiology (R1.3) · World-Model Scoreboard (R1.5) ·
  Pre-Mortem (R1.8) · Profit Provenance (R1.6).
- **Layer 10:** Assumption Registry (R2.1) · Opponent Ledger (R1.2,
  needs participant-wise OI ingestion added to Layer 2's report set) ·
  Information Diet (R2.3) · antibodies automation · prediction-market
  council weighting (parked R1.9).

**Parked/killed register:** Ghost Family (cost), Prediction Market
(until council exists), Immune-System-as-metaphor (folded into
epidemiology), plus rejected during generation: attention-economics
budgeting (vague), data-deception detection (thin at retail scale),
self-impact mirror test (irrelevant at this size), synthetic nightmare
generator (already in Plan 3 as stress rehearsal).
