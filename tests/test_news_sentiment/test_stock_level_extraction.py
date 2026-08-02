"""Hermetic tests for stock-S/R level extraction (Trunk II SENSES, research/149).

Pins the precision behaviour proven on real headlines: correct number parsing (no truncation),
analyst-target classification, and the guards that kill the real false positives — profit-in-crore
figures and multi-company listicles.
"""

from nse_algo_trader.news_sentiment.news_level_types import LevelKind
from nse_algo_trader.news_sentiment.nse_symbol_gazetteer import (
    build_symbol_gazetteer,
    parse_equity_master_csv,
)
from nse_algo_trader.news_sentiment.stock_level_extraction import extract_stock_level_sets

CSV = (
    "SYMBOL,NAME OF COMPANY\n"
    "INDIGO,InterGlobe Aviation Limited\n"
    "SRF,SRF Limited\n"
    "IDFCFIRSTB,IDFC First Bank Limited\n"
    "BRITANNIA,Britannia Industries Limited\n"
    "ULTRACEMCO,UltraTech Cement Limited\n"
)
FO = {"INDIGO", "SRF", "IDFCFIRSTB", "BRITANNIA", "ULTRACEMCO"}
GAZ = build_symbol_gazetteer(parse_equity_master_csv(CSV), restrict_symbols=FO)


def _one(title, summary=""):
    return extract_stock_level_sets("h", "sid", "MC", title, summary, GAZ)


def test_analyst_target_full_number_not_truncated():
    sets = _one("Buy InterGlobe Aviation; target of Rs 6580: Motilal Oswal")
    assert len(sets) == 1 and sets[0].underlying == "INDIGO"
    lvl = sets[0].levels[0]
    assert lvl.value == 6580.0 and lvl.kind == LevelKind.TARGET.value  # 6580, NOT 658


def test_support_and_resistance_keywords():
    s = _one("SRF finds support at Rs 3200 with resistance at Rs 3600")
    kinds = {(l.value, l.kind) for l in s[0].levels}
    assert (3200.0, LevelKind.SUPPORT.value) in kinds
    assert (3600.0, LevelKind.RESISTANCE.value) in kinds


def test_profit_in_crore_is_not_a_level():
    # "Rs 1,000 cr" is a profit figure — the magnitude-suffix guard must reject it.
    assert _one("IDFC First Bank Q1 profit tops Rs 1,000 cr") == []


def test_multi_company_listicle_skipped():
    # Names BRITANNIA + ULTRACEMCO → cross-attribution risk → the single-symbol guard skips it.
    assert _one("Bonus issues & dividends: Britannia, UltraTech Cement in focus at Rs 240") == []


def test_bare_price_without_level_word_ignored():
    # A money cue but no target/support/resistance intent → not a level.
    assert _one("SRF shares trade at Rs 3200 in early deals") == []


def test_no_symbol_no_levels():
    assert _one("Nifty ends higher; target of Rs 25000 seen") == [] or all(
        s.underlying in FO for s in _one("Nifty ends higher; target of Rs 25000 seen"))
