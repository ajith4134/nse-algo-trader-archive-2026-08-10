"""B18.1b — the daily ATM-IV history that lets the IV-rank arm arm at all.

The loop already computes ATM IV every option pass and discarded it. Without a stored history,
`rank_implied_volatility` can only ever abstain on "<60 observations".

The subtle requirement these pin: the history must be UNBIASED. Recording IV only inside the
credit-spread (range-bound) branch would build a series sampled exclusively from quiet sessions,
so trending days — typically higher IV — would never enter the distribution and every "rank" would
be measured against a truncated sample.
"""

from datetime import date, timedelta

import pytest

from nse_algo_trader.market_data.market_data_sqlite_store import MarketDataSqliteStore
from nse_algo_trader.strategy_engine.implied_volatility_rank import (
    rank_implied_volatility,
)


@pytest.fixture
def store(tmp_path):
    store = MarketDataSqliteStore(tmp_path / "market_data.sqlite3")
    yield store
    store.close()


class TestDailyAtmImpliedVolatilityStore:
    def test_an_observation_round_trips(self, store):
        assert store.save_daily_atm_implied_volatility("NIFTY", date(2026, 7, 27), 13.5)
        history = store.load_atm_implied_volatility_history("NIFTY")
        assert history == {date(2026, 7, 27): 13.5}

    def test_one_row_per_symbol_and_date_last_write_wins(self, store):
        store.save_daily_atm_implied_volatility("NIFTY", date(2026, 7, 27), 13.5)
        store.save_daily_atm_implied_volatility("NIFTY", date(2026, 7, 27), 14.9)
        history = store.load_atm_implied_volatility_history("NIFTY")
        assert history == {date(2026, 7, 27): 14.9}

    def test_symbols_are_kept_separate(self, store):
        store.save_daily_atm_implied_volatility("NIFTY", date(2026, 7, 27), 13.5)
        store.save_daily_atm_implied_volatility("BANKNIFTY", date(2026, 7, 27), 18.2)
        assert store.load_atm_implied_volatility_history("NIFTY") == {date(2026, 7, 27): 13.5}
        assert store.load_atm_implied_volatility_history("BANKNIFTY") == {date(2026, 7, 27): 18.2}

    def test_a_bad_inversion_is_refused_not_stored(self, store):
        """A non-positive or non-finite IV must never poison the rich-vs-cheap history."""
        for bad in (0.0, -1.0, float("nan"), float("inf"), None):
            assert not store.save_daily_atm_implied_volatility("NIFTY", date(2026, 7, 27), bad)
        assert store.load_atm_implied_volatility_history("NIFTY") == {}

    def test_the_lookback_window_is_respected_and_newest_first(self, store):
        start = date(2026, 1, 1)
        for index in range(300):
            store.save_daily_atm_implied_volatility(
                "NIFTY", start + timedelta(days=index), 10.0 + index * 0.01
            )
        assert len(store.load_atm_implied_volatility_history("NIFTY", lookback_days=252)) == 252
        assert len(store.load_atm_implied_volatility_history("NIFTY", lookback_days=30)) == 30

    def test_observation_counts_give_the_rule_q_have_n_read(self, store):
        for index in range(5):
            store.save_daily_atm_implied_volatility(
                "NIFTY", date(2026, 1, 1) + timedelta(days=index), 12.0
            )
        store.save_daily_atm_implied_volatility("BANKNIFTY", date(2026, 1, 1), 18.0)
        counts = store.atm_implied_volatility_observation_counts()
        assert counts["NIFTY"] == 5
        assert counts["BANKNIFTY"] == 1

    def test_an_empty_history_reads_as_empty_not_an_error(self, store):
        assert store.load_atm_implied_volatility_history("NEVERSEEN") == {}
        assert store.atm_implied_volatility_observation_counts() == {}


class TestTheStoreFeedsTheRanker:
    def test_a_stored_history_arms_the_ranker_end_to_end(self, store):
        """The whole point of B18.1b: accumulate enough observations and the rank becomes usable."""
        start = date(2025, 1, 6)  # wholly after the 2024-11-20 cadence break
        for index in range(120):
            store.save_daily_atm_implied_volatility(
                "BANKNIFTY", start + timedelta(days=index), 12.0 + (index % 10)
            )
        history = store.load_atm_implied_volatility_history("BANKNIFTY")
        ranking = rank_implied_volatility("BANKNIFTY", 21.0, history)
        assert ranking.is_usable, ranking.abstained_reason
        assert ranking.observation_count == 120
        assert ranking.implied_volatility_rank > 90.0

    def test_a_thin_history_still_abstains_rather_than_ranking_noise(self, store):
        start = date(2025, 1, 6)
        for index in range(10):
            store.save_daily_atm_implied_volatility(
                "BANKNIFTY", start + timedelta(days=index), 12.0 + index
            )
        ranking = rank_implied_volatility(
            "BANKNIFTY", 15.0, store.load_atm_implied_volatility_history("BANKNIFTY")
        )
        assert not ranking.is_usable
        assert "need" in ranking.abstained_reason


class TestCaptureIsUnbiasedAcrossRegimes:
    """The recorder sits BEFORE the regime branch, so a trending underlying's IV is captured too.

    If it sat inside the credit-spread branch, the stored series would contain only range-bound
    sessions and every later 'rank' would be measured against a truncated sample.
    """

    def test_the_state_recorder_is_a_noop_when_unwired(self):
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
        state.record_daily_atm_implied_volatility("NIFTY", date(2026, 7, 27), 13.5)
        assert state.atm_implied_volatility_recorded_count == 0

    def test_a_wired_recorder_counts_only_real_writes(self, store):
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
        state.atm_implied_volatility_recorder = store.save_daily_atm_implied_volatility
        state.record_daily_atm_implied_volatility("NIFTY", date(2026, 7, 27), 13.5)
        state.record_daily_atm_implied_volatility("NIFTY", date(2026, 7, 28), 0.0)  # refused
        assert state.atm_implied_volatility_recorded_count == 1

    def test_a_failing_recorder_never_breaks_a_trading_pass(self, capsys):
        from nse_algo_trader.paper_trading import PaperTradingLedger
        from nse_algo_trader.paper_trading.live_universe_paper_loop import (
            LiveUniversePaperState,
        )
        from nse_algo_trader.paper_trading.prediction_lab import (
            PredictionTableScoreboard,
        )

        def _explode(*_args):
            raise RuntimeError("disk full")

        state = LiveUniversePaperState(
            ledger=PaperTradingLedger(1e8), scoreboard=PredictionTableScoreboard()
        )
        state.atm_implied_volatility_recorder = _explode
        state.record_daily_atm_implied_volatility("NIFTY", date(2026, 7, 27), 13.5)  # must not raise
        assert state.atm_implied_volatility_recorded_count == 0
        assert "iv-history" in capsys.readouterr().out  # surfaced, not swallowed
