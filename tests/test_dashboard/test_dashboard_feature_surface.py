"""task #13 (Rule N) — dashboard feature-surface registry + coverage audit. The audit is
the enforcement point: every manifest feature must produce a surface, so a built-but-
invisible feature FAILS here (the mirror of the no-orphan rule)."""

import pytest

from nse_algo_trader.dashboard.dashboard_feature_surface import (
    FEATURE_SURFACE_MANIFEST,
    MANIFEST_KEYS,
    DashboardFeatureSurface,
    FeatureCoverageReport,
)
from nse_algo_trader.dashboard.live_paper_trading_service import LivePaperTradingService


def test_surface_rejects_unknown_status():
    with pytest.raises(ValueError, match="status"):
        DashboardFeatureSurface(key="k", title="t", status="bogus")


def test_coverage_report_placeholders_missing_features():
    partial = FeatureCoverageReport(surfaces=(
        DashboardFeatureSurface(key="champion_challenger", title="Champion", status="active"),
    ))
    assert partial.missing_keys() == MANIFEST_KEYS - {"champion_challenger"}
    rows = partial.rows_in_manifest_order()
    assert [r.key for r in rows] == [k for k, _ in FEATURE_SURFACE_MANIFEST]  # ALL listed
    champ = next(r for r in rows if r.key == "champion_challenger")
    assert champ.status == "active"
    missing = next(r for r in rows if r.key == "multi_broker_sourcing")
    assert missing.status == "unknown" and missing.note == "not yet surfaced"


def test_full_report_has_no_gap():
    full = FeatureCoverageReport(surfaces=tuple(
        DashboardFeatureSurface(key=k, title=t, status="active")
        for k, t in FEATURE_SURFACE_MANIFEST
    ))
    assert full.missing_keys() == frozenset()  # coverage complete


def test_service_build_feature_surfaces_covers_every_manifest_feature():
    """THE AUDIT: the live service must emit a surface for every manifest feature (in
    order). A new feature added without a surface makes this fail."""
    service = LivePaperTradingService(object(), 1_000_000.0)
    surfaces = service._build_feature_surfaces()
    assert [s.key for s in surfaces] == [k for k, _ in FEATURE_SURFACE_MANIFEST]
    assert {s.key for s in surfaces} == MANIFEST_KEYS
    for s in surfaces:
        assert s.status in ("active", "gathering", "idle", "blocked", "off", "unknown")
        assert s.title and isinstance(s.metrics, tuple)


def test_surface_to_json_dict_shape():
    s = DashboardFeatureSurface(key="k", title="T", status="active",
                                metrics=(("a", "1"), ("b", "2")), note="n")
    d = s.to_json_dict()
    assert d == {"key": "k", "title": "T", "status": "active",
                 "metrics": [["a", "1"], ["b", "2"]], "note": "n"}
