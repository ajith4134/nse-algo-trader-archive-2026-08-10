"""Rule-F verification for Trunk VII.14 — the incident post-mortem forensic store (research/113).

Uses the REAL safety organs (no fakes): the real `ConstitutionalCore`/`ConstitutionalReferee`
produce a real HARD verdict by adjudicating a real out-of-scope (futures) order, and the real
`CorrigibilitySwitch` produces a real halt. Those real incidents are persisted to a REAL on-disk
SQLite forensic store, which is then reopened from disk (a simulated restart) to prove durability,
and the post-mortem summariser reduces the real record to a reviewable summary.

Also confirms the LIVE service composes the forensic store + a normally-CLEAN real record (in a
correctly-behaving system the referee blocks nothing, the tripwires are clear, and the posture is
compliant — an empty forensic record is the honest real-system state).

Run:  python scripts/verify_incident_post_mortem_realdata.py
"""

from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path

from nse_algo_trader.conscience.constitutional_core import (
    ConstitutionalCore,
    ProposedTradingAction,
)
from nse_algo_trader.conscience.constitutional_referee import ConstitutionalReferee
from nse_algo_trader.conscience.corrigibility_switch import CorrigibilitySwitch
from nse_algo_trader.conscience.incident_post_mortem import (
    INCIDENT_TYPE_CONSTITUTION_BLOCK,
    INCIDENT_TYPE_OFF_SWITCH_HALT,
    SafetyIncident,
    summarize_incident_post_mortem,
)
from nse_algo_trader.conscience.incident_post_mortem_store import IncidentPostMortemStore
from nse_algo_trader.dashboard.live_paper_trading_service import LivePaperTradingService


def main() -> int:
    now = datetime(2026, 7, 26, 15, 15)

    # 1) A REAL constitutional block → a real HARD verdict (out-of-scope futures order, article A7).
    core = ConstitutionalCore()
    referee = ConstitutionalReferee(core)
    futures_order = ProposedTradingAction(
        segment="nse_futures", is_option=False, is_overnight_carry=False,
        option_risk_defined=True, is_atomic_multi_leg=True, routes_through_broker=True,
        has_algo_id=True,
    )
    permitted = referee.adjudicate_order(futures_order)
    assert permitted is False, "a real out-of-scope order should be blocked"
    block_verdict = referee.recent_blocks[-1]
    print(f"Real Referee block: scope={block_verdict.scope!r} permitted={block_verdict.permitted} "
          f"trace_id={block_verdict.trace_id[:12]}…")

    # 2) A REAL off-switch halt.
    switch = CorrigibilitySwitch()
    switch.halt("verify: emergency stop")
    assert switch.is_halted and switch.halt_count == 1
    print(f"Real off-switch halt: is_halted={switch.is_halted} reason={switch.reason!r}")

    # 3) Persist the REAL incidents to a REAL on-disk SQLite forensic store.
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "safety_incidents.sqlite3"
        store = IncidentPostMortemStore(db)
        store.record_incident(SafetyIncident(
            incident_type=INCIDENT_TYPE_CONSTITUTION_BLOCK, severity="hard",
            occurred_at=now.isoformat(), subject=block_verdict.scope,
            detail=block_verdict.detail, trace_id=block_verdict.trace_id,
        ))
        store.record_incident(SafetyIncident(
            incident_type=INCIDENT_TYPE_OFF_SWITCH_HALT, severity="critical",
            occurred_at=now.isoformat(), subject="operator",
            detail=switch.reason, trace_id="verify-halt-1",
        ))
        # idempotency on the same (type, trace_id)
        wrote_again = store.record_incident(SafetyIncident(
            incident_type=INCIDENT_TYPE_CONSTITUTION_BLOCK, severity="hard",
            occurred_at=now.isoformat(), subject=block_verdict.scope,
            detail=block_verdict.detail, trace_id=block_verdict.trace_id,
        ))
        assert wrote_again is False, "same incident must not double-log"
        store.close()

        # 4) Reopen from disk (simulated restart) → durability.
        reopened = IncidentPostMortemStore(db)
        incidents = reopened.all_incidents()
        pm = summarize_incident_post_mortem(incidents)
        reopened.close()

    assert pm.total == 2, f"expected 2 durable incidents, got {pm.total}"
    assert pm.critical_count == 2
    print(f"\nForensic record survived restart: total={pm.total} critical={pm.critical_count}")
    print(f"  by type: {pm.count_by_type}")
    print(f"  headline: {pm.headline}")

    # 5) The LIVE service composes the forensic store; the real record starts CLEAN.
    service = LivePaperTradingService(object(), 1_000_000.0)
    with tempfile.TemporaryDirectory() as tmp:
        service._incident_post_mortem_store_path = Path(tmp) / "safety_incidents.sqlite3"
        service._maybe_run_incident_post_mortem(now)
        clean = service._latest_incident_post_mortem
    assert clean is not None and clean.is_clean
    print(f"\nLive service forensic record (clean system): {clean.headline}")

    print("\nRESULT: PASS — real safety incidents persist to a durable forensic record, survive a "
          "restart, summarise into a post-mortem, and the live service starts with a clean record.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
