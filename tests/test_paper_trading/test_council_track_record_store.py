"""Hermetic test for the council track-record store (Layer 11 slice 5, research/104): resolved
per-role forecasts round-trip and the mean log-loss (bits) is computed correctly. Temp DB path.
"""

from __future__ import annotations

import math
from datetime import datetime

import pytest

from nse_algo_trader.paper_trading.council_track_record_store import (
    CouncilTrackRecordStore,
)


def test_records_resolved_forecasts_and_computes_role_log_loss(tmp_path):
    store = CouncilTrackRecordStore(tmp_path / "council.sqlite3")
    try:
        when = datetime(2026, 7, 25, 15, 15)
        # momentum forecast 0.9 on a TRUE outcome → log-loss = -log2(0.9)
        store.record_resolved_forecast("momentum", 0.9, is_true=True, recorded_at=when)
        # momentum forecast 0.9 on a FALSE outcome → log-loss = -log2(0.1)
        store.record_resolved_forecast("momentum", 0.9, is_true=False, recorded_at=when)
        store.record_resolved_forecast("risk_officer", 0.5, is_true=True, recorded_at=when)

        assert store.resolved_forecast_count() == 3
        losses = store.role_log_loss()
        expected_momentum = (-math.log2(0.9) + -math.log2(0.1)) / 2
        assert losses["momentum"] == pytest.approx(expected_momentum)
        assert losses["risk_officer"] == pytest.approx(1.0)  # -log2(0.5) = 1.0 bit (coin flip)
    finally:
        store.close()


def test_empty_store_has_no_role_log_loss(tmp_path):
    store = CouncilTrackRecordStore(tmp_path / "empty.sqlite3")
    try:
        assert store.role_log_loss() == {}
        assert store.resolved_forecast_count() == 0
    finally:
        store.close()
