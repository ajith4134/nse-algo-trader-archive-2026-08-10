"""B34 task #4: the per-underlying option-entry OUTCOME recorder.

Instrumentation that makes the INDEX-options firing gate diagnosable live (stocks fire, indices
don't). Pins that the recorder stores the latest reason+detail per underlying and aggregates counts,
and never raises (a diagnostic must never break a trading pass)."""

from nse_algo_trader.paper_trading import PaperTradingLedger
from nse_algo_trader.paper_trading.live_universe_paper_loop import LiveUniversePaperState
from nse_algo_trader.paper_trading.prediction_lab import PredictionTableScoreboard


def _state():
    return LiveUniversePaperState(
        ledger=PaperTradingLedger(1e8), scoreboard=PredictionTableScoreboard()
    )


def test_records_latest_reason_and_detail_per_underlying():
    s = _state()
    s.record_option_entry_outcome("NIFTY", "sized_down_to_zero", "composed=0.30")
    s.record_option_entry_outcome("RELIANCE", "opened_credit_spread", "2lot")
    assert s.option_entry_outcome_by_underlying["NIFTY"]["reason"] == "sized_down_to_zero"
    assert s.option_entry_outcome_by_underlying["NIFTY"]["detail"] == "composed=0.30"
    assert s.option_entry_outcome_by_underlying["RELIANCE"]["reason"] == "opened_credit_spread"


def test_latest_outcome_overwrites_and_counts_accumulate():
    s = _state()
    s.record_option_entry_outcome("NIFTY", "directional_no_breakout")
    s.record_option_entry_outcome("NIFTY", "directional_no_breakout")
    s.record_option_entry_outcome("NIFTY", "opened_directional", "1lot long")
    # latest per underlying is the OPEN; counts keep the whole history
    assert s.option_entry_outcome_by_underlying["NIFTY"]["reason"] == "opened_directional"
    assert s.option_entry_reason_counts["directional_no_breakout"] == 2
    assert s.option_entry_reason_counts["opened_directional"] == 1


def test_recorder_never_raises_on_bad_timestamp():
    s = _state()
    # `now` without isoformat must not blow up the trading pass — the recorder swallows its own errors.
    s.record_option_entry_outcome("NIFTY", "gate_oversight", "wp=0.40", now=object())
    # the reason count still incremented is not required; the guarantee is simply: no exception.
