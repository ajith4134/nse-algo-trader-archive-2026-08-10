# Research/53 — 24/7 Market-Open Simulation: the full idea space

**Planning / idea-map (Rule D). No online research yet** — this is the idea space
first; the research pass (data sourcing + techniques) is the agreed next step.
Skill used: `expand-idea`. Companion to the eventual build design.

## 0. The user's idea (verbatim intent)
When the real NSE market closes (e.g. 3rd, after 15:30), switch into a
**simulated-live** mode: rewind the clock to a PAST trading day at 09:15 (e.g. 2nd),
replay it tick-by-tick **as if live**, feeding the bot everything a live session has
— traded prices, order book, order depth, bid vs ask volume, volume profile, etc. —
and keep cycling through past days until the next real open (4th 09:15). Goal: the
AI/learning runs **24/7 like crypto** on realistic replayed microstructure, not just
OHLC bars.

## 1. Is the idea good? — YES, strongly, with three honest caveats
**Why it's right:**
- An intraday bot is idle ~18h/day; 24/7 experience is the single biggest lever on
  learning speed. This is the correct instinct.
- **Microstructure fidelity** (book/depth/flow) — not OHLC — is exactly what the
  weak parts of the project need: fill realism, the opponent-ledger signals, and the
  §9/Layer-10 calibration all improve with real depth.
- It **reuses** what exists: the `MarketClockGatedDataSourceRouter` already flips
  live↔replay; this is that seam, upgraded to high fidelity + always-on.

**Three caveats the advanced tiers must solve (else it backfires):**
1. **Overfitting / memorization.** Replaying the *same* past days over and over
   teaches the bot *those days*, not general skill. → needs curriculum diversity +
   counterfactual perturbation + synthetic days.
2. **Open-loop blindness.** In pure replay the bot's own orders don't move the tape,
   so it never learns **market impact / queue position** — it will over-trust fills.
   → needs a fill+impact model, ideally a reactive market.
3. **Data acquisition is the hard part (Rule I).** Tick + L2/L3 depth history for
   2,000+ NSE symbols is scarce/expensive. Fidelity is gated by what we can source.
   → the research step must map real sources before over-designing.

## 2. The true category
Strip the examples: the core request is a **continuous market-experience GENERATOR
+ training environment** for a learning agent. That category (one level up from
"replay past days") spans: historical replay · order-book reconstruction ·
agent-based/synthetic markets · counterfactual engines · RL environments ·
curriculum/self-play harnesses. The user's examples (book, depth, bid/ask, volume
profile) locate us in **market-data fidelity**; the real prize is the whole
environment around it.

## 3. Full taxonomy (⭐ user-named · ✅ adjacent · 🚀 advanced · 🌌 ultra/frontier)

### A · Data fidelity — what the bot sees
- ⭐ traded prices / OHLC bars · ⭐ order book (L2 ladders) · ⭐ order depth, bid vs
  ask volume · ⭐ volume profile (volume-at-price)
- ✅ full tick / time-&-sales prints · ✅ L2 snapshots (5/20-level) + incremental diffs
- 🚀 **L3 / MBO** (every individual order add/cancel/modify → full book reconstruction)
- 🚀 intraday options surface (per-strike IV/greeks/OI) · 🚀 intraday participant flow
- 🚀 **derived microstructure**: order-flow imbalance (OFI), microprice, queue
  position, trade-sign (Lee-Ready), **VPIN** (flow toxicity), **Kyle's λ** (impact)
- 🌌 synchronized cross-asset tape (index + constituents + futures + options as one clock)

### B · Replay-engine mechanics — how time flows
- ⭐ sequential tick-by-tick of one past day
- ✅ deterministic **event-driven** virtual clock · ✅ **accelerated time** (10×/100×/max —
  a day in minutes → more reps)
- 🚀 **parallel multi-day replay** (many days at once across cores → hundreds of
  sessions per night) · 🚀 **walk-forward / rolling-origin** (train 1..N, test N+1, slide)
- 🚀 **CPCV** resampled paths (feed the existing Deflated-Sharpe/CPCV gate)
- 🌌 always-on scheduler where the sim **chooses the next day/scenario** (curriculum controller)

### C · Closed-loop realism — does the bot affect the market?
- ⭐ open-loop replay (tape ignores the bot) — the user's implicit default
- ✅ **queue-aware fill model** (partial fills, position-in-queue) — upgrades the current slippage model
- 🚀 **market-impact model** (temporary + permanent; square-root law; size moves price)
- 🚀 limit orders sit in the real book and fill as the tape trades through them
- 🌌 **agent-based market (ABM)**: the tape is produced by populations of simulated
  traders (makers, momentum, mean-reversion, noise) that **react** to the bot → true closed loop

### D · Beyond-historical experience — the big multiplier
- ✅ historical replay (given days)
- 🚀 **counterfactual / what-if**: perturb the real day (shift the gap, inject a
  shock, remove a spike, widen spreads) — stress the real tape
- 🚀 **regime-diverse curriculum**: sequence days by regime (trend/chop/high-vol/
  gap/expiry/event) to cover the full distribution — **directly fills the
  single-regime data gap that currently blocks our Layer-10 regime queries**
- 🚀 **synthetic market generation**: Hawkes-process order flow, rough/Heston vol,
  GAN/diffusion "days that never happened"
- 🚀 **adversarial scenarios**: an adversary deforms the tape to maximize bot loss (robustness)
- 🌌 **self-play**: the bot's past strategies become opponents in the ABM (co-evolution)
- 🌌 **world model** (Ha–Schmidhuber / Dreamer): learn a generative market model, then
  **train inside the "dream"** at massive speed

### E · Learning / experimentation harness — what the sim FEEDS
- ⭐ paper trades → §9 lab → Layer-10 memory (exists)
- ✅ **experience-replay buffer** of (state, action, reward, next-state) transitions
- 🚀 **RL environment** (Gymnasium API): state = microstructure features, action =
  order decisions, reward = risk-adjusted PnL
- 🚀 **champion-challenger**: N strategy variants on the SAME tape in parallel → the CPCV/DSR gate
- 🚀 param/hyperparameter search with the sim as fitness function
- 🚀 **automated hypothesis lab**: bot proposes a thesis → sim tests it across many
  days → memory records the verdict (self-directed §9 experiments)
- 🌌 **active-learning curriculum controller**: reads Layer-10 calibration and
  manufactures the scenarios where the bot is **most wrong** ("teach to the weakness")
- 🌌 **continual learning**: guard against catastrophic forgetting as it cycles days

### F · Evaluation & anti-overfitting — the discipline layer
- ✅ purged & embargoed train/val/test day splits (López de Prado)
- 🚀 Deflated Sharpe / **PBO** (probability of backtest overfitting) — extends the DSR gate
- 🚀 **leakage / look-ahead guards** (point-in-time correctness — the replay must never leak the future)
- 🌌 **sim-reality-gap antibody**: continuously compare sim-predicted fills/PnL to
  REAL session outcomes; if they diverge, the sim is wrong → down-weight/auto-correct
  it (mirrors Layer-10's antibody + information-diet trust tracking)

## 4. Combinations (the value is in the fusions)
1. **Curriculum × counterfactual × Layer-10 calibration** → a controller that notices
   the memory has only seen "normal" regime and then selects/synthesizes trending,
   high-vol, gap and expiry days AND perturbs them — *fills the exact multi-regime
   gap blocking our queued regime-transition / co-failure queries.*
2. **L3 book reconstruction × queue-aware fill+impact × RL env** → the bot learns
   *realistic execution* (queue position, its own size moving price) instead of
   assuming perfect fills — turns opponent-ledger + fill realism into something learnable.
3. **Parallel multi-day replay × champion-challenger × CPCV/DSR gate** → overnight,
   hundreds of strategy variants across hundreds of resampled paths; only purged-CV
   survivors get promoted. Disciplined mass experimentation while you sleep.
4. **World model × self-play ABM × accelerated time** → the ultra tier: dream
   thousands of *reactive* synthetic market-days per night, co-evolving vs past selves.
5. **Sim-reality-gap monitor × information diet** → the sim becomes an *information
   source* whose trust is tracked; if its experience stops matching real sessions, its
   influence on learning is down-weighted (the antibody, applied to the simulator itself).

## 5. The three tiers

### BASE — "Faithful replay-as-live" (the user's idea, done well)
After-hours scheduler flips to sim at close, rewinds to a chosen past day 09:15, and
streams the highest-fidelity data we can source (ticks + L2 depth + volume profile)
through the **same live-feed interface** the bot already consumes — so the bot cannot
tell it isn't live. Deterministic virtual clock, optional accelerated time, cycles
recent days until real open. Feeds the existing paper loop + Layer-10 memory.
*Delivers 24/7 learning by itself; reuses the existing router seam.*

### ADVANCED 🚀 — "Curriculum + closed-loop execution + parallel experimentation"
Add: (a) **regime-diverse curriculum** sequencing days across trend/chop/gap/
high-vol/expiry (fixes the single-regime gap); (b) **counterfactual perturbation** to
stress the real tape; (c) a **queue-aware fill + market-impact model** so the bot's
own orders interact with the replayed book; (d) **parallel multi-day replay** so a
night = hundreds of sessions feeding **champion-challenger + the CPCV/DSR gate**. Now
it runs *disciplined experiments at scale*, not just replay.

### ULTRA 🌌 — "Generative reactive world + active curriculum + RL"
(a) an **agent-based / world-model market that REACTS** to the bot (true closed loop,
self-play vs past selves); (b) **synthetic day generation** (Hawkes/rough-vol) — train
on markets that never happened; (c) an **active-learning curriculum controller** that
reads Layer-10 calibration and manufactures the exact scenarios where the bot is most
wrong; (d) the whole thing exposed as an **RL environment** with an experience-replay
buffer; (e) a **sim-reality-gap antibody** that checks sim vs real and down-weights the
sim when it drifts. A self-improving, always-on intelligence that generates its own
curriculum — the crypto-style 24/7 brain, disciplined against overfitting and
reality-gap.

## 6. Which skills are useful here (the user asked)
- **`deep-research`** — the NEXT step: verify (a) where to legitimately source NSE
  tick + L2/L3 depth + intraday options/participant data (Rule I acquisition), and
  (b) the real techniques (order-book reconstruction, impact models, ABM/world-model
  libraries, RL market envs, synthetic-market generators, PBO/CPCV).
- **`sourcing-oss-parts`** — for each buildable piece: replay/event-sim engines,
  Gymnasium market envs (e.g. trading-gym-likes), LOB reconstruction, impact models,
  synthetic-LOB generators — borrow before building.
- **`building-features-from-ideas`** — turn the chosen tier into ordered buildable
  slices (Rule A) once we pick a branch.
- **`dataviz`** — any sim dashboards/panels (replay clock, curriculum coverage,
  sim-vs-real gap) go through it.

## 7. Open questions to decide before research (pick branches)
1. **Fidelity target** — is L2 depth enough, or do we want L3/MBO reconstruction?
   (drives the whole data-sourcing difficulty).
2. **Overfitting stance** — how far up the curriculum/counterfactual/synthetic ladder
   to guarantee generalization vs memorization?
3. **Closed-loop depth** — open-loop replay → fill model → impact → full ABM: where's
   the sweet spot of value vs complexity?
4. **Always-on vs nightly batch** — continuous heavy compute, or scheduled overnight runs?
5. **Learning paradigm** — keep the current §9/Layer-10 supervised-calibration loop,
   or graduate to full RL (bigger, riskier)?
6. **Scope of first slice** — recommend: BASE faithful-replay first (achievable now,
   reuses the router), then climb to ADVANCED curriculum (which also unblocks the
   Layer-10 regime queries).

---

## 8. Claude's own additions (beyond the taxonomy) — ideas tuned to THIS bot

The taxonomy above is the *space*. These eight are my own contributions: they are
not generic replay features — each one plugs directly into machinery this project
ALREADY has (§9 grading, Brier/log-score recalibration, the antibody, the
information-diet ledger, opponent ledger, CPCV/DSR gate). That is what makes them
"hugely benefit our learning" cheaply, without waiting for the hardest data.

### 8.1 ⭐ Prequential replay — turn every idle hour into a graded exam *(highest ROI, cheapest)*
Before each replayed step, force the brain to emit its probabilistic forecast FIRST
(win-prob / direction / expected move), THEN reveal the next tick. Every past day is
already fully labeled by its own future, so replay becomes a **predict-then-see
(prequential) scoring stream**: thousands of graded predictions per night flowing
straight into the EXISTING log/quadratic/Brier scorer and the auto-recalibration
consumer (tasks #25–27). No new data source needed — this works on data we already
have. **This is the single biggest learning-volume win and should be part of BASE.**

### 8.2 🔒 Provenance watermark + trust weight on every experience *(safety-critical, must-have)*
Every experience the bot stores carries a provenance tag —
`live | replay-faithful | counterfactual | synthetic` — with a trust weight. The
antibody and the information-diet ledger (task #30) then treat sim-derived confidence
as a *tracked, down-weightable information source*, and a sim-only lesson can NEVER
override live evidence. This is the firewall that stops 24/7 simulation from silently
corrupting the live brain. **Non-negotiable; belongs in BASE before any sim writes to
Layer-10 memory.** Ties to §3.F sim-reality-gap antibody and combination #5.

### 8.3 🕳️ Structural leakage firewall — point-in-time replay as a causal filter
The replay source must be physically incapable of emitting any datum with
timestamp > virtual-now, and must reconstruct state from raw ticks forward, never from
any file that already "saw" the whole day (volume profile, VWAP, day high/low). Enforce
it in the Rule-J DI seam: the fake/replay adapter is a strict causal gate. Look-ahead
leakage is the #1 reason backtests lie; making it *structurally impossible* (not just
"we were careful") is worth more than any fidelity upgrade.

### 8.4 ⏱️ Surprise-gated time dilation — spend compute where the gradient is
Don't replay at uniform speed. Accelerate through low-information stretches (flat tape,
low OFI/VPIN) at 100×, and slow toward real-time around high-information events (open,
gap, breakout, expiry, volume/toxicity spikes). The learning signal per wall-clock
second is maximized by letting **VPIN/OFI drive the replay clock**. Active learning
applied to the *time axis itself* — a cheap multiplier on §B accelerated time.

### 8.5 🧠 Sleep-consolidation memory — scratch buffer → promote only what generalizes
Model replay as biological "sleep": sim experiences write to a *scratch* buffer, and a
pattern is promoted to long-term Layer-10 memory ONLY if it survives across MANY
diverse replayed days (regime-varied). Directly attacks both overfitting (caveat #1)
and catastrophic forgetting (§3.E continual learning) with one mechanism, and gives the
provenance system (8.2) a natural consolidation gate.

### 8.6 🪞 Temporal self-play — current brain vs its own past decisions on identical tape
On each replayed day, run the bot's REAL historical decisions AND its current-brain
decisions on the SAME tape; the delta is a clean, controlled measure of whether the
brain actually improved (identical history, only the policy differs). Champion–challenger
(§3.E) but against *past self* — feeds the CPCV/DSR promotion gate with an
apples-to-apples signal instead of noisy cross-day comparisons.

### 8.7 🎯 Deficit-driven curriculum — the memory's weakness picks the next lesson
Make the curriculum controller (§3.E ultra) concrete against metrics we ALREADY compute:
the sim selects the next day/scenario by querying Layer-10 for the regime where
**calibration resolution is lowest / the antibody trips most / recalibration offset is
largest**. The bot literally studies where it is most wrong. This is the concrete form
of combination #1 and the thing that unblocks the queued regime-transition/co-failure
work in BACKLOG.md.

### 8.8 📊 Sim-reality gap as a live KPI + auto-throttle
Persist, per replayed prediction, the sim's expected fill/PnL; when the market reopens,
diff against real outcomes and publish a single **sim-reality-gap** metric. If it widens
past a threshold, auto-throttle how much the sim is allowed to influence learning (down
the trust weight of 8.2). The simulator becomes a monitored subsystem, not a black box
we blindly trust. (Concrete wiring of §3.F + combination #5; a dataviz panel later.)

### Where these land in the tiers
- **BASE must include:** 8.1 (prequential), 8.2 (provenance), 8.3 (leakage firewall).
  Without these three, 24/7 replay is at best wasted and at worst harmful.
- **ADVANCED adds:** 8.4 (time dilation), 8.6 (temporal self-play), 8.7 (deficit curriculum).
- **ULTRA adds:** 8.5 (sleep consolidation), 8.8 (auto-throttle gap monitor) as the
  self-regulating layer over synthetic/world-model days.

### My recommended first slice (revises §7.6)
**BASE-minimal = 8.3 + 8.2 + 8.1 on top of the existing router seam**, in that order:
first make replay *causally honest* (8.3), then *provenance-safe* (8.2), then *turn it
into graded learning* (8.1). Faithful high-fidelity depth (L2/L3) is layered in AFTER,
gated by what the research pass proves we can actually source (Rule I) — so we start
delivering 24/7 learning on data we already have, and raise fidelity as data arrives.

---

## 9. User refinement #2 — "never stops · live-indistinguishable · full-universe · point-in-time"

The user sharpened the idea (2026-07-24). Four binding requirements that upgrade the
contract from *"replay historic data"* to *"a never-ending live market built from real
past sessions."* These are now REQUIREMENTS on any tier we build, not options.

### 9.1 It never stops — one continuous market clock, no idle state
There is no "sim mode" that turns on at 15:30 and off at 09:15. There is ONE
**continuous market-experience clock** the bot always reads. When the real NSE is open,
it is fed by the live adapter; the instant real close hits, the SAME clock keeps
advancing — seamlessly handed to a replayed past session rewound to 09:15 — and cycles
past sessions back-to-back until the next real open, where it hands back to live. From
the bot's seat, time simply never stops and the market is *always* open. (Reuses the
`MarketClockGatedDataSourceRouter` seam, upgraded from a gate into a never-idle clock.)

### 9.2 Live-indistinguishable — real session lifecycle, real open & closed trades
It must FEEL live, not like a data file. That means the replayed session carries the
full trade lifecycle: the bot opens positions and closes them *within* the simulated
session, orders fill against the replayed tape/book, and — invariant preserved — every
position is **squared off before the simulated close** (intraday-only holds INSIDE the
sim too; no overnight carry even in a replayed day). Each simulated session has its own
open→manage→square-off arc, exactly like a real day. The bot consumes the identical
live-feed interface and cannot tell it is not live (except via the provenance watermark
§8.2, which only the safety layer sees — never the strategy).

### 9.3 Full-universe, equal coverage — every symbol AND every contract, no sampling
The simulated session must present the WHOLE tradeable universe each replayed day, with
**NSE cash-equity intraday and options (index + single-stock) weighted EQUALLY** — the
bot must be able to pick and trade across all of them, not a NIFTY/RELIANCE sample:
- **Cash:** all ~2,000+ NSE intraday-eligible stocks.
- **Index options:** all 5 index underlyings (NIFTY, BANKNIFTY, FINNIFTY, MIDCPNIFTY,
  NIFTYNXT50) across their strike/expiry ladders (ATM/ITM/OTM).
- **Stock options:** all ~210 single-stock option underlyings across their ladders.
This binds to the project's standing **full-universe rule** (never sample symbols) and
makes replay coverage a hard acceptance criterion: a replayed day that only carries a
handful of liquid names is NOT a faithful session. Data-sourcing (Rule I) must therefore
deliver point-in-time state for the *entire* universe per historical timestamp — a major
driver of the §54 sourcing research.

### 9.4 Point-in-time everything — the news AND the trade data AS THEY WERE THEN
When the clock sits at, say, 2nd 11:07:32, the bot must see exactly what a live trader
saw at that instant and NOTHING from later:
- **Point-in-time trade/microstructure data** — the ticks, book, depth, bid/ask, volume
  profile as of that timestamp (already the §8.3 leakage-firewall guarantee).
- **Point-in-time NEWS & events** — the headlines, corporate announcements, results,
  index/circuit/halt events, and FII/DII/participant context that were *public at that
  timestamp*. The bot reacts to news the way it would have live — and CRUCIALLY, no
  future news ever leaks backward (the firewall now covers the news feed too).
- This adds a NEW acquisition target (Rule I): a **timestamped historical NEWS/events
  feed** aligned to the NSE clock, per symbol — flagged for the §54 sourcing research as
  its own fidelity tier alongside tick/L2/L3/options/participant data. If unobtainable at
  full fidelity, it is recorded as an explicit blocker, never silently dropped.

### 9.5 What this changes for the build
- The BASE seam becomes a **never-idle continuous clock** (not an after-hours toggle).
- **Provenance/firewall (§8.2, §8.3) get MORE important**, not less: the more
  indistinguishable-from-live it feels, the more the safety layer must know precisely
  which experiences were replayed vs truly live, and guarantee no future (price OR news)
  leaks backward.
- **Full-universe coverage** and **point-in-time news** are added as first-class Rule-I
  data-acquisition targets for the research pass (feeds `docs/research/54`).
- Intraday square-off invariant is asserted inside the sim, per session.

---

## 10. User refinement #3 — CORRECTION: replay the ENTIRE NSE history, today → inception

**This corrects a wrong assumption in §9.** The simulation's source is NOT "the
sessions the bot traded live." It is the **complete real NSE historical archive** — the
actual market as it happened on *every* trading day — replayed as-live, whether or not
the bot ever participated that day.

### 10.1 The corrected loop — a systematic backward walk through all of history
Start at **today's session** and walk **backward, one trading day at a time, all the way
to the inception** of each segment we trade:
- **NSE cash equity intraday** — back to its early history.
- **NSE index options** and **single-stock options** — back to when each was first
  introduced on NSE (the user estimates ~2008/2012; the *exact* inception dates and,
  more importantly, the earliest date data is actually LICENSABLE are a research item,
  not asserted from memory — see §10.3).

Each historical day is rewound to 09:15 and replayed as a full live session (open →
manage → square-off, §9.2), at full-universe coverage (§9.3), point-in-time (§9.4).
When the backward walk is exhausted (reaches inception), the design decides the cycle
policy (e.g. jump back to most-recent and walk again, or interleave by regime via the
§8.7 deficit curriculum) — but the DEFAULT intent is: cover *every day from today back
to the beginning*, not loop a handful of recent/traded days.

### 10.2 Why this matters — it's the whole point
Walking the full archive is what gives the bot decades of diverse regimes (2008 GFC,
2013 taper, 2016 demonetisation, 2018 IL&FS, 2020 COVID crash + recovery, 2021 bull,
2022 rate shock, ...). This is the thing that fills the single-regime gap blocking the
Layer-10 regime queries (BACKLOG) — not by synthesising regimes, but by replaying the
REAL ones that actually happened. The §8.7 deficit-driven curriculum then decides WHICH
slice of that history to prioritise, but the corpus is all of it.

### 10.3 What this does to data-sourcing (Rule I) — the honest fidelity ceiling by era
Full-history replay collides with the §54 sourcing reality, and fidelity is NOT uniform
across the timeline — this must be designed around, not glossed:
- **Deep every-trade TICK history IS licensable** from NSE Data & Analytics historical
  dissemination (§54): cash from ~1995, F&O from ~2003, all strikes. So a *tick + derived
  microstructure* replay of the full archive is achievable via that license — this is the
  spine of the whole idea and makes it real.
- **Historical ORDER-BOOK DEPTH (L2/L3) does NOT exist for the past** — no vendor sells
  it and it can only be self-recorded going FORWARD (§54). So deep-history days
  (pre-today) will have **tick + trade prints + derived features, but reconstructed depth
  only where it can be inferred, not true recorded L2/L3.** Depth fidelity therefore
  *improves as the clock approaches today* and as our own forward-recording accumulates.
- **Intraday participant/FII-DII flow is EOD-only, forever** (§54) — so historical days
  carry previous-day/EOD participant context, never intraday.
- **Point-in-time NEWS across 15–20 years** is a NEW, large acquisition target: a
  timestamped historical NSE news/announcements/corporate-actions archive going back to
  inception, aligned to the market clock, leak-guarded (§9.4). Sourcing this deep is its
  own research item and a likely partial blocker for the oldest years.
- **Exact segment inception dates + earliest licensable date per segment** → research
  item (do not assert from memory).

### 10.4 Net effect on the build
- The BASE seam is now a **historical-archive replay driver** that walks today→inception
  over the licensed tick archive, wrapped in the never-idle continuous clock (§9.1) and
  the live-indistinguishable session lifecycle (§9.2).
- **Fidelity is era-dependent and must be tagged** (extends the provenance watermark
  §8.2: each experience records not just live-vs-replay but its *fidelity tier* — full
  live depth / recorded depth / tick-only-derived / news-missing — so the safety layer
  and calibration weight older, thinner days appropriately).
- Data acquisition is now explicitly two-track: **(a) license the NSE deep tick archive**
  for the backward history, and **(b) record our own full-depth feed forward** from today
  — the two meet at "today" and fidelity is highest there.
- New research/blocker items: NSE historical-tick license scope+cost+earliest dates;
  deep historical news archive; per-segment inception dates. (To BACKLOG on build start.)

---

## 11. Claude's additions to the full-history idea (before research) — the silent corruptors

Four things that, if missed, would silently corrupt decades of replayed learning while
LOOKING correct. #11.1 is the classic backtest killer and is non-negotiable.

### 11.1 🚨 Point-in-time universe — survivorship-bias-free (CRITICAL)
When the clock is at 2009, the tradeable universe must be **the universe as it existed in
2009**, not today's list projected backward:
- **Only stocks/contracts listed & tradeable on that date** (include the ones later
  DELISTED — Yes Bank pre-crisis, DHFL, delisted PSUs, etc.). Using today's survivors on
  2009 data = survivorship bias = the bot learns the market was safer than it was.
- **The F&O-eligible list AS OF that date** — the ~210 stock-option underlyings changed
  every review; many names in/out over the years. Replaying today's F&O list on 2015 is
  wrong both ways (contracts that didn't exist / missing ones that did).
- **Index constituents AS OF that date** — NIFTY/BANKNIFTY membership changed constantly;
  the index itself must be reconstructed from the *then-current* basket, not today's.
- Requires: historical listing/delisting master, historical F&O-eligibility snapshots,
  historical index-constituent history. → research/54 acquisition items.

### 11.2 🔀 Corporate-action & adjustment engine (point-in-time)
Splits, bonuses, dividends, rights, symbol renames, mergers across 15–20 years. The bot
must see **unadjusted point-in-time prices** (what actually printed that day), while the
engine keeps **continuity correct across the action** (a 1:5 split isn't an 80% crash).
Wrong handling injects thousands of fake gaps/shocks into the learning stream. Requires a
historical corporate-actions master aligned to the tick archive.

### 11.3 📜 Point-in-time MARKET RULES, not just prices (per-era microstructure params)
The rules of the game changed over the timeline; the sim must apply the rules **in force
on the replayed date**, not today's:
- **Expiry cycles** (monthly-only early on → weekly expiries introduced later; different
  weekdays per index over time), **lot sizes** (revised repeatedly), **tick size**,
  **circuit/price bands & market-wide halts**, **STT/stamp/exchange charge schedules**
  (changed many times), **session hours & pre-open** (pre-open auction added 2010),
  **settlement/margin regime** (peak-margin, SPAN changes).
- Getting these wrong makes fills, expiry payoffs, and PnL systematically fake for whole
  eras. → a **point-in-time market-rules calendar** is a new data/design item.

### 11.4 📅 Point-in-time trading calendar (holidays/special sessions per year)
Historical NSE holiday lists, muhurat sessions, ad-hoc closures/extensions per year — the
backward walk must step over the ACTUAL trading days of each year, not a modern calendar.

### 11.5 ⏩ Two-phase cadence — accelerated bootstrap, then near-real-time "feels-live"
First full pass through the 15–20-year archive runs **accelerated** (surprise-gated time
dilation §8.4) to bootstrap the brain fast across all regimes; once caught up, the
always-on loop runs **nearer real-time** so it keeps the live-indistinguishable feel
(§9.2) rather than blurring past everything. Bootstrap for coverage, then cruise for feel.

### Net: two new acceptance criteria + research items
- **Acceptance:** a replayed historical day is only "faithful" if it uses that date's
  universe (11.1), adjusted correctly (11.2), under that date's rules (11.3) and calendar
  (11.4). Add these to the §9.3 full-universe acceptance test.
- **Research/54 additions (Rule I):** historical listing/delisting master · historical
  F&O-eligibility snapshots · historical index-constituent history · corporate-actions
  master · point-in-time market-rules & charges history · historical trading-calendar.
  (All → BACKLOG on build start; likely partial blockers for the oldest years.)

