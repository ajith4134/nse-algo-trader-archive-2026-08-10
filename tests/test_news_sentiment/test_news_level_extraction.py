"""Hermetic tests for S2 index support/resistance level extraction (Trunk II SENSES, research/142).

Pure parser, no network/DB needed for the extraction tests (the store test uses a temp SQLite).
Fixtures are TRIMMED REAL headlines from the S1 corpus (Rule F prefers real samples) so the tests
pin the exact precision behaviour verified on live data: nearest-preceding-index attribution,
directional-beats-pivot classification, and rejection of years / counts / point-moves / prices.
"""

from datetime import datetime, timezone

from nse_algo_trader.news_sentiment.news_level_extraction import extract_level_sets
from nse_algo_trader.news_sentiment.news_level_types import LevelKind
from nse_algo_trader.news_sentiment.news_sqlite_store import NewsSqliteStore

NOW = datetime(2026, 7, 26, 12, 0, 0, tzinfo=timezone.utc)


def _one(title, summary=""):
    return extract_level_sets("h1", "et_markets", "ET Markets", title, summary, published_at=NOW)


def _levels(sets, underlying):
    for s in sets:
        if s.underlying == underlying:
            return {(lvl.value, lvl.kind) for lvl in s.levels}
    return set()


def test_explicit_support_and_resistance():
    sets = _one("Nifty ends lower", "Nifty support seen at 24,800 while resistance sits at 25,100.")
    got = _levels(sets, "NIFTY")
    assert (24800.0, LevelKind.SUPPORT.value) in got
    assert (25100.0, LevelKind.RESISTANCE.value) in got


def test_bare_key_level_is_pivot():
    # Real headline: side unstated -> PIVOT, not support/resistance.
    sets = _one("Nifty closes below key 23,800 level on Gulf war ripples")
    assert (23800.0, LevelKind.PIVOT.value) in _levels(sets, "NIFTY")


def test_directional_keyword_beats_pivot_marker():
    # "key support at 55,800" — 'support' must win over the nearby pivot marker 'key'.
    sets = _one("F&O Talk: Nifty looks weak",
                "Bank Nifty faces key support at 55,800 after a break below 23,600.")
    assert (55800.0, LevelKind.SUPPORT.value) in _levels(sets, "BANKNIFTY")


def test_multi_index_nearest_preceding_attribution():
    # The load-bearing precision case from the real corpus: 23,600 -> NIFTY, 55,800 -> BANKNIFTY,
    # NOT both numbers to both indices.
    sets = _one("F&O Talk: Nifty looks weak on chart",
                "Nifty warning of a break below 23,600. Bank Nifty faces key support at 55,800.")
    assert (23600.0, LevelKind.PIVOT.value) in _levels(sets, "NIFTY")
    assert (55800.0, LevelKind.SUPPORT.value) in _levels(sets, "BANKNIFTY")
    # 23,600 must NOT leak onto BANKNIFTY, nor 55,800 onto NIFTY.
    assert 23600.0 not in {v for v, _ in _levels(sets, "BANKNIFTY")}
    assert 55800.0 not in {v for v, _ in _levels(sets, "NIFTY")}


def test_noise_is_rejected():
    # Years, small counts, point-moves and prices are NOT levels (band + keyword-adjacency guards).
    sets = _one("Sensex sinks over 2,000 points in 5 days as Brent above $95",
                "Markets fell for the 6th session in 2026; 363 pts lost, 5 factors to watch.")
    # No NIFTY/BankNifty level should be produced (Sensex is out of scope; the numbers are noise).
    assert all(not s.levels for s in sets) or sets == []


def test_sensex_out_of_scope():
    # Sensex is a BSE index — detected for context but never emitted as a tradeable underlying.
    sets = _one("Sensex hits resistance at 81,000")
    assert sets == []


def test_finnifty_midcpnifty_niftynxt50_covered():
    sets = _one("FinNifty holds support at 23,500; MidcpNifty resistance 12,800; "
                "Nifty Next 50 support at 67,200")
    assert (23500.0, LevelKind.SUPPORT.value) in _levels(sets, "FINNIFTY")
    assert (12800.0, LevelKind.RESISTANCE.value) in _levels(sets, "MIDCPNIFTY")
    assert (67200.0, LevelKind.SUPPORT.value) in _levels(sets, "NIFTYNXT50")


def test_bank_nifty_alias_not_double_counted_as_nifty():
    # "Bank Nifty" must resolve ONLY to BANKNIFTY, not also fire a bare NIFTY at the inner 'nifty'.
    sets = _one("Bank Nifty resistance at 56,000")
    assert {s.underlying for s in sets} == {"BANKNIFTY"}


def test_store_roundtrip_dedup(tmp_path):
    store = NewsSqliteStore(tmp_path / "news.sqlite3")
    try:
        sets = _one("Nifty support at 24,800 and resistance at 25,100")
        new_first = store.save_extracted_levels(sets)
        assert new_first == 2
        # Re-saving the same extraction stores nothing new (PK dedup).
        assert store.save_extracted_levels(sets) == 0
        assert store.level_count() == 2
        loaded = store.load_recent_levels(limit=10)
        assert loaded and loaded[0].underlying == "NIFTY"
        assert {(l.value, l.kind) for l in loaded[0].levels} == {
            (24800.0, LevelKind.SUPPORT.value), (25100.0, LevelKind.RESISTANCE.value)}
    finally:
        store.close()
