"""Hermetic test for the service-level wiring of the VII.14 incident post-mortem (research/113):
`_record_safety_incident` persists through the INJECTED forensic store (temp file, never the real
one), and `_maybe_run_incident_post_mortem` drains unpersisted Referee blocks + refreshes the
cached post-mortem summary the dashboard reads. No LLM, no network.
"""

from __future__ import annotations

from datetime import datetime

from nse_algo_trader.conscience.constitutional_core import (
    ConstitutionalCore,
    ProposedTradingAction,
)
from nse_algo_trader.conscience.constitutional_referee import ConstitutionalReferee
from nse_algo_trader.conscience.incident_post_mortem import (
    INCIDENT_TYPE_OFF_SWITCH_HALT,
)
from nse_algo_trader.dashboard.live_paper_trading_service import LivePaperTradingService


def _service(tmp_path):
    service = LivePaperTradingService(object(), 1_000_000.0)
    service._incident_post_mortem_store_path = tmp_path / "safety_incidents.sqlite3"
    return service


def test_record_safety_incident_persists_through_injected_store(tmp_path):
    service = _service(tmp_path)
    service._record_safety_incident(
        INCIDENT_TYPE_OFF_SWITCH_HALT, "critical", datetime(2026, 7, 26, 15, 15),
        subject="wireheading", detail="critical trip", trace_id="halt-1",
    )
    store = service._ensure_incident_post_mortem_store()
    assert store.incident_count() == 1
    assert store.all_incidents()[0].trace_id == "halt-1"


def test_post_mortem_drains_referee_blocks_and_refreshes_summary(tmp_path):
    service = _service(tmp_path)
    # a real Referee that has really blocked a real out-of-scope (futures) order → a real verdict
    referee = ConstitutionalReferee(ConstitutionalCore())
    futures_order = ProposedTradingAction(
        segment="nse_futures", is_option=False, is_overnight_carry=False,
        option_risk_defined=True, is_atomic_multi_leg=True, routes_through_broker=True,
        has_algo_id=True,
    )
    assert referee.adjudicate_order(futures_order) is False  # blocked (scope A7)
    service._state.constitutional_referee = referee

    service._maybe_run_incident_post_mortem(datetime(2026, 7, 26, 15, 16))
    pm = service._latest_incident_post_mortem
    assert pm is not None and pm.total == 1
    assert "constitution_block" in pm.count_by_type

    # idempotent: re-running the SAME day is a no-op (daily guard); a fresh day re-drains but the
    # UNIQUE index keeps the same block from doubling
    service._incident_post_mortem_last_run_date = None
    service._maybe_run_incident_post_mortem(datetime(2026, 7, 27, 15, 16))
    assert service._latest_incident_post_mortem.total == 1


def test_empty_record_summarizes_clean(tmp_path):
    service = _service(tmp_path)
    service._maybe_run_incident_post_mortem(datetime(2026, 7, 26, 15, 16))
    pm = service._latest_incident_post_mortem
    assert pm is not None and pm.is_clean and pm.total == 0
