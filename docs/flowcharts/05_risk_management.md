# 05 — Risk Management (Layer 5)

**Status:** v1 built, unit + adversarial tested, universe-wide sweep
verified. Awaiting user sign-off before Layer 6.

## Whole-pipeline data flow so far

```
[L1 Universe] -> [L2 Market Data] -> [L3 Indicators] -> [L4 Signals]
                                                            |
                                                            v
[Layer 5: risk_management/]  every signal passes the gate or dies
   option_combination_risk_profile
     assess_option_combination_risk(legs) -> OptionCombinationRiskProfile
       (category DEFINED/UNDEFINED, worst_case_structural_loss —
        None == unlimited, has_unlimited_upside_loss,
        has_unpaired_short_leg)
   margin_requirement_estimator            risk_based_position_sizer
     estimate_defined_risk_spread_margin     size_cash_position_by_stop_distance
     estimate_intraday_cash_margin           size_defined_risk_spread_lots
                     \                          /
                      v                        v
   pre_trade_risk_gate
     evaluate_opening_range_breakout_signal(signal, RiskBudgetConfig)
     evaluate_credit_spread_signal(signal, banned_underlyings, budget)
     -> RiskGateDecision(approved, rejection_reasons(tuple of
        RiskRejectionReason), approved_quantity, estimated_margin,
        estimated_worst_case_loss)
        |
        v
   (approved decisions await Layer 6 OMS; rejections carry
    machine-readable reasons for Layer 9 dashboards / Layer 10 memory)
```

## Files belonging to this layer

```
src/nse_algo_trader/risk_management/
├── __init__.py                          # public surface re-exports
├── option_combination_risk_profile.py   # payoff-structure risk analysis
├── margin_requirement_estimator.py      # conservative upper-bound margins
├── risk_based_position_sizer.py         # fixed-fractional sizing
└── pre_trade_risk_gate.py               # the gate + decision/reason types

tests/test_risk_management/              # 27 tests incl. adversarial pass
├── test_option_combination_risk_profile.py
└── test_sizing_margin_and_risk_gate.py
```

## v1 policy (deliberate choices)
- **Defined-risk only**: net short calls (unlimited) AND any unpaired
  short leg — grouped per (right, expiry) in SHARES not lots, so
  mismatched lot sizes can't hide net-short exposure — are rejected.
  Naked short puts are structurally finite but still rejected (unpaired).
- **Structural max loss ignores premiums** — conservative by design;
  payoff evaluated at 0, every strike, and 2x max strike (piecewise
  linearity makes those the only candidates), slope beyond checked for
  unlimited exposure.
- **Margins over-stated on purpose** until Layer 6 wires the broker
  margin API: spreads = structural max loss +10%; intraday cash = 25%
  of notional (stricter than SEBI's 20% peak-margin floor). No naked
  margin estimator exists — pricing what v1 forbids invites its use.
- **Fixed-fractional sizing**: 1% risk/trade, 25% margin/position caps
  (RiskBudgetConfig); unaffordable-at-1-unit -> rejected, never rounded
  up. MWPL ban list (L2 data) blocks fresh F&O positions per underlying.

## How it was verified (2026-07-23)
- 27 tests (132 suite, green), including the PLAN §5 adversarial pass:
  naked call/put, short strangle, 2:1 ratio spread, hedge-on-wrong-
  expiry, hedge-on-wrong-right, and lot-size-mismatch (150 vs 75) all
  detected; iron condor/bull put/long straddle correctly DEFINED with
  hand-checked max losses; sizing arithmetic hand-verified.
- **Universe-wide sweep (real data, full pipeline L3->L4->L5)**: all 215
  option underlyings, real live lot sizes + the real 2026-07-23 ban
  list: KAYNES rejected (ban list), 47 approved with sensible margins
  (NIFTY 1 lot, max loss Rs.6,500 — live lot size 65, not the assumed
  75; the sweep caught that), 167 correctly rejected as unaffordable
  within the 1%-of-Rs.10L risk budget (e.g. YESBANK's ~31k-share lots).
  Zero errors, zero symbol-specific code.

## Known limitations / explicitly deferred
- Real SPAN+exposure margins via broker margin API — Layer 6.
- Portfolio-level limits (max concurrent positions, daily loss cap,
  correlation/sector exposure) need a positions ledger — arrives with
  Layer 6/7's paper engine; gate is per-signal until then.
- Premium-aware max loss (width - credit) — needs live quotes at
  execution time (Layer 6); structural loss is the conservative bound.
