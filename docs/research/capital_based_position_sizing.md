# Capital-based position sizing (min/max capital per trade)

**User ask:** stop opening every option trade at 1 lot; size each trade's lots/quantity so its capital-at-risk
follows the dashboard controls — `min_capital_per_trade` (₹40k) ≤ trade capital ≤ `max_capital_per_trade`
(₹100k), also bounded by `max_risk_per_trade_fraction` × account. Applies to every segment.

## Capital-at-risk per trade
For a DEFINED-RISK option structure (condor / debit spread / credit spread — what the bots trade), the
capital at risk is its **max loss**, which the slice-3 payoff optimizer already computes PER LOT and stores in
`proposal.feature_provenance["max_loss"]`. So per-lot capital = that max_loss (for one contract lot).

## Sizing rule (`_capital_sized_lots`)
`effective_max = min(max_capital_per_trade, max_risk_fraction × account_capital)`
`lots = floor(effective_max / per_lot_risk)`, then `lots = max(1, lots)` (1 lot is the minimum tradeable even
if a single lot exceeds the cap — can't trade a fraction). This yields the most lots that stay within the max
capital; because we size UP to the max, the used capital is ≥ min in every realistic case (per_lot ≤ max).
If a name has no `max_loss` (a template / non-synthesized structure), fall back to the allocator's lots
(≥1 floor) — capital sizing needs a risk estimate.

## Where
`PortfolioSupervisor._segment_fair_lots` — replace the flat ≥1-lot floor on option segments with
`_capital_sized_lots`. `run_cycle` gains the sizing config (min/max/risk), threaded from `PodRunner` which
loads `trading_control_config.json`. Cash keeps its own conviction sizing (the cash bot already sizes shares;
a capital cap there is the queued follow-up). No cap on the NUMBER of option trades (user's no-limit rule
stands) — only each trade's SIZE is capital-measured.

## Verification (Rule F)
On the live book: a NIFTY condor with per-lot max_loss ~₹7k under a ₹100k cap → ~14 lots (not 1); a name whose
1 lot already exceeds ₹100k → 1 lot; every trade's `max_loss × lots ≤ effective_max`. Hermetic: known max_loss
+ caps → exact lot count; missing max_loss → allocator fallback.

## Backlog (Rule K)
- Cash-segment capital sizing (shares from entry price × capital) — cash is toggled off today.
- SPAN-style margin (not just defined-risk max-loss) for the live capital-at-risk once live trading is on.
