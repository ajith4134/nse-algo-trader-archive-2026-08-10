# Layer 7.5 Slice 4 — World-model scoreboard + Profit provenance (research/95 finale)

Date: 2026-07-25. Status: DESIGN → build this turn. Task: Layer 7.5 slice 4 (BACKLOG). The LAST of
the control-arms lab's "all 4". Read-only diagnostics over the arms + memory.

## 1. Goal (research/95 queued list)
- **World-model scoreboard** — score the bot's TRADE-INDEPENDENT forecasts (how good is its model
  of the market, separate from whether it made money): (a) prequential forecast SKILL (log-loss /
  Brier on its win-probability forecasts — calibration, not P&L) and (b) regime-model RESOLUTION
  (do its market-regime labels carry real information — different outcomes across regimes?).
- **Profit provenance** — decompose the real strategy's P&L vs the control arms: how much is LUCK
  (the random-control baseline), how much is DIRECTIONAL SKILL (real − random), and what the GATE
  contributed (loss avoided by refusing the vetoed mechanisms). Attributes profit to its sources.

## 2. Why (the two halves of "is it good, and why")
Profit provenance answers "where did the P&L come from" (execution/edge attribution). The
world-model scoreboard answers "is the underlying MODEL good" independent of P&L — a bot can have a
sound world model but thin edge, or make money by luck with a poor model. Together they close the
lab: skill-vs-luck (slice 1) + gate quality (slice 2) + tail (slice 3) + attribution + model
quality (slice 4).

## 3. Components (Rule C)
`paper_trading/profit_provenance.py` (PURE):
- `ProfitProvenance(total_real_return, luck_baseline, directional_skill,
  gate_avoided_loss_per_trade, dominant_source, detail)`.
- `decompose_profit_provenance(control_arm_comparison, shadow_rejected_analysis) ->
  ProfitProvenance` — `luck_baseline` = random-control total return; `directional_skill` = real −
  random total return; `gate_avoided_loss_per_trade` = −(shadow-rejected mean return) when the gate
  adds skill (the per-trade loss it refused); `dominant_source` = skill vs luck by magnitude.

`paper_trading/world_model_scoreboard.py` (PURE):
- `WorldModelScoreboard(forecast_experiments, forecast_log_loss_bits, forecast_brier,
  regime_resolution, world_model_informative, verdict)`.
- `score_world_model(experience_memory) -> WorldModelScoreboard` — reads
  `prequential_forecast_score()` (skill: <1.0 bit beats a coin-flip forecaster) and
  `calibration_by_market_regime()` (resolution = spread of hit-rates across regimes;
  `world_model_informative = resolution ≥ 0.05` AND forecast log-loss < 1.0).

## 4. Wiring (Rule G) + cadence
- Service `_maybe_run_lab_summary(now)` (daily, after the pre-mortem): reuse the cached slice-1
  comparison + recompute the shadow-rejected split → `decompose_profit_provenance`; and
  `score_world_model(memory)` → cache both. Best-effort.
- Two dashboard surfaces `profit_provenance` + `world_model_scoreboard` (Rule N).

## 5. Read-only (Rule K)
Both are diagnostics. No decision consumes them directly (the earlier slices' consumers cover the
acting side); these are the lab's summary verdicts. Nothing deferred beyond the already-tracked
per-slice learning/decision consumers.

## 6. Verification
- Hermetic (Rule J): provenance decomposition math over constructed arms; world-model verdict over
  a memory stub (informative vs noise regime spreads, skilled vs coin-flip forecast).
- Real-data (Rule F): over the real memory + real arms → the provenance split + the world-model
  scoreboard. `scripts/verify_lab_summary_realdata.py`.

## 7. ⇒ Layer 7.5 control-arms lab COMPLETE (all 4). Remaining across the project: the per-slice
decision/learning consumers (mostly market-gated) + the Layer-11 decision-consumers.
