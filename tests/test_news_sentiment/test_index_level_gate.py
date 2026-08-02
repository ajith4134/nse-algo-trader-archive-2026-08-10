"""Hermetic tests for the index-level option gate (Trunk II SENSES, research/151).

Covers the pure proximity multiplier + the load-bearing safety property (identity until earned), and
the loop-state wiring.
"""

from nse_algo_trader.news_sentiment.index_level_gate import (
    index_level_size_multiplier,
    nearest_level_distance_pct,
)

NIFTY_LEVELS = [23600.0, 23800.0, 24000.0, 24200.0]


def test_nearest_distance():
    assert abs(nearest_level_distance_pct(24010.0, NIFTY_LEVELS) - (10.0 / 24010.0)) < 1e-9
    assert nearest_level_distance_pct(24010.0, []) is None


def test_identity_until_earned():
    # Sitting right on 24,000 but NOT earned → identity (safety).
    assert index_level_size_multiplier(24000.0, NIFTY_LEVELS, calibration_earned=False) == 1.0


def test_defer_when_on_a_level_once_earned():
    assert index_level_size_multiplier(24000.0, NIFTY_LEVELS, calibration_earned=True) == 0.0  # on the level


def test_size_down_when_near_a_level():
    # 24,120 is ~0.5% from 24,000/24,200 → within the 1.0% size-down band.
    assert index_level_size_multiplier(24120.0, NIFTY_LEVELS, calibration_earned=True) == 0.5


def test_no_change_when_far_from_levels():
    assert index_level_size_multiplier(24700.0, NIFTY_LEVELS, calibration_earned=True) == 1.0  # >2% away
    assert index_level_size_multiplier(24000.0, [], calibration_earned=True) == 1.0  # no levels


def test_loop_state_gate_wired_and_safe():
    from nse_algo_trader.paper_trading.live_universe_paper_loop import LiveUniversePaperState

    state = LiveUniversePaperState.__new__(LiveUniversePaperState)
    state.index_level_values_by_underlying = {"NIFTY": NIFTY_LEVELS}
    state.index_level_calibration_earned = False
    state.index_level_deferred_count = 0
    state.index_level_sized_down_count = 0
    assert state.index_level_size_multiplier("NIFTY", 24000.0) == 1.0   # advisory → safe
    assert state.index_level_size_multiplier("BANKNIFTY", 51000.0) == 1.0  # no levels → identity

    state.index_level_calibration_earned = True
    assert state.index_level_size_multiplier("NIFTY", 24000.0) == 0.0   # earned + on level → defer
    assert state.index_level_deferred_count == 1
