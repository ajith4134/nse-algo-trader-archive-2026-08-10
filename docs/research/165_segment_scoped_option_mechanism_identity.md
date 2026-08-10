# 165 — Segment-scoped option mechanism identity (unblock index options for a fair antibody trial)

**Date:** 2026-08-03 · **Type:** root-cause fix (systematic-debugging) · **Closes:** B34 index-option blocker

## Root cause (proven on live data, 2026-08-03)
Index options approve at the risk gate but never open because the **antibody**
(`entry_decision_for_mechanism` → `vetoed_mechanisms`) vetoes their mechanisms for a statistically-proven
**no-edge / overconfident** record: `defined-risk credit spread…` n=95 (calibration-tripped),
`long ATM option…ORB breakout` n=156 (`resolution≈0`). minimum_samples=12 → NOT a thin-data artifact. The
prior B34 suspect (`index_level_size_multiplier` flooring) is REFUTED. Shadow-probe relief valve works
(55 probes / 404 vetoes ≈ 1/8).

## The real defect: segment-agnostic mechanism identity
`option_prediction_records.py:74,106` set the option `mechanism_name` to a FIXED string, identical for
index AND stock options. So the antibody track record conflates 5 liquid index underlyings with 208 stock
underlyings (+ replay). Index options — tighter spreads, different vol regime, different microstructure —
are vetoed largely on **non-index** evidence and have never had an independent fair trial. This violates
the spirit of Rule Q (don't refuse a mechanism on evidence not specific to it) and the operator's intent
("index and stock options can be traded for profit in any day/regime with the right setup").

## Fix (operator chose Option 1)
Scope the option `mechanism_name` by segment — append `[index]` / `[stock]` derived from
`instrument.kind` (INDEX_OPTION / STOCK_OPTION). This yields FOUR independent option mechanism identities
(index/stock × directional/credit), each accruing its OWN antibody calibration. Consequences:
- The old combined-name history is orphaned; index AND stock options each start a FRESH trial and fire
  freely until each reaches minimum_samples (12) and earns its own verdict.
- Downside risk (re-trading a possibly-no-edge mechanism during the fresh trial) is BOUNDED by the risk
  gate + the new L1 pre-trade cost gate (both already in the path) + paper capital. This is the fair-trial
  the operator wants, not a bypass of the antibody — each segment can still earn a veto on its OWN record.
- The real profitability path (an edge-bearing option setup) remains B35 / redesign L4; this fix only
  gives each segment an honest, independent chance to prove or disprove edge.

## Blast radius / safety
The two mechanism strings are referenced ONLY in `option_prediction_records.py` (grep-verified) — no test,
mapping, or dashboard hardcodes them; the antibody matches whatever name the record carries, so the change
is self-contained.

## Sourcing (Rule O.1)
No OSS search applies — this is an internal change to the antibody's mechanism-identity string (no
algorithm, parser, or external component to source). The reused machinery (antibody / reliability
decomposition / recalibration) is already in-repo (`memory_reflection/`). Logged, not silently skipped.

## Verification
- Unit: the two builders emit segment-suffixed names for an index vs stock instrument.
- Rule F (live): index options begin opening on the live feed after deploy (fresh per-segment trial),
  bounded by risk + cost gates; confirm on the dashboard's option boards + segment tables.
