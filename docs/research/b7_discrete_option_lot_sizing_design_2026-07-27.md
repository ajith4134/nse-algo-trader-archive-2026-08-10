# B7 — Discrete option-lot sizing: design (2026-07-27)

Fixes the defect diagnosed in `live_session_diagnosis_2026-07-27.md` §7a: **every option order is
truncated to zero lots**, so the bot has never opened a single index-option position.

**Sourcing note (Rule I / sourcing gate, explicit not silent):** no OSS sourcing pass applies here.
This is a defect in this repo's own sizing arithmetic — the correct behaviour is fully determined by
the existing `RiskGateConfig`/`RiskGateDecision` contracts and NSE lot indivisibility. There is no
external library that decides "how many lots may I trade given my own risk gate"; importing one
would be strictly worse than using the risk gate already present. Logged in `docs/BACKLOG.md`.

---

## 1 · The defect, precisely

Both option entry sites (`option_credit_spread_live_path.py:206,226-233` credit spread and
`:344-350` directional) do this:

```python
lots = 1                                   # <-- hard-coded, discards decision.approved_quantity
lots = int(lots * m_debate * m_index_level * m_vitality)   # truncation #1
lots = state.apply_workspace_caution(lots)                 # truncation #2: int(size * 0.90)
if lots <= 0: return False
```

Three compounding errors:

1. **The risk-sized quantity is discarded.** `evaluate_credit_spread_signal` already computes
   `affordable_lots` from the real risk budget (`pre_trade_risk_gate.py:117-119`), then throws it away
   via `approved_lots = min(affordable_lots, signal_lots)` (`:126`) where `signal_lots` is the leg
   selector's **template default of 1** (`credit_spread_leg_selector.py:33 lots: int = 1`). A template
   default is not a risk decision, so capping affordability by it is wrong. The entry site then ignores
   `decision.approved_quantity` entirely and re-hard-codes 1.
2. **Multipliers are truncated stepwise instead of composed.** `int()` is applied twice — once inside
   the entry site, once inside `apply_workspace_caution` (`live_universe_paper_loop.py:583`). Two
   floors on a base of 1 guarantee 0.
3. **Floor instead of round.** `int(1 × 0.90) = 0`. A lever saying "trim 10%" becomes "never trade".
   Cash is unaffected only because its quantity is in the hundreds.

Measured live: composed multiplier ≈ **0.225** (`m_debate` 1.0 · `m_index_level` 1.0 ·
`m_vitality` 0.25 · workspace 0.90). With base 1 → `int(0.225) = 0`, always.

## 2 · Correct semantics

Option lots are **indivisible**. Three outcomes must be distinguishable, and all three must be counted:

| composed multiplier `f` | meaning | correct result |
|---|---|---|
| `f == 0.0` | a lever explicitly vetoes (critical safety, dead VITAL organ) | **0 lots — stand aside** |
| `f > 0`, `round(base × f) >= 1` | trim to a smaller but tradable position | **`round(base × f)` lots** |
| `f > 0`, `round(base × f) == 0` | intended exposure is under half the minimum tradable unit | **0 lots — stand aside, counted** |

Round-**half-up** is the right rounding: it picks the nearest achievable position to the intended
exposure. `round(0.9) = 1` (trim 10% of one lot → still trade one lot, the smallest expression of a
reduced position). `round(0.25) = 0` (a quarter-lot is not tradable → stand aside honestly).

Critically, this only works once the **base** is the risk-affordable lot count rather than 1. With the
real budget (`account_capital` ₹10 cr, `max_margin_per_position_fraction` = 100,000×0.25/1e8 =
0.00025 → margin budget ₹25,000) a typical NIFTY spread affords ~6 lots. Then `round(6 × 0.225) = 1`
— **the trade happens**, correctly sized down. With base 1 it never can.

## 3 · The change

**New module** `src/nse_algo_trader/risk_management/discrete_lot_size_down_policy.py` — the single
place discrete-lot size-down is decided, so both option entry sites and any future one share it:

- `compose_size_down_multipliers(*multipliers) -> float` — product, each clamped to `[0, 1]` first so
  the policy is **tighten-only by construction** (no configuration can up-size), NaN/inf treated as a
  veto rather than silently as 1.0.
- `size_down_discrete_lots(base_lots, composed_multiplier, minimum_tradable_lots=1)
   -> DiscreteLotSizeDownDecision` with fields `granted_lots`, `intended_lots`,
  `composed_multiplier`, `stood_aside_reason`. A stand-aside always carries a human-readable reason —
  never a bare 0 (Rule O.3: no silent failure).

**Entry sites** (`option_credit_spread_live_path.py`, both):
- base becomes `decision.approved_quantity` (risk-sized) instead of `1`;
- the four multipliers are composed once and applied once via the policy;
- `apply_workspace_caution` is no longer called on the lot count — its multiplier is folded into the
  composition, and its existing trim/defer counters are incremented through a new
  `workspace_caution_multiplier_for_composition()` accessor so the Trunk-VIII tally stays truthful.

**Risk gate** (`pre_trade_risk_gate.py:126`): `approved_lots = affordable_lots`. The leg selector's
`lots` template no longer caps affordability. Single production caller, so this is safe; tests updated.

## 4 · What this does NOT fix (Rule K — tracked, not silently skipped)

- **B8** — options are still seeded once per process with no retry, so even with correct sizing the
  only opportunity is the first ~7 minutes after the open. B7 alone will produce few trades until B8
  lands. Already in `docs/BACKLOG.md`.
- **B3 (option half)** — the min/max capital-per-trade clamp is still not applied to option lots at
  all. B7 deliberately does not add it; it belongs with the B3 fix that moves the clamp to the last
  step at all four entry sites. Already in `docs/BACKLOG.md`.
- **B9** — stock options remain absent from the ladder outside monthly-expiry week.
- Whether `homeostat_permits_order()` is separately vetoing all orders is **UNRESOLVED** — the gate's
  telemetry observes live process state and cannot be measured from outside the running process. If it
  is vetoing, B7 will correctly size the order and the homeostat will still refuse it. This is the
  explicit real-data question B7's verification answers.

## 5 · Verification plan

- **Unit (hermetic, Rule J):** the policy's boundaries — `f=0` vetoes; `round(0.9×1)=1`;
  `round(0.25×1)=0` with a reason; composition is tighten-only; NaN/inf vetoes; base 6 × 0.225 → 1.
- **Rule F real-data:** the market is open. After deploying, watch `/api/snapshot` for
  `segment_boards[index_option].open_count > 0` and a non-empty option funnel. If lots are now
  correctly sized but orders are still refused, the refusal reason identifies the next blocker
  (homeostat / oversight), which is itself the answer to §4's open question.
- **Deployment risk (must be surfaced before restarting):** open positions are **not persisted
  anywhere** (`grep` for restore/persist returns nothing) and `stop()` (`live_paper_trading_service
  .py:918`) only flips a flag — it does not square off. Restarting mid-session **drops all currently
  open paper positions without recording them as closed experiments**. This is an operator decision,
  not mine to take.
