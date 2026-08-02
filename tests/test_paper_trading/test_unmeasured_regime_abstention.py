"""B31 — an UNMEASURED regime must abstain, not masquerade as range-bound.

`_regime_adx_warmed_at` returned 0.0 when ADX was not yet warm. 0.0 is indistinguishable from a
genuine ADX of zero and sits below the range-bound threshold, so an unmeasurable regime was
classified as a CONFIDENT "range-bound" read. B4 measured the damage: 144 of 376 experiments carried
win_probability ~= 0.0712 — the exact value ADX 0 produces — meaning ~38% of all trades were graded,
filed and LEARNED FROM under a regime never actually measured.

This matters more since B18: the regime is the arm selector's CONTEXT KEY, so a fabricated regime
files the outcome in the wrong cell and poisons the evidence the selector exists to accumulate.
"""

from datetime import datetime, timedelta

from nse_algo_trader.market_data.market_data_types import BarInterval, PriceBar
from nse_algo_trader.paper_trading.live_universe_paper_loop import _regime_adx_warmed_at
from nse_algo_trader.strategy_engine.session_strategy_regime_gate import (
    MarketRegime,
    V1SessionStrategyChoice,
    choose_v1_session_strategy,
    classify_adx_market_regime,
)

START = datetime(2026, 7, 27, 9, 15)


def _bars(count: int) -> list[PriceBar]:
    return [
        PriceBar(
            instrument_token=1,
            timestamp=START + timedelta(minutes=5 * index),
            interval=BarInterval.MINUTE_5,
            open_price=100.0 + index * 0.1, high_price=100.5 + index * 0.1,
            low_price=99.5 + index * 0.1, close_price=100.2 + index * 0.1,
            volume=1000,
        )
        for index in range(count)
    ]


class TestUnwarmedAdxIsUnknownNotZero:
    def test_too_few_bars_returns_None_not_a_fake_zero(self):
        bars = _bars(20)  # under the 28-bar warm-up
        assert _regime_adx_warmed_at(bars, bars[-1].timestamp) is None

    def test_enough_bars_returns_a_real_number(self):
        bars = _bars(60)
        assert isinstance(_regime_adx_warmed_at(bars, bars[-1].timestamp), float)

    def test_the_old_zero_sentinel_would_have_read_as_confidently_range_bound(self):
        """Pins WHY this was harmful: 0.0 is a confident regime, not an absence of one."""
        assert classify_adx_market_regime(0.0) is MarketRegime.RANGE_BOUND
        assert choose_v1_session_strategy(0.0) is V1SessionStrategyChoice.CREDIT_SPREAD

    def test_None_is_treated_as_unknown_and_stands_aside(self):
        assert classify_adx_market_regime(None) is MarketRegime.INDECISIVE
        assert choose_v1_session_strategy(None) is V1SessionStrategyChoice.STAND_ASIDE

    def test_a_genuine_low_adx_is_still_range_bound(self):
        """The fix must not make real low-ADX readings abstain — only UNMEASURED ones."""
        assert choose_v1_session_strategy(5.0) is V1SessionStrategyChoice.CREDIT_SPREAD
        assert choose_v1_session_strategy(0.5) is V1SessionStrategyChoice.CREDIT_SPREAD


class TestAbstentionIsCountedNotSilent:
    def test_the_loop_state_exposes_a_skip_counter(self):
        from nse_algo_trader.paper_trading import PaperTradingLedger
        from nse_algo_trader.paper_trading.live_universe_paper_loop import (
            LiveUniversePaperState,
        )
        from nse_algo_trader.paper_trading.prediction_lab import (
            PredictionTableScoreboard,
        )

        state = LiveUniversePaperState(
            ledger=PaperTradingLedger(1e8), scoreboard=PredictionTableScoreboard()
        )
        assert state.entries_skipped_for_unmeasured_regime_count == 0
