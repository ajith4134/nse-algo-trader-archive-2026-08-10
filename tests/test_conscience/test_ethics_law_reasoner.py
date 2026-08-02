"""Hermetic test for the ethics/law reasoner (Trunk VII; research/119): a compliant posture yields a
compliant cited report; each SEBI rule breach is detected with its citation. Pure, no I/O.
"""

from __future__ import annotations

from nse_algo_trader.conscience.ethics_law_reasoner import (
    RegulatoryPosture,
    assess_regulatory_compliance,
)


def _compliant_posture(**overrides):
    base = dict(
        max_orders_per_second=5, routes_through_broker=True, carries_algo_id=True,
        intraday_only=True, offered_to_others=False, trading_mode="paper",
    )
    base.update(overrides)
    return RegulatoryPosture(**base)


def test_compliant_posture_is_compliant():
    report = assess_regulatory_compliance(_compliant_posture())
    assert report.compliant and not report.violations
    assert len(report.findings) == 5
    assert all(f.citation for f in report.findings)  # every finding is cited


def test_order_rate_over_ceiling_is_a_violation():
    report = assess_regulatory_compliance(_compliant_posture(max_orders_per_second=12))
    assert not report.compliant and "ORDER_RATE" in report.violations


def test_direct_to_exchange_is_a_violation():
    report = assess_regulatory_compliance(_compliant_posture(routes_through_broker=False))
    assert "BROKER_PRINCIPAL" in report.violations


def test_missing_algo_id_is_a_violation():
    report = assess_regulatory_compliance(_compliant_posture(carries_algo_id=False))
    assert "ALGO_ID" in report.violations


def test_overnight_carry_is_a_violation():
    report = assess_regulatory_compliance(_compliant_posture(intraday_only=False))
    assert "INTRADAY_ONLY" in report.violations


def test_offering_to_others_triggers_ra_registration_violation():
    report = assess_regulatory_compliance(_compliant_posture(offered_to_others=True))
    assert "WHITE_BOX_PERSONAL" in report.violations
    finding = next(f for f in report.findings if f.rule_id == "WHITE_BOX_PERSONAL")
    assert "Research-Analyst" in finding.citation


def test_order_rate_at_ten_is_a_violation_boundary():
    # exactly 10 crosses the white-box threshold (>= 10)
    report = assess_regulatory_compliance(_compliant_posture(max_orders_per_second=10))
    assert "ORDER_RATE" in report.violations
    # 9 is fine
    assert assess_regulatory_compliance(_compliant_posture(max_orders_per_second=9)).compliant
