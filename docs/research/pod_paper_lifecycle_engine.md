# Pod Paper Lifecycle Engine (slice 2a) — close the cold-start deadlock, populate the board

## The real blocker (diagnosed on real data, Rule F)
The segment-bot pod runs cycles but proposes 0 trades and the board stays empty. NOT a data gap — the
adapters serve real full-universe stored data (5 index underlyings, 2,416 cash names, 1,872-row chains,
real ATM IV). Two coupled deadlocks:

1. **Cold-start gate.** Every bot does `if not competency.is_earned: return []`, and the supervisor sets an
   unearned bot's allocation weight to `0.0`. With 0 closed trades a bot is never earned → never proposes /
   never sized → never trades → never accrues a closed trade → never earns. A permanent standstill.
2. **No feedback loop.** Nothing ever calls `record_closed_trade` on the 3 bots. The pod opens orders via
   `PodOrderRouter → SimulatedBrokerClient` but never marks, exits, or closes them back into the bots'
   track record. Even if (1) were fixed, competency could not accrue.

## The engine (not a scalar)
A **PodPaperLifecycleEngine** carrying persisted open-position STATE across cycles, running a real
mark→exit→square-off simulation each tick, and feeding realised outcomes back into each bot's competency +
learned-head training loop — the closed loop that makes the pod self-improve.

**SOTA analog:** NautilusTrader's position lifecycle + a paper matching engine; the accrual loop mirrors
Qlib's rolling retrain (each closed trade is a labelled sample the bot's head trains on).

### Modules / data flow
```
PodRunner.run_cycle
  → supervisor proposals (COLD-START: unearned bots propose at a paper floor)   [layer A]
  → router opens accepted orders on SimulatedBrokerClient (real fills)
  → PodPaperLifecycleEngine.on_opened(placed, decision)  → persist OPEN positions [layer B, carried state]
  → PodPaperLifecycleEngine.mark_and_exit(now, adapters) each cycle:             [layer C]
        mark each open leg at the real adapter price / option-chain mid
        exit rule: stop-loss · target · intraday square-off (mandatory pre-close, never carry)
        on exit → realised P&L → ClosedTrade(features, won, entry_epoch, calibrated_prob)
                → owning_bot.record_closed_trade(...) → competency accrues + head trains  [layer D]
```

### Layer A — cold-start (Rule Q, correct maturity ladder)
Immature behaviour is NOT silence — it is full-function paper participation at a floor size, with LIVE
capital-weight still gated. Change per bot: `propose()` runs the full pipeline always (drop the
`return []`); the size functions take a **paper floor of 1 lot/unit at competency level 0** so a trade can
actually open and accrue. Supervisor: an unearned bot gets a small non-zero **warm-up weight** (floor) so
the allocator can grant the paper floor, instead of `0.0`. Live trading still requires earned competency
(a separate gate at the live-execution seam, unchanged). This is Rule Q exactly: full algorithm, ACTIVATION
laddered, arms automatically as trades accrue — never a shrunk algorithm.

### Layer B/C — carried state + real exit simulation
`PodOpenPositionStore` persists open positions (JSON) keyed by a pod-order id: underlying, segment, side,
legs (token, qty, entry fill), stop/target, owning bot name, entry epoch, entry features + calibrated_prob.
Each cycle marks legs at the real price (`adapter.price_series` last for cash/underlying; option-chain mid
for option legs) and applies exits. Intraday square-off is unconditional near close (the project's binding
intraday-only rule) — no overnight carry, ever.

### Layer D — decision-grade output that CHANGES behaviour
Each close calls `owning_bot.record_closed_trade` → competency ladder advances → future proposals arm +
size up, and the learned win-probability head trains on the new labelled trial. This is the behaviour
change: the pod goes from permanently idle to a self-improving trading loop; the per-bot heartbeat then
shows real `proposed · accepted`, and the board populates.

## Depth justification (what a thin diagnostic would omit)
A diagnostic would show "0 trades, gathering" and stop. This engine builds the missing acting path: carried
open-position state, a real fill/mark/exit simulation on real prices, mandatory intraday square-off, and the
competency+ML accrual feedback loop. It changes real decisions (what each bot proposes and how it is sized
next cycle). It composes the existing `SimulatedBrokerClient` + `PaperTradingLedger` + `market_impact_fill_model`
rather than reimplementing a matching engine.

## Sourcing (Rule I/O)
Compose existing internal engines — `broker_oms.simulated_broker_client.SimulatedBrokerClient` (fills +
trigger eval + net position), `paper_trading.fill_slippage_model` / `market_impact_fill_model` (fill realism),
`paper_trading.position_excursion_tracker` (MFE/MAE). No external OSS part; the heavyweight ML already lives
in the bots' heads. Logged, not a silent skip.

## Verification (Rule F / J)
Real-data: run `PodRunner` on the real market store; assert unearned bots now propose (paper floor), the
lifecycle opens + marks + squares-off on real prices, `record_closed_trade` fires, competency `closed_trades`
increments, and `last_cycle.json.by_bot` shows `proposals>0`. Eyeball the realised P&L + a closed trade.
Unit/property: cold-start proposes; square-off never carries past close; a stop/target exit computes correct
P&L sign; competency accrues monotonically; hermetic fake adapter (Rule J) drives a full open→close cycle.

## Backlog (Rule K)
- Live intraday feed (slice 2b) — replace stored bhavcopy with today's 5m bars + live chain (freshness).
- Real margin/lot-notional in sizing (currently nominal ₹100k/lot).
- Option-leg mid from the chain vs last-trade — refine mark source.
