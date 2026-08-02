"""B18 arm 1 — IV rank/percentile, and the abstention that keeps it honest.

The load-bearing test here is the expiry-cadence break: on 2024-11-20 SEBI's one-weekly-index rule
removed weekly expiries from BANKNIFTY/FINNIFTY/MIDCPNIFTY. A 252-day lookback spanning that date
compares weekly ATM IV against monthly ATM IV — different time-to-expiry, different term-structure
point — and calling that difference "rank" would size real trades on a fabricated number.

See `docs/research/b18_index_options_ensemble_SPEC_2026-07-27.md`.
"""

from datetime import date, timedelta

from nse_algo_trader.strategy_engine.implied_volatility_rank import (
    MINIMUM_OBSERVATIONS_FOR_RANK,
    UNDERLYINGS_WITH_EXPIRY_CADENCE_BREAK,
    WEEKLY_EXPIRY_WITHDRAWAL_DATE,
    lookback_spans_expiry_cadence_break,
    rank_implied_volatility,
)


def _history(start: date, values: list[float]) -> dict[date, float]:
    return {start + timedelta(days=index): iv for index, iv in enumerate(values)}


AFTER_BREAK = WEEKLY_EXPIRY_WITHDRAWAL_DATE + timedelta(days=30)
LONG_AGO = WEEKLY_EXPIRY_WITHDRAWAL_DATE - timedelta(days=200)


class TestTheStatistics:
    def test_iv_at_the_top_of_its_range_ranks_high(self):
        history = _history(AFTER_BREAK, [10.0 + (index % 10) for index in range(120)])
        ranking = rank_implied_volatility("NIFTY", 19.0, history)
        assert ranking.is_usable
        assert ranking.implied_volatility_rank > 90.0
        assert ranking.implied_volatility_percentile > 80.0

    def test_iv_at_the_bottom_of_its_range_ranks_low(self):
        history = _history(AFTER_BREAK, [10.0 + (index % 10) for index in range(120)])
        ranking = rank_implied_volatility("NIFTY", 10.1, history)
        assert ranking.implied_volatility_rank < 10.0
        assert ranking.implied_volatility_percentile < 20.0

    def test_rank_and_percentile_disagree_informatively_on_a_single_spike(self):
        """One panic spike sets iv_max for a year — IVR is crushed while IVP stays honest.

        This is exactly why both are reported and why `is_rich` requires BOTH.
        """
        values = [12.0] * 119 + [80.0]  # one spike
        ranking = rank_implied_volatility("NIFTY", 13.0, _history(AFTER_BREAK, values))
        assert ranking.implied_volatility_rank < 5.0      # crushed by the spike
        assert ranking.implied_volatility_percentile > 90.0  # robust
        assert not ranking.is_rich, "a single spike must not qualify as 'IV rich'"

    def test_rich_and_cheap_require_both_measures_to_agree(self):
        rising = _history(AFTER_BREAK, [float(index) for index in range(1, 121)])
        assert rank_implied_volatility("NIFTY", 119.0, rising).is_rich
        assert rank_implied_volatility("NIFTY", 2.0, rising).is_cheap
        middle = rank_implied_volatility("NIFTY", 60.0, rising)
        assert not middle.is_rich and not middle.is_cheap

    def test_a_new_high_clamps_into_range_rather_than_exceeding_100(self):
        history = _history(AFTER_BREAK, [10.0 + (index % 10) for index in range(120)])
        ranking = rank_implied_volatility("NIFTY", 500.0, history)
        assert ranking.implied_volatility_rank == 100.0
        assert ranking.implied_volatility_percentile == 100.0


class TestTheExpiryCadenceBreakAbstention:
    def test_a_transitioned_index_abstains_when_the_window_spans_the_break(self):
        """THE abstention: weekly IV and monthly IV are not the same quantity."""
        history = _history(LONG_AGO, [12.0 + (index % 8) for index in range(300)])
        for symbol in UNDERLYINGS_WITH_EXPIRY_CADENCE_BREAK:
            ranking = rank_implied_volatility(symbol, 15.0, history)
            assert not ranking.is_usable, f"{symbol} must abstain across the break"
            assert "weekly" in ranking.abstained_reason
            assert ranking.implied_volatility_rank is None

    def test_the_same_index_is_usable_once_the_window_is_wholly_after_the_break(self):
        history = _history(AFTER_BREAK, [12.0 + (index % 8) for index in range(120)])
        ranking = rank_implied_volatility("BANKNIFTY", 15.0, history)
        assert ranking.is_usable, "a post-break window is like-for-like and must be usable"

    def test_nifty_is_unaffected_because_it_KEPT_its_weeklies(self):
        history = _history(LONG_AGO, [12.0 + (index % 8) for index in range(300)])
        assert rank_implied_volatility("NIFTY", 15.0, history).is_usable

    def test_niftynxt50_is_unaffected_because_it_never_transitioned(self):
        """It launched monthly-only in April 2024 — there is no cadence break to span."""
        assert "NIFTYNXT50" not in UNDERLYINGS_WITH_EXPIRY_CADENCE_BREAK
        history = _history(LONG_AGO, [12.0 + (index % 8) for index in range(300)])
        assert rank_implied_volatility("NIFTYNXT50", 15.0, history).is_usable

    def test_the_break_predicate_is_exact_about_straddling(self):
        assert not lookback_spans_expiry_cadence_break("BANKNIFTY", [])
        assert not lookback_spans_expiry_cadence_break(
            "BANKNIFTY", [AFTER_BREAK, AFTER_BREAK + timedelta(days=5)]
        )
        assert not lookback_spans_expiry_cadence_break("NIFTY", [LONG_AGO, AFTER_BREAK])
        assert lookback_spans_expiry_cadence_break("BANKNIFTY", [LONG_AGO, AFTER_BREAK])


class TestMaturityAndDegenerateInput:
    def test_a_short_history_abstains_rather_than_ranking_noise(self):
        history = _history(AFTER_BREAK, [12.0] * (MINIMUM_OBSERVATIONS_FOR_RANK - 1))
        ranking = rank_implied_volatility("NIFTY", 15.0, history)
        assert not ranking.is_usable
        assert "need" in ranking.abstained_reason
        assert ranking.observation_count == MINIMUM_OBSERVATIONS_FOR_RANK - 1

    def test_a_flat_history_abstains_instead_of_dividing_by_zero(self):
        history = _history(AFTER_BREAK, [12.0] * 120)
        ranking = rank_implied_volatility("NIFTY", 15.0, history)
        assert not ranking.is_usable
        assert "degenerate" in ranking.abstained_reason

    def test_a_missing_current_iv_abstains(self):
        history = _history(AFTER_BREAK, [12.0 + (index % 8) for index in range(120)])
        assert not rank_implied_volatility("NIFTY", 0.0, history).is_usable
        assert not rank_implied_volatility("NIFTY", None, history).is_usable

    def test_non_positive_history_points_are_dropped_not_counted(self):
        history = _history(AFTER_BREAK, [12.0 + (index % 8) for index in range(120)])
        history[AFTER_BREAK + timedelta(days=500)] = 0.0
        history[AFTER_BREAK + timedelta(days=501)] = -3.0
        assert rank_implied_volatility("NIFTY", 15.0, history).observation_count == 120

    def test_the_lookback_window_is_respected(self):
        history = _history(AFTER_BREAK, [float(index) for index in range(1, 400)])
        ranking = rank_implied_volatility("NIFTY", 350.0, history, lookback_trading_days=100)
        assert ranking.observation_count == 100

    def test_an_abstention_never_leaks_a_rich_or_cheap_verdict(self):
        history = _history(AFTER_BREAK, [12.0] * 10)
        ranking = rank_implied_volatility("NIFTY", 15.0, history)
        assert not ranking.is_usable
        assert not ranking.is_rich and not ranking.is_cheap
