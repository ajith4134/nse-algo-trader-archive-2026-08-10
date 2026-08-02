"""Hermetic test for workspace attention (Trunk VIII; research/126): selective attention weights by
regime, state-dependent attention boosts safety/risk when the system is hurting and damps
opportunity; critical safety is preserved. Pure, no I/O.
"""

from __future__ import annotations

from nse_algo_trader.sentience.global_workspace import WorkspaceContribution, salience_score
from nse_algo_trader.sentience.workspace_attention import (
    AttentionContext,
    apply_attention,
    attention_weight,
)


def _c(kind, urgency=0.6, relevance=0.6, confidence=0.6, critical=False):
    return WorkspaceContribution(
        source=kind, kind=kind, urgency=urgency, relevance=relevance,
        confidence=confidence, content="c", is_critical=critical,
    )


def test_defensive_state_boosts_risk_attention():
    calm = AttentionContext(market_regime="trending")
    hurt = AttentionContext(market_regime="trending", drawdown_fraction=0.06)
    risk = _c("risk")
    assert attention_weight(risk, hurt) > attention_weight(risk, calm)
    # the boosted risk contribution has higher salience after attention
    calm_c = apply_attention([risk], calm)[0]
    hurt_c = apply_attention([risk], hurt)[0]
    assert salience_score(hurt_c) >= salience_score(calm_c)


def test_indecisive_regime_damps_opportunity():
    trend = AttentionContext(market_regime="trending")
    chop = AttentionContext(market_regime="indecisive")
    opp = _c("opportunity")
    assert attention_weight(opp, chop) < attention_weight(opp, trend)


def test_defensive_state_damps_opportunity_further():
    ctx = AttentionContext(market_regime="trending", off_switch_engaged=True)
    assert ctx.is_defensive
    assert attention_weight(_c("opportunity"), ctx) < 1.0


def test_safety_always_attended_and_critical_preserved():
    calm = AttentionContext(market_regime="range")
    assert attention_weight(_c("safety"), calm) >= 1.0
    crit = _c("safety", urgency=0.1, relevance=0.1, critical=True)
    out = apply_attention([crit], calm)[0]
    assert out.is_critical and salience_score(out) == 1.0  # critical still wins


def test_weights_and_values_are_clamped():
    ctx = AttentionContext(market_regime="trending", drawdown_fraction=0.5, consecutive_losses=9)
    for kind in ("safety", "risk", "opportunity", "info"):
        w = attention_weight(_c(kind), ctx)
        assert 0.3 <= w <= 1.5
    out = apply_attention([_c("risk", urgency=0.95, relevance=0.95)], ctx)[0]
    assert 0.0 <= out.urgency <= 1.0 and 0.0 <= out.relevance <= 1.0


def test_is_defensive_triggers():
    assert AttentionContext(consecutive_losses=2).is_defensive
    assert AttentionContext(drawdown_fraction=0.02).is_defensive
    assert AttentionContext(off_switch_engaged=True).is_defensive
    assert not AttentionContext(market_regime="trending").is_defensive
