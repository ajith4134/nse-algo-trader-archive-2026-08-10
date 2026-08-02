"""Hermetic tests for the NSE symbol↔name gazetteer + S7 headline matching (Trunk II SENSES, research/148).

Uses trimmed REAL equity-master rows (Rule F prefers real samples). Confirms name/ticker resolution,
F&O bounding, false-positive guards, and that gazetteer matches now feed the S7 news-event gate so
headlines (not just "SYMBOL:" filings) attribute event risk.
"""

from datetime import datetime, timedelta, timezone

from nse_algo_trader.news_sentiment.news_entry_gate import build_news_event_risk_by_symbol
from nse_algo_trader.news_sentiment.news_item_types import NewsSourceTier, RawNewsItem
from nse_algo_trader.news_sentiment.nse_symbol_gazetteer import (
    build_symbol_gazetteer,
    parse_equity_master_csv,
)

NOW = datetime(2026, 7, 26, 18, 0, 0, tzinfo=timezone.utc)

# Trimmed real EQUITY_L.csv rows (real symbol,name pairs from the live master).
REAL_CSV = (
    "SYMBOL,NAME OF COMPANY, SERIES, DATE OF LISTING\n"
    "INDIGO,InterGlobe Aviation Limited,EQ,10-NOV-2015\n"
    "HINDPETRO,Hindustan Petroleum Corporation Limited,EQ,01-JAN-1996\n"
    "SRF,SRF Limited,EQ,05-JUN-1996\n"
    "20MICRONS,20 Microns Limited,EQ,06-OCT-2008\n"   # not an F&O underlying → excluded by restrict
)
FO_UNDERLYINGS = {"INDIGO", "HINDPETRO", "SRF"}


def _gaz():
    return build_symbol_gazetteer(parse_equity_master_csv(REAL_CSV), restrict_symbols=FO_UNDERLYINGS)


def test_resolves_company_name_to_symbol():
    gaz = _gaz()
    assert gaz.match_symbols("Buy InterGlobe Aviation; target of Rs 6580: Motilal Oswal") == {"INDIGO"}
    assert "HINDPETRO" in gaz.match_symbols("HPCL parent Hindustan Petroleum Corporation gains")


def test_exact_ticker_token_matches():
    gaz = _gaz()
    assert "SRF" in gaz.match_symbols("SRF hits 52-week high on strong Q1")


def test_fo_bounding_excludes_non_underlyings():
    gaz = _gaz()
    # 20MICRONS is in the CSV but NOT an F&O underlying → never matched.
    assert "20MICRONS" not in gaz.tickers
    assert gaz.match_symbols("20 Microns Limited reports results") == set()


def test_no_false_positive_on_unrelated_text():
    gaz = _gaz()
    assert gaz.match_symbols("Nifty ends higher as banks lead the rally today") == set()


def test_gazetteer_feeds_s7_event_risk_from_headlines():
    gaz = _gaz()
    item = RawNewsItem(
        source_id="moneycontrol_stocks_rendered", source_name="MC", tier=NewsSourceTier.PUBLIC_NEWS.value,
        title="Buy InterGlobe Aviation; target of Rs 6580: Motilal Oswal", summary="",
        url="https://x", published_at=NOW - timedelta(hours=1), fetched_at=NOW,
        content_hash="h1")
    reliability = {"moneycontrol_stocks_rendered": 0.67}
    # Without the gazetteer the headline attributes to no symbol; WITH it → INDIGO gets event risk.
    assert build_news_event_risk_by_symbol([item], reliability, NOW) == {}
    with_gaz = build_news_event_risk_by_symbol([item], reliability, NOW, gazetteer=gaz)
    assert "INDIGO" in with_gaz and with_gaz["INDIGO"] > 0
