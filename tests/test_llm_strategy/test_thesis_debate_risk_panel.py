"""Hermetic test for the debate-as-risk-check panel (Layer 11 slice 2, research/100; Rule J).

Drives the panel with a role-scripted fake LLM + an in-memory memory stub — asserts (a) the
pure risk math, (b) each role prompt carries the REAL grounding facts + its distinct role
instruction, (c) the risk_score is computed from the three role soundness values, and (d) a
pool exhaustion surfaces as a non-generated assessment (never a crash). No network, no real LLM.
"""

from __future__ import annotations

import pytest

from nse_algo_trader.llm_strategy.strategy_llm_client import LlmRateLimitError
from nse_algo_trader.llm_strategy.thesis_debate_risk_panel import (
    ROLE_VERDICT_SCHEMA,
    ThesisDebateRiskPanel,
    TradeThesis,
    compute_adverse_conviction,
    compute_disagreement_score,
    compute_risk_score,
)
from tests.test_llm_strategy.llm_strategy_test_doubles import (
    InMemoryExperienceMemoryStub,
    RoleScriptedFakeLlmClient,
)


def _verdict(soundness):
    return {"soundness": soundness, "key_points": ["p"], "main_risk": "r"}


def _panel(output_by_purpose=None, default_output=None, fail_with=None):
    client = RoleScriptedFakeLlmClient(
        output_by_purpose=output_by_purpose or {},
        default_output=default_output or _verdict(0.5),
        fail_with=fail_with,
    )
    panel = ThesisDebateRiskPanel(client, InMemoryExperienceMemoryStub())
    return panel, client


# ----- pure risk math -----


def test_disagreement_is_the_spread_and_adverse_is_one_minus_mean():
    values = [0.8, 0.2, 0.5]
    assert compute_disagreement_score(values) == pytest.approx(0.6)
    assert compute_adverse_conviction(values) == pytest.approx(0.5)  # 1 - 0.5 mean


def test_risk_score_blends_disagreement_and_adverse_conviction():
    # default 0.5/0.5 blend of disagreement 0.6 and adverse 0.5 → 0.55
    assert compute_risk_score(0.6, 0.5) == pytest.approx(0.55)


def test_risk_math_handles_empty_and_clamps():
    assert compute_disagreement_score([]) == 0.0
    assert compute_adverse_conviction([]) == 0.0
    assert compute_risk_score(1.0, 1.0) == 1.0  # blended 1.0, stays in range
    assert compute_risk_score(-5.0, -5.0) == 0.0  # clamped up to 0


# ----- the debate -----


def _thesis():
    return TradeThesis(
        mechanism_name="opening_range_breakout", strategy_tag="orb",
        claim="Keep trading ORB — the edge is real.", stated_win_probability=0.62,
    )


def test_each_role_prompt_carries_grounding_and_its_distinct_role():
    panel, client = _panel()
    panel.debate(_thesis())

    assert [r.purpose for r in client.captured_requests] == [
        "thesis_debate_bull", "thesis_debate_bear", "thesis_debate_risk_officer",
    ]
    for request in client.captured_requests:
        # real memory facts about the mechanism are in every role's prompt
        assert "opening_range_breakout" in request.user_prompt
        assert "predicted win-rate 62% vs actual 41%" in request.user_prompt
    # the three role system instructions are distinct
    systems = [r.system_instruction for r in client.captured_requests]
    assert "BULL" in systems[0] and "BEAR" in systems[1] and "RISK OFFICER" in systems[2]


def test_risk_score_is_computed_from_the_three_role_soundnesses():
    panel, _ = _panel(output_by_purpose={
        "thesis_debate_bull": _verdict(0.9),
        "thesis_debate_bear": _verdict(0.2),
        "thesis_debate_risk_officer": _verdict(0.3),
    })
    assessment = panel.debate(_thesis())

    assert assessment.generated is True
    assert len(assessment.verdicts) == 3
    assert assessment.served_by == "fake-provider:fake-model"  # de-duped across roles
    assert assessment.disagreement_score == pytest.approx(0.7)  # 0.9 - 0.2
    assert assessment.adverse_conviction == pytest.approx(1 - (0.9 + 0.2 + 0.3) / 3)
    # 0.5*0.7 + 0.5*0.5333 = 0.6167
    assert assessment.risk_score == pytest.approx(0.6167, abs=1e-3)


def test_soundness_is_clamped_to_unit_interval():
    panel, _ = _panel(output_by_purpose={
        "thesis_debate_bull": _verdict(1.5),      # → 1.0
        "thesis_debate_bear": _verdict(-0.3),     # → 0.0
        "thesis_debate_risk_officer": _verdict(0.4),
    })
    assessment = panel.debate(_thesis())
    soundness = [v.soundness for v in assessment.verdicts]
    assert soundness == [1.0, 0.0, 0.4]
    assert assessment.disagreement_score == pytest.approx(1.0)


def test_pool_exhaustion_yields_a_non_generated_assessment():
    panel, _ = _panel(fail_with=LlmRateLimitError("fake", "whole pool exhausted"))
    assessment = panel.debate(_thesis())
    assert assessment.generated is False
    assert "bull role" in assessment.note  # first role that hit the exhausted pool
    # grounding facts are retained for transparency even on the blocked path
    assert any("opening_range_breakout" in f for f in assessment.grounding_facts)


def test_debate_active_theses_derive_from_the_calibration_board():
    panel, _ = _panel()
    assessments = panel.debate_active_theses(limit=3)
    assert len(assessments) == 1  # the stub board has one mechanism
    thesis = assessments[0].thesis
    assert thesis.mechanism_name == "opening_range_breakout"
    assert "opening_range_breakout" in thesis.claim


def test_role_verdict_schema_is_forced_on_every_request():
    panel, client = _panel()
    panel.debate(_thesis())
    for request in client.captured_requests:
        assert request.response_json_schema is ROLE_VERDICT_SCHEMA
    assert ROLE_VERDICT_SCHEMA["required"] == ["soundness", "key_points", "main_risk"]
    assert ROLE_VERDICT_SCHEMA["additionalProperties"] is False
