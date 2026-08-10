# 171 — Moneyness-varied directional option arm (ITM/ATM/OTM × CE/PE), validation-gated

**Date:** 2026-08-03 · **Redesign:** L4 family addition · **Skill:** building-engine-grade-features
**Operator ask:** the bot only opens the ATM directional option; wants outright directional buys across the
strike ladder (ITM 24400 CE / 24450 CE …, OTM) AND puts, not just ATM calls.

## Read-first / current behaviour
- `_try_open_directional_option` already buys in the breakout DIRECTION — `want_right = "CE" if LONG else
  "PE"` — so PUTs ARE built (they only fired 0× today because it's a strong UP day → all up-breakouts → CE;
  verified 25/25 opens `long`). The gap is MONEYNESS: line 582 always picks the **ATM** strike
  (`min(abs(strike−spot))`); it never buys ITM or OTM.
- `strategy_engine/option_moneyness_classifier.OptionMoneyness` (ATM/ITM/OTM) already exists — reuse.

## Design
- Pure selector `select_directional_strike(candidates, spot_price, want_right, moneyness, ladder_steps)`:
  ATM = nearest strike; ITM = `ladder_steps` strikes toward the money (CE: strike < spot; PE: strike >
  spot); OTM = `ladder_steps` away (CE: > spot; PE: < spot). Deterministic; guards empty/degenerate.
- Config on the arm `directional_option_moneyness: OptionMoneyness = ATM` (DEFAULT = ATM → the exact
  current `min(...)` behaviour → ZERO regression). Flip to ITM/OTM to trade those strikes.
- Each moneyness is a DISTINCT antibody mechanism + promotion family (`… [index|stock] [ATM|ITM|OTM]`), so
  ITM/OTM/PUT directional each EARN their own edge verdict through L2 — the validation gate keeps a lower-
  edge play (OTM = theta lottery) in PAPER unless it proves out.

## Honest edge note
Outright ITM/OTM directional buys are typically LOWER edge (OTM decays, ITM is capital-heavy). This ships
the CAPABILITY, gated; expect the validation ladder to hold ITM/OTM directional at PAPER unless a real edge
emerges. That is the point of L4 — breadth is allowed, but only validated families reach capital.

## Scope this slice
1. `select_directional_strike` (pure) + tests (ITM/ATM/OTM for CE and PE; ladder-step; degenerate guards).
2. Wire the 1-line swap at 582 via the config (default ATM). Moneyness in the mechanism/family name.
3. **Deferred (opt-in, BACKLOG):** open a LADDER (ATM+ITM+OTM together) per signal — a bigger behaviour +
   risk change, off by default. Real-data pass for PUT side = a down-breakout day (already logged).
