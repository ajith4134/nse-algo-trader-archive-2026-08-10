"""Information-diet accounting (§10) — shares + health verdicts."""
from nse_algo_trader.paper_trading.information_diet import (
    read_information_diet, InformationDietHealth, InformationDietSource,
)


def test_gathering_below_min_sample():
    d = read_information_diet(decisions_considered=5, positioning_deferred=0,
                              antibody_vetoed=0, memory_recalibrated=0, shadow_probes=0)
    assert d.health_status == InformationDietHealth.GATHERING


def test_inert_learning_warns():
    # 50 decisions, memory never engaged -> WARNING (learning inert)
    d = read_information_diet(decisions_considered=50, positioning_deferred=3,
                              antibody_vetoed=0, memory_recalibrated=0, shadow_probes=0)
    assert d.health_status == InformationDietHealth.WARNING
    assert d.memory_influence_share == 0.0
    assert "INERT" in d.note


def test_healthy_when_memory_engages():
    d = read_information_diet(decisions_considered=50, positioning_deferred=5,
                              antibody_vetoed=8, memory_recalibrated=6, shadow_probes=1)
    assert d.health_status == InformationDietHealth.HEALTHY
    assert d.memory_influence_share == round(15/50, 3)
    # ADX shapes 100% of decisions by construction
    assert d.influence_share_by_source[InformationDietSource.ADX_REGIME] == 1.0
    assert d.influence_share_by_source[InformationDietSource.MEMORY_ANTIBODY] == round(8/50, 3)


def test_inert_diet_raises_a_monitoring_alert():
    from nse_algo_trader.dashboard.monitoring_alerts import generate_dashboard_alerts
    from nse_algo_trader.dashboard.trading_control_config import TradingControlConfig
    from nse_algo_trader.dashboard.dashboard_read_model import PaperTradingSummary
    diet = read_information_diet(60, 0, 0, 0, 0).__dict__
    alerts = generate_dashboard_alerts(
        TradingControlConfig(), PaperTradingSummary(1e6, 0.0, 0, True), [],
        True, 1, information_diet=diet)
    assert any(a.category == "information-diet" for a in alerts)


def test_over_reliance_on_replay_warns():
    # Memory engages, but the experience base is 75% replay (30/40) -> WARNING.
    d = read_information_diet(
        decisions_considered=50, positioning_deferred=5, antibody_vetoed=8,
        memory_recalibrated=6, shadow_probes=1,
        live_experience_count=10, replay_experience_count=30,
    )
    assert d.health_status == InformationDietHealth.WARNING
    assert d.replay_experience_share == 0.75
    assert "OVER-RELYING on replay" in d.note


def test_live_dominated_experience_base_is_healthy():
    # Same engagement, but 90% live -> no over-reliance, healthy.
    d = read_information_diet(
        decisions_considered=50, positioning_deferred=5, antibody_vetoed=8,
        memory_recalibrated=6, shadow_probes=1,
        live_experience_count=90, replay_experience_count=10,
    )
    assert d.health_status == InformationDietHealth.HEALTHY
    assert d.replay_experience_share == 0.1


def test_replay_share_needs_enough_experiences_to_warn():
    # High replay fraction but a tiny base (< min) must not warn.
    d = read_information_diet(
        decisions_considered=50, positioning_deferred=5, antibody_vetoed=8,
        memory_recalibrated=6, shadow_probes=1,
        live_experience_count=1, replay_experience_count=5,
    )
    assert d.health_status == InformationDietHealth.HEALTHY
