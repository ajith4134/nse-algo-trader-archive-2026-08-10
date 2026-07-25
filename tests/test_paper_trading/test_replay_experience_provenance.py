"""ReplayExperienceProvenanceTagger — the tag that stops replayed experience
from being mistaken for live (research/62 P6, research/53 §8.2, §10.3).
"""

from datetime import date

from nse_algo_trader.paper_trading.replay_experience_provenance import (
    DataProvenance,
    ReplayExperienceProvenanceTagger,
    ReplayFidelityTier,
)


def test_base_tier_stamps_replay_faithful_bar_only():
    stamp = ReplayExperienceProvenanceTagger().stamp_for_session(date(2020, 3, 12))
    assert stamp.provenance is DataProvenance.REPLAY_FAITHFUL
    assert stamp.fidelity_tier is ReplayFidelityTier.BAR_ONLY
    assert stamp.session_date == date(2020, 3, 12)


def test_recorded_depth_beats_everything_when_available():
    tier = ReplayExperienceProvenanceTagger.best_available_fidelity_for(
        date(2026, 7, 24), have_recorded_depth=True
    )
    assert tier is ReplayFidelityTier.RECORDED_DEPTH


def test_licensed_tick_is_tick_derived_in_the_tick_era_and_trades_only_before():
    tagger = ReplayExperienceProvenanceTagger
    # Post ~Dec-2007 → per-order tick.
    assert (
        tagger.best_available_fidelity_for(date(2015, 1, 5), have_licensed_tick=True)
        is ReplayFidelityTier.TICK_DERIVED
    )
    # Pre ~Dec-2007 → the archive is trades-only (research/53 §10.3).
    assert (
        tagger.best_available_fidelity_for(date(2005, 1, 5), have_licensed_tick=True)
        is ReplayFidelityTier.TRADES_ONLY
    )


def test_bar_only_is_the_honest_floor_with_no_richer_source():
    assert (
        ReplayExperienceProvenanceTagger.best_available_fidelity_for(date(2009, 6, 1))
        is ReplayFidelityTier.BAR_ONLY
    )
