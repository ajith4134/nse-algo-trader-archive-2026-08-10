# B23 — profit-trail gating + excursion (MFE/MAE) tracking: design

**Sourcing note (Rule I / sourcing gate, explicit not silent):** no `sourcing-oss-parts` pass run yet.
Trailing-stop and excursion arithmetic is a handful of comparisons over this repo's own position
objects — there is no external component that knows this project's three position types or its
sign conventions. **If** the ATR arm below is built against a library ATR rather than the existing
`indicators.average_directional_index` family, that part gets a real sourcing pass first. Logged in
`docs/BACKLOG.md`.

## Operator decisions (clarify step, 2026-07-27)

| axis | answer |
|---|---|
| trail trigger | *"hybrid of all 4 — think"* |
| trail distance | *"all 4 hybrid, think if possible, for the best option"* |
| stop/target | *"option one, and the target exit will also move based on the move so we can catch big wins — your suggestion"* |
| MFE/MAE | track on open **and** persist onto closed trades |

## The three position types this must serve (and their sign traps)

| type | field | profits when | trap |
|---|---|---|---|
| `OpenPaperPosition` (cash) | `entry_price`, `stop_loss_price`, `target_price`, `direction` | price moves the direction's way | already has both stop and target |
| `OpenDirectionalOptionPosition` | `entry_premium`, `lots`, `lot_size` | premium **rises** | no stop/target fields at all today |
| `OpenOptionSpreadPosition` | `entry_net_credit_per_unit` | net premium **falls** — **inverted** | credit received up front; profit = decay |

The credit spread is the sign trap: its P&L is `(entry_net_credit − current_net_premium) × lots ×
lot_size`, so "price up" is *loss*. Any trail written against a naive "higher is better" assumption
would ratchet the wrong way and turn a protective stop into a guaranteed loss. The engine therefore
works in **profit space (₹), never price space** — a single monotone quantity that means the same
thing for all three types.

## 1 · Excursion tracking (MFE / MAE) — the foundation

For every open position, carried on the position object and updated each pass:

- **MFE** (Maximum Favourable Excursion) — the highest unrealised profit reached since open.
- **MAE** (Maximum Adverse Excursion) — the worst unrealised loss reached since open.

Both in rupees, both monotone (MFE only rises, MAE only falls), both seeded at 0.0 at entry so a trade
that never goes green has `MFE = 0`, not `None`.

These are the operator's requested columns, and they are also the **evidence base** for tuning
everything below: persisted onto closed trades, `MFE ≫ realised profit` across a sample is the proof
that targets are capping runs, and `MAE` near-zero on winners proves stops are wider than they need
to be. Without them the trail can only ever be guessed at.

## 2 · The ARM trigger — earliest-of three yardsticks (not four)

**The trap in a literal 4-way hybrid:** "immediately from entry" fires at profit > 0, so OR-ing it
with the other three makes it always win and the other three decorative. It is therefore not a fourth
arm — it is the degenerate configuration of any arm with its threshold set to 0.

The honest hybrid is **earliest-of three**, because each guards a different failure mode:

```
armed  ⟺  profit ≥ arm_r_multiple × initial_risk        (R yardstick)
       ∨  profit ≥ arm_atr_multiple × atr_profit_units   (volatility yardstick)
       ∨  profit ≥ arm_profit_fraction × entry_notional  (percentage floor)
```

- **R** is the primary and works whenever the stop distance is meaningful.
- **ATR** covers the case where the stop was placed without regard to current volatility.
- **% floor** covers the case where the stop is pathologically tight, which makes R meaningless
  (1R of a 0.05% stop is noise).

Any arm whose input is unavailable (no ATR for an option premium, no stop on a directional option)
**abstains** rather than contributing a fabricated value — never a silent default.

## 3 · The trail DISTANCE — median of four candidates (a real consensus)

Taking the `max` of the four methods means the tightest always wins and the other three are
decorative; taking the `min` means the loosest always wins. Neither is a hybrid. The engine computes
**all four candidate locked-profit levels and takes the median** — a robust consensus that survives
any single method going pathological (an ATR spike, a degenerate stop distance):

| candidate | locked profit level |
|---|---|
| give-back fraction | `MFE × give_back_fraction` |
| step ratchet | `floor(MFE / initial_risk − 1) × initial_risk` (breakeven at 1R, +1R at 2R, …) |
| ATR chandelier | `MFE − atr_multiple × atr_profit_units` |
| fixed fraction | `MFE × (1 − fixed_give_back_fraction)` |

Candidates that cannot be computed abstain; the median is taken over whatever remains (with a
documented rule for 1 or 2 survivors).

**Hard ratchet, independent of the blend:** `locked_profit = max(previous_locked_profit, blended)`.
This is the operator's core requirement — *"protects and locks the profit movement as profit
increases"* — and it is enforced structurally, so no blend, parameter, or future arm can ever loosen
a lock. It is the single most important invariant in this engine.

## 4 · How it interacts with stop and target

**Stop (operator chose option 1).** The effective protective exit is the **tighter** of the original
stop and the trail: in profit space, exit when `unrealised_profit ≤ locked_profit` once armed, with
the original stop still active underneath. Strictly tightening — it can never widen risk.

**Target — moves outward (operator's request; this is my recommendation, with a caveat).**

```
effective_target_profit = max(original_target_profit, MFE + target_extension_multiple × initial_risk)
```

While the trade keeps making new highs the target keeps retreating *ahead* of it, so it never caps a
run; the trail behind it becomes the actual exit. This is what "catch big wins" requires.

**The caveat, stated plainly:** moving targets outward converts a high-win-rate / small-win system
into a lower-win-rate / larger-win one. This book's realised win rate is already low, so this change
could make the equity curve worse before it makes it better. Therefore, per **Rule Q**: build the
full mechanism now, but gate its **activation** behind a maturity ladder — it stays inert (extension
multiple 0 → target unchanged) until enough closed trades with persisted MFE show that targets are
in fact capping runs. The function is complete from day one; only the arming is earned. The trail
itself is NOT gated — locking profit is protective and safe to run immediately.

## 5 · Acceptance criteria

1. **Ratchet invariant:** `locked_profit` is non-decreasing over any sequence of price updates, for
   all three position types, including adversarial oscillation. *(the core property)*
2. Correct sign on a **credit spread** — a falling net premium is profit; the trail ratchets with it.
3. MFE is non-decreasing, MAE is non-increasing, both start at 0.0.
4. Before arming, the trail never exits a trade; the original stop is untouched.
5. After arming, an exit fires exactly when profit retraces to `locked_profit`.
6. The effective stop is never looser than the original stop.
7. Target extension is **inert** while immature (identity), and never moves the target *inward*.
8. An unavailable input (no ATR, no stop) makes that arm/candidate abstain — never fabricate.
9. MFE/MAE persist onto closed trades and are readable from the experience memory.
10. Rule-F: on real live positions, MFE/MAE columns populate and a real trade exits on the trail.

## 6 · Verification plan

- Property tests for criteria 1-3 over randomised price paths (the ratchet invariant is exactly a
  property test: no path may ever lower the lock).
- Unit tests for 4-8 with the real position dataclasses.
- Rule F on the live market: MFE/MAE visible on open positions, and a trail exit observed.
- **Rule J fallback:** if the market closes before a live trail exit is observed, the functional
  verification stands via injected price paths behind the existing feed seam, and **the real-data
  trail-exit observation remains an OPEN BLOCKER** — recorded, not waved through.

## 7 · Decomposition

- `paper_trading/position_excursion_tracker.py` — MFE/MAE, pure.
- `paper_trading/profit_trail_lock_engine.py` — arm triggers, candidate levels, median blend, hard
  ratchet, target extension. Pure; no I/O, no position mutation.
- Integration in `live_universe_paper_loop._manage_open_positions_against_prices` (cash) and
  `option_credit_spread_live_path.manage_open_*` (both option types).
- Persistence of MFE/MAE onto the closed-trade record + experience memory.
- Dashboard: new columns on the open-trade tables + a trail surface (Rule N).

## 8 · Explicitly NOT in this slice (Rule K)

- Tuning the parameters from evidence — that needs the persisted MFE/MAE to accrue first.
- Applying the trail to the **index**-option arms specifically (B16/B18 still gate those entries).
- The dashboard rebuild (B25) — this adds columns to the existing tables only.
