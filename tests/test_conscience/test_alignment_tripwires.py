"""Hermetic test for the alignment tripwires (Trunk VII.10+VII.11; research/112): wireheading
flags win-rate-vs-return gaming (systemic = critical), the deceptive-alignment monitor flags
live-worse-than-replay, and clean cohorts stay clear. Pure, no I/O.
"""

from __future__ import annotations

from nse_algo_trader.conscience.alignment_tripwires import (
    deceptive_alignment_monitor,
    wireheading_tripwire,
)
from nse_algo_trader.memory_reflection.experience_memory import CalibrationBoardRow


def _row(mech, n, win, ret):
    return CalibrationBoardRow(
        strategy_tag="s", mechanism_name=mech, experiment_count=n,
        predicted_win_rate=win, actual_win_rate=win, mean_brier=0.2,
        mean_return_fraction=ret, mean_log_score=1.0,
    )


class _Memory:
    def __init__(self, overall=None, live=None, replay=None):
        self._overall = overall or []
        self._by = {"live": live or [], "replay_faithful": replay or []}

    def calibration_board(self, minimum_experiments=1, limit=50, data_provenance=None, **_):
        return list(self._by[data_provenance]) if data_provenance else list(self._overall)


# ----- wireheading -----


def test_wireheading_flags_high_winrate_negative_return_mechanism():
    mem = _Memory(overall=[
        _row("good", 100, 0.45, 0.02),           # big, profitable cohort → overall return positive
        _row("option_seller", 30, 0.80, -0.03),  # wins often, loses money → gaming (flagged)
    ])
    v = wireheading_tripwire(mem)
    # per-mechanism gaming flagged, but NOT systemic (overall return stays positive) → warning
    assert v.tripped and v.severity == "warning"
    assert "option_seller" in v.flagged


def test_wireheading_systemic_is_critical():
    # overall win-rate high but overall return negative → systemic reward-hack
    mem = _Memory(overall=[_row("m1", 50, 0.7, -0.02), _row("m2", 50, 0.65, -0.01)])
    v = wireheading_tripwire(mem)
    assert v.tripped and v.severity == "critical" and v.is_critical


def test_wireheading_clear_when_return_tracks_winrate():
    mem = _Memory(overall=[_row("m1", 40, 0.55, 0.01), _row("m2", 40, 0.30, -0.002)])
    v = wireheading_tripwire(mem)
    assert not v.tripped and v.severity == "clear"


# ----- deceptive alignment -----


def test_deceptive_alignment_trips_when_live_worse_than_replay():
    mem = _Memory(
        replay=[_row("m", 40, 0.60, 0.01)],   # looks good in eval
        live=[_row("m", 40, 0.40, -0.02)],    # worse in deploy → deceptive
    )
    v = deceptive_alignment_monitor(mem)
    assert v.tripped and v.severity == "critical"  # 20pp gap + return flip


def test_deceptive_alignment_clear_when_live_matches_replay():
    mem = _Memory(
        replay=[_row("m", 40, 0.50, 0.005)],
        live=[_row("m", 40, 0.49, 0.004)],
    )
    v = deceptive_alignment_monitor(mem)
    assert not v.tripped and v.severity == "clear"


def test_deceptive_alignment_insufficient_data_is_clear():
    mem = _Memory(replay=[_row("m", 3, 0.6, 0.01)], live=[_row("m", 2, 0.4, -0.01)])
    v = deceptive_alignment_monitor(mem)
    assert not v.tripped and "insufficient" in v.detail
