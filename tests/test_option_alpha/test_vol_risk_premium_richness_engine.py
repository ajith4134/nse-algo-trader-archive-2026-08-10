"""Tests for the VRP richness engine — cross-sectional + time-series shrinkage percentile."""

from __future__ import annotations

import pytest

from nse_algo_trader.option_alpha.vol_risk_premium_richness_engine import (
    VolRichnessInput,
    VolRiskPremiumRichnessEngine,
    VrpHistoryStore,
)


def _engine(tmp_path):
    return VolRiskPremiumRichnessEngine(VrpHistoryStore(tmp_path))


def _inputs(vrps: dict[str, float | None], date: str):
    return [VolRichnessInput(u, date, v, 0.15) for u, v in vrps.items()]


def test_richness_in_unit_interval_and_ranks_cross_section(tmp_path):
    eng = _engine(tmp_path)
    out = eng.assess_universe(_inputs({"A": 0.01, "B": 0.20, "C": 0.10, "D": 0.30, "E": 0.05}, "2026-08-04"))
    for s in out.values():
        assert s.richness is None or 0.0 <= s.richness <= 1.0
    # richest VRP ranks highest cross-sectionally (first cycle → cross-section only)
    assert out["D"].richness > out["C"].richness > out["A"].richness
    assert out["D"].richness == pytest.approx(0.9)  # top of 5 names, percentileofscore mean
    assert out["D"].is_rich() and out["A"].is_cheap()


def test_monotone_in_vrp_within_a_cycle(tmp_path):
    eng = _engine(tmp_path)
    out = eng.assess_universe(_inputs({f"N{i}": float(i) / 100 for i in range(10)}, "2026-08-04"))
    ranked = sorted(out.values(), key=lambda s: s.vrp)
    richs = [s.richness for s in ranked]
    assert richs == sorted(richs)  # richness increases with VRP


def test_none_vrp_is_gathering_no_richness(tmp_path):
    eng = _engine(tmp_path)
    # ≥3 priced names so the cross-section is defined; the None-VRP name is excluded from it
    out = eng.assess_universe(_inputs({"A": 0.1, "B": None, "C": 0.2, "D": 0.3, "E": 0.05}, "2026-08-04"))
    assert out["B"].richness is None and out["B"].maturity == "gathering"
    assert out["A"].richness is not None  # priced names still scored cross-sectionally


def test_time_series_percentile_accrues_over_cycles(tmp_path):
    eng = _engine(tmp_path)
    # feed one name rising VRP over many days → its own-history percentile should end high
    for d in range(1, 40):
        eng.assess_universe(_inputs({"A": d / 100.0, "B": 0.5, "C": 0.1}, f"2026-06-{d:02d}"))
    out = eng.assess_universe(_inputs({"A": 0.60, "B": 0.5, "C": 0.1}, "2026-07-01"))
    s = out["A"]
    assert s.n_history >= 30 and s.maturity == "earned"
    assert s.time_series_percentile is not None and s.time_series_percentile >= 0.9  # 0.60 tops its own history


def test_shrinkage_blends_thin_history_toward_cross_section(tmp_path):
    eng = VolRiskPremiumRichnessEngine(VrpHistoryStore(tmp_path), shrinkage_k=20.0)
    out = eng.assess_universe(_inputs({"A": 0.3, "B": 0.2, "C": 0.1}, "2026-08-04"))
    s = out["A"]
    # n=1 → w = 1/(1+20) ≈ 0.048, so richness ≈ mostly the cross-section percentile
    assert s.cross_section_percentile is not None
    assert s.richness == pytest.approx(s.cross_section_percentile, abs=0.06)


def test_persist_and_reload_history(tmp_path):
    store = VrpHistoryStore(tmp_path)
    store.append_and_load("A", "2026-08-01", 0.1, 0.15)
    series = store.append_and_load("A", "2026-08-02", 0.2, 0.16)
    assert series == [0.1, 0.2]  # chronological, persisted across calls


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
