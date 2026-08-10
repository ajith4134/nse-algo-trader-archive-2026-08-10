"""L4 — per-family promotion ladder gated by validation (research/170). Hermetic; SQLite in tmp_path."""

from nse_algo_trader.paper_trading.strategy_family_promotion_registry import (
    PromotionStage,
    StrategyFamilyPromotionRegistry,
)


def _reg(tmp_path):
    return StrategyFamilyPromotionRegistry(db_file_path=tmp_path / "fam.sqlite3")


def test_new_family_defaults_to_paper_and_may_trade_paper_not_live(tmp_path):
    r = _reg(tmp_path)
    r.ensure_family("orb_cash")
    assert r.stage_of("orb_cash") is PromotionStage.PAPER
    assert r.may_trade_paper("orb_cash")
    assert not r.may_trade_live("orb_cash")


def test_no_edge_stays_in_paper(tmp_path):
    r = _reg(tmp_path)
    stage = r.record_evaluation("orb_cash", edge_promoted=False, deflated_sharpe=0.3,
                                trades_evaluated=40, regime_coverage_met=True)
    assert stage is PromotionStage.PAPER


def test_edge_plus_coverage_promotes_paper_to_shadow(tmp_path):
    r = _reg(tmp_path)
    stage = r.record_evaluation("mean_reversion", edge_promoted=True, deflated_sharpe=0.97,
                                trades_evaluated=60, regime_coverage_met=True)
    assert stage is PromotionStage.SHADOW


def test_edge_without_regime_coverage_holds_in_paper(tmp_path):
    r = _reg(tmp_path)
    stage = r.record_evaluation("orb_cash", edge_promoted=True, deflated_sharpe=0.97,
                                trades_evaluated=60, regime_coverage_met=False)
    assert stage is PromotionStage.PAPER  # earned but no coverage → not yet


def test_shadow_needs_human_go_live_for_reduced_live(tmp_path):
    r = _reg(tmp_path)
    r.record_evaluation("cs", True, 0.97, 60, True)  # → shadow
    # still no manual flag → stays shadow
    assert r.record_evaluation("cs", True, 0.97, 80, True) is PromotionStage.SHADOW
    # manual flag → reduced live
    assert r.record_evaluation("cs", True, 0.97, 90, True, manual_go_live_approved=True) is (
        PromotionStage.REDUCED_LIVE
    )
    assert r.may_trade_live("cs")


def test_reduced_live_advances_to_full_live_with_manual(tmp_path):
    r = _reg(tmp_path)
    for _ in range(1):
        r.record_evaluation("cs", True, 0.97, 60, True)  # shadow
    r.record_evaluation("cs", True, 0.97, 90, True, manual_go_live_approved=True)  # reduced
    assert r.record_evaluation("cs", True, 0.98, 120, True, manual_go_live_approved=True) is (
        PromotionStage.FULL_LIVE
    )


def test_edge_decay_demotes_live_family_to_shadow(tmp_path):
    r = _reg(tmp_path)
    r.record_evaluation("cs", True, 0.97, 60, True)  # shadow
    r.record_evaluation("cs", True, 0.97, 90, True, manual_go_live_approved=True)  # reduced_live
    demoted = r.record_evaluation("cs", edge_promoted=False, deflated_sharpe=0.4,
                                  trades_evaluated=100, regime_coverage_met=True)
    assert demoted is PromotionStage.SHADOW  # antibody for whole families
    assert not r.may_trade_live("cs")


def test_halt_blocks_all_trading(tmp_path):
    r = _reg(tmp_path)
    r.halt("orb_cash", "operator stop")
    assert r.stage_of("orb_cash") is PromotionStage.HALTED
    assert not r.may_trade_paper("orb_cash")
    # a halted family never advances
    assert r.record_evaluation("orb_cash", True, 0.99, 200, True, True) is PromotionStage.HALTED


def test_snapshot_reports_families_and_stage_counts(tmp_path):
    r = _reg(tmp_path)
    r.record_evaluation("orb_cash", True, 0.97, 60, True)   # shadow
    r.record_evaluation("zero_dte", False, 0.2, 40, True)   # paper
    snap = r.snapshot()
    stages = {f["family"]: f["stage"] for f in snap["families"]}
    assert stages["orb_cash"] == "shadow" and stages["zero_dte"] == "paper"
    assert snap["stage_counts"].get("shadow") == 1


def test_persists_across_instances(tmp_path):
    r = _reg(tmp_path)
    r.record_evaluation("cs", True, 0.97, 60, True)  # shadow
    r.close()
    r2 = StrategyFamilyPromotionRegistry(db_file_path=tmp_path / "fam.sqlite3")
    assert r2.stage_of("cs") is PromotionStage.SHADOW
