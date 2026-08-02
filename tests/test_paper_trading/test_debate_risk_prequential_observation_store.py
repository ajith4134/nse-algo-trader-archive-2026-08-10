"""Hermetic test for the debate-risk prequential observation store (Layer 11 slice 2c,
research/101): round-trips (risk_score, outcome) pairs, ordered, into the harness's input.
Uses a temp DB path (DI seam) — never touches the real store.
"""

from __future__ import annotations

from datetime import datetime

from nse_algo_trader.paper_trading.debate_risk_prequential_observation_store import (
    DebateRiskPrequentialObservationStore,
)


def test_records_and_reads_back_observations_in_order(tmp_path):
    store = DebateRiskPrequentialObservationStore(tmp_path / "obs.sqlite3")
    try:
        when = datetime(2026, 7, 25, 15, 15)
        store.record_observation("orb", 0.8, is_win=False, recorded_at=when)
        store.record_observation("orb", 0.2, is_win=True, recorded_at=when)
        store.record_observation("credit_spread", 0.6, is_win=True, recorded_at=when)

        observations = store.all_observations()
        assert store.observation_count() == 3
        assert [(o.risk_score, o.is_win) for o in observations] == [
            (0.8, False), (0.2, True), (0.6, True),
        ]
    finally:
        store.close()


def test_empty_store_yields_no_observations(tmp_path):
    store = DebateRiskPrequentialObservationStore(tmp_path / "empty.sqlite3")
    try:
        assert store.all_observations() == []
        assert store.observation_count() == 0
    finally:
        store.close()
