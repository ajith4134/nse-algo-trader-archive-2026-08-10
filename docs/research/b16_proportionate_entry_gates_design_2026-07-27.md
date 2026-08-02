# B16 — make the three entry gates PROPORTIONATE (they are over-broad, not wrong)

**Sourcing note (Rule I, explicit):** no OSS pass applies. These are three policy thresholds in this
repo's own gate chain; the evidence for changing them is this system's own realised P&L, measured
today. No external library knows this book. Logged in `docs/BACKLOG.md`.

**Scope note (Rule A):** three gates, one slice — deliberately. Each *independently* blocks index
options, so fixing one still yields zero index trades and would be unverifiable. They are one
coherent defect: **each gate is a blunt binary where a graded response is correct.**

**None of these gates is deleted.** Every one is kept and made proportionate to the risk it is
actually protecting against. A safety gate removed is a safety gate that stops protecting; a safety
gate that blocks everything is one that gets switched off in frustration. Both are failures.

---

## Gate 1 · The opponent-ledger positioning veto — binary, and it killed the profitable side

`participant_positioning/market_positioning_bias.py::institutional_positioning_opposes_entry`
returns a bare `True`/`False`, and callers treat `True` as a hard defer.

**Measured on this book's own closed trades (2026-07-27):**

| direction | n | win rate | realised P&L |
|---|---|---|---|
| long | 82 | **50.0%** | **+10,282** |
| short | 294 | **9.5%** | **−45,033** |

The veto fired on `directional_lean = "bearish"`, which blocks **every bullish entry** — i.e. it
blocked the *only profitable side of the book*, all day, on 145 of 377 decisions. The long book is
roughly breakeven-positive; the entire loss is the forced short book.

**Two distinct defects:**
1. **Binary, not graded.** A confirmation signal is being used as a trigger-strength veto. The
   module's own docstring says participant OI is "a multi-day CONFIRMATION input, never a trigger" —
   a hard block *is* treating it as a trigger.
2. **A category error on relevance.** It is one **market-wide NSE index-futures** reading applied
   unchanged to an individual stock. FII index-futures positioning says something about NIFTY; it
   says very little about a single mid-cap. Its weight should scale with how related the instrument
   is to the index it measures.

**Change:** return a **graded multiplier in [floor, 1.0]**, not a boolean. Full-strength opposition
sizes down (does not block); relevance is scaled by instrument class — index options get the full
weight (the signal is literally about that index), stock options less, individual cash equities
least. A hard defer survives ONLY for the strongest case, and never for an entire direction.

---

## Gate 2 · Scalable oversight — "all options are high-stakes" is the wrong axis

`conscience/scalable_oversight.py::classify_oversight` blocks when
`win_probability < 0.55 AND is_high_stakes`. Every option entry passes `is_high_stakes=True`
unconditionally, while cash always passes `False`.

Combined with the memory recalibration (offsets of −0.37 to −0.65 on the option mechanisms), option
win probabilities sit far below 0.55 — so **essentially every option entry is blocked**, which is
the single most direct cause of "index options = 0". Meanwhile a cash position of *ten times the
rupee risk* passes unexamined.

**The axis is wrong.** Stakes are not an instrument class — they are **how much money is at risk
relative to capital**. A ₹5,000 defined-risk spread is not higher-stakes than a ₹50,000 cash
position; it is an order of magnitude lower.

**Change:** `is_high_stakes` is derived from `risk_amount / account_capital` against a stated
threshold, with defined-risk structures recognised as such. The gate keeps blocking genuinely
high-stakes low-confidence decisions — it stops blocking small defined-risk ones for being options.

---

## Gate 3 · The ADX 20–25 dead band — stand-aside is not the only honest answer

`choose_v1_session_strategy` returns `STAND_ASIDE` for `INDECISIVE`. Measured live today, BANKNIFTY
sat at **ADX 24.96** — inside the band — and 20–72 underlyings per pass were standing aside.

Standing aside when the regime is genuinely unclear is **correct** and is kept. The defect is that
"no clear trend" is treated as "no tradable structure", when it is in fact the textbook condition
for a **defined-risk, non-directional** premium structure. The band currently means "we know
nothing", when it actually means "we know it is not trending".

**Change:** the indecisive band routes to the defined-risk credit spread (the non-directional
structure) rather than to nothing — with the position sized down, because conviction genuinely is
lower there. `STAND_ASIDE` is retained for the cases that warrant it (no ADX at all, unusable data).

---

## Acceptance criteria

1. **No gate is removed.** Each still blocks its genuine case: strongest-divergence positioning,
   genuinely high-stakes low-confidence decisions, unusable/absent regime data.
2. Positioning returns a graded multiplier in `[floor, 1.0]`; it can never *increase* size.
3. Positioning can no longer block an entire direction: with a bearish lean, a bullish entry is
   **sized down, not refused** (except in the retained strongest case).
4. Positioning relevance is instrument-aware: index option ≥ stock option ≥ cash equity.
5. Oversight stakes derive from `risk_amount / capital`, not instrument class. A large cash position
   is now correctly high-stakes; a small defined-risk spread is not.
6. Oversight still blocks high-stakes + low-confidence — verified by a test that must keep failing
   the entry.
7. The ADX indecisive band routes to a defined-risk structure at reduced size; `STAND_ASIDE` remains
   for absent/unusable ADX.
8. Tighten-only invariant preserved everywhere: no path can size a position UP.
9. Every abstain/size-down is counted and surfaced with a reason (Rule O.3).

## Verification plan

- Unit + property tests for 1–8, using the REAL measured values (bearish lean, conviction "normal",
  `fii_net_trend` "confirming", ADX 24.96, the actual win-probability distribution).
- **Rule J (market is CLOSED — 15:30 IST passed):** hermetic sim through the existing feed seam
  asserting an index-option candidate now reaches the order stage where it previously did not.
- ⛔ **Rule F real-data pass is an OPEN BLOCKER** until tomorrow's open: the decisive check is a live
  index-option position opening on a trending index. Logged, not waved through.

## Explicitly NOT in this slice (Rule K)

- **B2's full fix** — a cap on how one-sided the whole book may become. Gate 1 here stops the veto
  blocking a direction; it does not yet cap book skew.
- Re-tuning the recalibration offsets that push option win-probabilities down (B4).
- The B18 ensemble itself — this slice only makes its orders *reachable*.
