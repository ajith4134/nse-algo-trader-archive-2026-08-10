"""Tests for the segment-bot surface prober + its always-on injection into the dashboard snapshot."""

from __future__ import annotations

import json

from nse_algo_trader.dashboard.dashboard_feature_surface import MANIFEST_KEYS
from nse_algo_trader.dashboard.dashboard_read_model import _with_segment_bot_surfaces
from nse_algo_trader.dashboard.segment_bot_surface_prober import probe_segment_bot_surfaces

_BOT_KEYS = {"index_option_bot", "stock_option_bot", "cash_intraday_bot",
             "directional_ai_bull", "directional_ai_bear"}
_PROBED_KEYS = _BOT_KEYS | {"option_book_risk", "trade_evidence"}  # + book-risk tile + per-trade evidence card


def test_probe_returns_the_five_features_in_manifest():
    surfaces = probe_segment_bot_surfaces(pod_store_root="/nonexistent-store-xyz")
    assert {s.key for s in surfaces} == _PROBED_KEYS
    assert _PROBED_KEYS <= MANIFEST_KEYS  # every probed key is a manifest key (Rule N)
    for s in surfaces:
        assert s.status in ("active", "gathering", "idle", "blocked", "off", "unknown")
        assert s.title and isinstance(s.metrics, tuple)


def test_bots_are_measured_wired_even_with_no_store():
    # no pod store on disk → no live cycle, but the CODE wiring is still measured (Rule R)
    by_key = {s.key: s for s in probe_segment_bot_surfaces(pod_store_root="/nonexistent-store-xyz")}
    for k in ("index_option_bot", "stock_option_bot", "cash_intraday_bot"):
        metrics = dict(by_key[k].metrics)
        assert metrics["wired → pod"] == "yes"          # measured from pod_runner's AST imports
        assert metrics["directional brain"] == "wired"  # measured from the bot module's AST imports
        assert by_key[k].status in ("idle", "gathering", "active")  # built + wired, never a false "blocked"
        assert metrics["live pod cycle"] == "NOT-INSTRUMENTED"  # honest: no store, no green


def test_prober_overrides_placeholder_rows_in_snapshot_merge():
    # the live service emits a "not yet surfaced" placeholder for a bot key; the prober must WIN
    placeholder = {"key": "index_option_bot", "title": "x", "status": "unknown",
                   "metrics": [], "note": "not yet surfaced"}
    other = {"key": "cost_gate_demo", "title": "y", "status": "active", "metrics": [], "note": ""}
    merged = _with_segment_bot_surfaces([placeholder, other])
    by_key = {s["key"]: s for s in merged}
    assert by_key["index_option_bot"]["note"] != "not yet surfaced"  # replaced by the real probe
    assert by_key["index_option_bot"]["status"] in ("idle", "gathering", "active")
    assert by_key["cost_gate_demo"] == other  # untouched
    assert _BOT_KEYS <= set(by_key)  # all 5 present after merge


def test_snapshot_merge_serializes_to_json():
    merged = _with_segment_bot_surfaces([])
    json.dumps(merged)  # must be JSON-safe for /api/snapshot
    assert _BOT_KEYS <= {s["key"] for s in merged}
