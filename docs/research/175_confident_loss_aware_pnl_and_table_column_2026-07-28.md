# B33 — Confident-loss-aware P&L + assigned-table column on closed trades (2026-07-28)

## Intent (operator, 2026-07-28)
Every closed trade must show WHICH §9 table it opened under (`confident_win` / `confident_loss` /
`uncertain`), and the headline P&L must STOP lumping `confident_loss` probes into the bot's real money.

`confident_loss` trades are opened DELIBERATELY predicting a loss — a learning probe so the AI learns
to recognise losing setups. Their sign is INVERTED for scoring: a trade that **loses = prediction was
RIGHT** (learning success); a trade that **profits = prediction was WRONG**. Their rupees are NOT the
bot's real P&L.

**Definitions this build enforces:**
- **Real realized P&L** = Σ realized_pnl over `confident_win` + `uncertain` trades only.
- **Confident-loss probe P&L** = Σ realized_pnl over `confident_loss` trades — reported SEPARATELY,
  never added to real P&L.
- **Confident-loss prediction accuracy** = (# confident_loss trades that actually LOST) / (# confident_loss
  trades) — the "loss is profit" learning metric.

## Why it's cheap (data already exists)
`memory_reflection` `experience_nodes` already stores `assigned_table`, `actual_outcome (win|loss)`,
`realized_pnl` per closed trade (durable, spans sessions — the authoritative source the closed-trades
panel already reads via `recent_closed_experiences`). Gaps: (a) that SELECT omits `assigned_table`;
(b) no group-by-table P&L aggregate; (c) `combined_realized_pnl` sums everything; (d) `ClosedTradeView`
+ render have no table column; (e) `ClosedPaperTrade` (ledger fallback) lacks the field.

## Build (decomposition)
1. `sqlite_experience_memory.py`: add `assigned_table` to `recent_closed_experiences` SELECT; add
   `realized_pnl_by_assigned_table()` → `{table: {realized_pnl, trade_count, loss_count}}` (real SQL
   GROUP BY, the authoritative split across ALL sessions).
2. `experience_memory.py` Protocol: declare the new method; document the row now carries assigned_table.
3. `dashboard_read_model.py`: `ClosedTradeView.assigned_table`; new snapshot fields
   `real_realized_pnl`, `confident_loss_probe_realized_pnl`, `confident_loss_prediction_accuracy`;
   keep `combined_realized_pnl` (relabelled "gross incl. probes") for continuity.
4. `live_paper_trading_service.py`: populate `assigned_table` in `_recent_closed_trades`; compute the
   three split figures from `realized_pnl_by_assigned_table()`; pass into the snapshot.
5. `live_universe_paper_loop.py`: add `assigned_table` to `ClosedPaperTrade`, populate at close
   (prediction_record is in scope), and set it in the ledger-fallback `ClosedTradeView`.
6. `render_dashboard_html.py`: closed-trades table gets a "Table" column (win/loss/unc tag); the
   headline splits into **Real P&L (confident-win + uncertain)** and a separate **Confident-loss lab**
   card showing probe P&L + prediction-accuracy with the inverted-interpretation label.

## Acceptance (Rule P/F/O)
- Real P&L excludes every confident_loss trade (unit test on a mixed set).
- Prediction accuracy inverts correctly (a confident_loss trade that LOST counts as correct).
- Column present on every closed row.
- Rule-F: verified on the LIVE experience memory (908+ real closed trades today) — real vs probe split
  reconciles to per-table SQL sums; panel shows the column.

## Sourcing gate (Rule I)
**No external OSS search applicable — 100% REUSE of in-repo infrastructure.** This is accounting logic
over an EXISTING schema (`experience_nodes` already stores `assigned_table`/`actual_outcome`/
`realized_pnl`): a SQL `GROUP BY assigned_table` aggregate + read-model/render wiring. No algorithm,
parser, or model to source — nothing a library would provide that the existing SQLite store + read
model don't. Not a deferred search; a genuinely N/A one.

## Dashboard (Rule N)
Extends the existing closed-trades + P&L surfaces — no new orphan; the read model is the consumer.
