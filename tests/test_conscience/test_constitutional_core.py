"""Hermetic test for the constitutional core (Trunk VII.1 CONSCIENCE; research/109): each
inviolable article passes its compliant case and BLOCKS its violation with the right article id,
the verdict serialises + traces deterministically, and the real control-config posture is
compliant. Pure, no I/O.
"""

from __future__ import annotations

import dataclasses

from nse_algo_trader.conscience.constitutional_core import (
    CONSTITUTION,
    ConstitutionalCore,
    ProposedTradingAction,
    SystemPosture,
    audit_control_config_posture,
)
from nse_algo_trader.dashboard.trading_control_config import TradingControlConfig

_CORE = ConstitutionalCore()


def _compliant_action():
    return ProposedTradingAction(
        segment="nse_index_options", is_live=True, is_option=True, is_overnight_carry=False,
        option_risk_defined=True, is_atomic_multi_leg=True, routes_through_broker=True,
        has_algo_id=True, orders_this_second=3, per_trade_risk_fraction=0.008,
        max_risk_per_trade_fraction=0.01,
    )


def _compliant_posture():
    return SystemPosture(
        intraday_only=True, personal_use_only=True, max_risk_per_trade_fraction=0.01,
        min_capital_per_trade=10_000.0, max_capital_per_trade=250_000.0,
        enabled_segments=("nse_cash_equity", "nse_index_options"), secrets_committed=False,
    )


def test_a_fully_compliant_action_is_permitted():
    verdict = _CORE.review_action(_compliant_action())
    assert verdict.permitted is True
    assert verdict.hard_violations == () and verdict.soft_warnings == ()
    assert verdict.detail == "compliant with the constitution"


def test_each_action_violation_is_blocked_by_the_right_article():
    cases = {
        "A1": {"is_overnight_carry": True},
        "A2": {"orders_this_second": 11},
        "A3": {"is_option": True, "option_risk_defined": False},
        "A4": {"is_atomic_multi_leg": False},
        "A5": {"routes_through_broker": False},
        "A6": {"is_live": True, "has_algo_id": False},
        "A7": {"segment": "nse_futures"},               # out of phase-1 scope
        "A8": {"per_trade_risk_fraction": 0.05, "max_risk_per_trade_fraction": 0.01},
    }
    for article_id, override in cases.items():
        action = dataclasses.replace(_compliant_action(), **override)
        verdict = _CORE.review_action(action)
        assert verdict.permitted is False, f"{article_id} should block"
        assert article_id in {v.article_id for v in verdict.hard_violations}, article_id


def test_posture_violations_and_soft_warning():
    # over-risk config → hard A10; a naked personal-use flip → soft A14 (warns, still permitted)
    over_risk = dataclasses.replace(_compliant_posture(), max_risk_per_trade_fraction=0.20)
    v1 = _CORE.audit_system_posture(over_risk)
    assert v1.permitted is False and "A10" in {v.article_id for v in v1.hard_violations}

    not_personal = dataclasses.replace(_compliant_posture(), personal_use_only=False)
    v2 = _CORE.audit_system_posture(not_personal)
    assert v2.permitted is True  # A14 is SOFT — a warning, not a block
    assert "A14" in {v.article_id for v in v2.soft_warnings}

    bad_segment = dataclasses.replace(_compliant_posture(), enabled_segments=("nse_futures",))
    v3 = _CORE.audit_system_posture(bad_segment)
    assert "A12" in {v.article_id for v in v3.hard_violations}


def test_verdict_serialises_and_traces_deterministically():
    a = _CORE.review_action(_compliant_action())
    b = _CORE.review_action(_compliant_action())
    assert a.trace_id == b.trace_id  # same subject → same trace
    j = a.to_json_dict()
    assert j["permitted"] is True and j["trace_id"] == a.trace_id and "hard_violations" in j


def test_the_real_default_control_config_is_constitutionally_compliant():
    verdict = audit_control_config_posture(TradingControlConfig())
    assert verdict.permitted is True, verdict.detail


def test_constitution_has_hard_and_soft_articles():
    severities = {a.severity.value for a in CONSTITUTION}
    assert "hard" in severities and "soft" in severities
    assert len(CONSTITUTION) >= 12
