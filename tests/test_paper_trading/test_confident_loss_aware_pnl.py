"""B33: the bot's REAL P&L excludes confident_loss learning probes, and the probe is scored on
prediction accuracy (a probe that LOST = the loss-prediction was RIGHT — the inverted metric)."""

from nse_algo_trader.paper_trading.confident_loss_aware_pnl import (
    split_realized_pnl_by_prediction_intent,
)


def _agg(realized_pnl: float, trade_count: int, loss_count: int) -> dict[str, float]:
    return {"realized_pnl": realized_pnl, "trade_count": trade_count, "loss_count": loss_count}


def test_real_pnl_excludes_confident_loss_probes():
    split = split_realized_pnl_by_prediction_intent({
        "confident_win": _agg(1000.0, 10, 3),
        "uncertain": _agg(-200.0, 8, 5),
        "confident_loss": _agg(-500.0, 6, 4),  # probe rupees must NOT touch real P&L
    })
    assert split.real_realized_pnl == 800.0        # 1000 + (-200), confident_loss excluded
    assert split.real_trade_count == 18
    assert split.probe_realized_pnl == -500.0
    assert split.probe_trade_count == 6


def test_probe_accuracy_counts_a_loss_as_a_correct_prediction():
    # 4 of 6 confident_loss probes actually LOST → the loss-prediction was right 4/6 of the time.
    split = split_realized_pnl_by_prediction_intent({
        "confident_loss": _agg(-500.0, 6, 4),
    })
    assert split.probe_prediction_accuracy == 4 / 6


def test_no_probes_yields_none_accuracy_and_zero_probe_pnl():
    split = split_realized_pnl_by_prediction_intent({"confident_win": _agg(300.0, 4, 1)})
    assert split.probe_prediction_accuracy is None
    assert split.probe_realized_pnl == 0.0
    assert split.real_realized_pnl == 300.0


def test_unknown_table_is_treated_as_real_money_failsafe():
    # a new real-money strategy label must not be silently dropped from the headline.
    split = split_realized_pnl_by_prediction_intent({"some_new_real_arm": _agg(150.0, 2, 0)})
    assert split.real_realized_pnl == 150.0
    assert split.probe_trade_count == 0


def test_empty_aggregate_is_all_zero():
    split = split_realized_pnl_by_prediction_intent({})
    assert split.real_realized_pnl == 0.0
    assert split.probe_realized_pnl == 0.0
    assert split.probe_prediction_accuracy is None
