"""B33 — separate the bot's REAL realized P&L from its `confident_loss` learning probes.

The §9 prediction lab opens trades under three tables (research/9):
  · `confident_win`  — opened predicting a WIN, to make money. Real P&L.
  · `uncertain`      — a near-50% genuine experiment. Real P&L.
  · `confident_loss` — opened DELIBERATELY predicting a LOSS, so the bot learns to recognise losing
                       setups. This is a LEARNING PROBE, not a money-making trade.

For `confident_loss` the sign is INVERTED for scoring: a probe that actually LOST means the
loss-prediction was RIGHT (a learning success); a probe that PROFITED means the prediction was WRONG.
Its rupees are therefore NEVER added to the bot's real P&L — doing so would let deliberate-loss
probes flatter or dent the headline and misrepresent how the bot is actually doing.

This module is the single place that split is defined, so no panel or metric can re-mix the two.
"""

from __future__ import annotations

from dataclasses import dataclass

#: The §9 tables whose realized P&L IS the bot's real money (opened to profit / genuine experiment).
REAL_MONEY_ASSIGNED_TABLES: frozenset[str] = frozenset({"confident_win", "uncertain"})
#: The deliberate-loss learning-probe table (scored on prediction-correctness, not rupees).
CONFIDENT_LOSS_ASSIGNED_TABLE = "confident_loss"


@dataclass(frozen=True)
class ConfidentLossAwarePnlSplit:
    """The confident-loss-aware realized-P&L split for the dashboard headline."""

    real_realized_pnl: float           # Σ realized_pnl over confident_win + uncertain
    real_trade_count: int
    probe_realized_pnl: float          # Σ realized_pnl over confident_loss (reported separately)
    probe_trade_count: int
    #: fraction of confident_loss probes that ACTUALLY lost = how often the loss-prediction was
    #: right (the inverted "loss is profit" learning metric). None when no probes have closed yet.
    probe_prediction_accuracy: float | None


def split_realized_pnl_by_prediction_intent(
    realized_pnl_by_assigned_table: dict[str, dict[str, float]],
) -> ConfidentLossAwarePnlSplit:
    """Fold the per-table aggregate (`{table: {realized_pnl, trade_count, loss_count}}`, e.g. from
    `ExperienceMemory.realized_pnl_by_assigned_table`) into the real-vs-probe split. Unknown table
    labels are treated as real money (fail-safe: a new real strategy is never silently dropped from
    the headline; only the explicit confident_loss table is segregated)."""
    real_realized_pnl = 0.0
    real_trade_count = 0
    probe_realized_pnl = 0.0
    probe_trade_count = 0
    probe_loss_count = 0

    for assigned_table, aggregate in realized_pnl_by_assigned_table.items():
        realized_pnl = float(aggregate.get("realized_pnl", 0.0))
        trade_count = int(aggregate.get("trade_count", 0))
        if assigned_table == CONFIDENT_LOSS_ASSIGNED_TABLE:
            probe_realized_pnl += realized_pnl
            probe_trade_count += trade_count
            probe_loss_count += int(aggregate.get("loss_count", 0))
        else:
            # confident_win, uncertain, and any unrecognised real-money label
            real_realized_pnl += realized_pnl
            real_trade_count += trade_count

    probe_prediction_accuracy = (
        probe_loss_count / probe_trade_count if probe_trade_count > 0 else None
    )
    return ConfidentLossAwarePnlSplit(
        real_realized_pnl=real_realized_pnl,
        real_trade_count=real_trade_count,
        probe_realized_pnl=probe_realized_pnl,
        probe_trade_count=probe_trade_count,
        probe_prediction_accuracy=probe_prediction_accuracy,
    )
