"""Hermetic test for the self-model + attention schema (Trunk VIII; research/128): the self-model
reports the true posture/trust/health; the attention schema reflects what the workspace is attending
to + its distribution + context. Pure, no I/O.
"""

from __future__ import annotations

from nse_algo_trader.sentience.attention_schema import build_attention_schema
from nse_algo_trader.sentience.global_workspace import WorkspaceBroadcast, WorkspaceContribution
from nse_algo_trader.sentience.self_model import build_self_model
from nse_algo_trader.sentience.workspace_attention import AttentionContext


def test_self_model_healthy_when_compliant_calibrated_positive():
    sm = build_self_model(
        calibration_reliable_share=0.8, trusted_mechanism_count=3, distrusted_mechanisms=(),
        constitution_compliant=True, off_switch_engaged=False, goal_aligned=True,
        recent_return_fraction=0.01,
    )
    assert sm.is_healthy and sm.safety_posture == "compliant" and "HEALTHY" in sm.summary


def test_self_model_posture_priority_halted_over_breach():
    sm = build_self_model(0.9, 3, (), constitution_compliant=False, off_switch_engaged=True,
                          goal_aligned=False, recent_return_fraction=0.01)
    assert sm.safety_posture == "halted" and not sm.is_healthy  # off-switch dominates


def test_self_model_goal_drift_and_distrust_reported():
    sm = build_self_model(0.08, 1, ("false_breakout", "atm_option"),
                          constitution_compliant=True, off_switch_engaged=False,
                          goal_aligned=False, recent_return_fraction=-0.009)
    assert sm.safety_posture == "goal-drift" and not sm.is_healthy
    assert "false_breakout" in sm.summary


def test_attention_schema_reflects_dominant_focus_and_distribution():
    b = WorkspaceBroadcast(winner_source="goal_integrity", kind="safety", content="c",
                           salience=0.62, ignited=True)
    ctx = AttentionContext(market_regime="trending", drawdown_fraction=0.06)  # defensive
    contribs = [
        WorkspaceContribution("goal_integrity", "safety", 0.6, 0.8, 0.7, "c"),
        WorkspaceContribution("interp", "risk", 0.5, 0.6, 0.6, "c"),
    ]
    asch = build_attention_schema(b, ctx, contribs)
    assert asch.attending_to == "goal_integrity" and asch.attending_kind == "safety"
    assert asch.attention_by_kind == {"safety": 1, "risk": 1}
    assert asch.is_defensive and asch.context_regime == "trending"


def test_attention_schema_diffuse_when_no_broadcast():
    asch = build_attention_schema(None, AttentionContext(), [])
    assert asch.attending_to is None and "diffuse" in asch.summary
