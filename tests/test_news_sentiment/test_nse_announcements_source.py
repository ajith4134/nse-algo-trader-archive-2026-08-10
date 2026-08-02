"""Hermetic tests for S4c NSE corporate-announcement filings (Trunk II SENSES, research/145).

The NSE fetch sits behind a `fetch_json` DI seam — tests inject a fake returning canned REAL-SHAPE
records (captured from the live endpoint, Rule F prefers real samples), so parsing + IST→UTC + poll
logic verify with no network. Confirms: title 'SYMBOL: subject', EXCHANGE_FILING tier, IST→UTC
timestamp, PDF url, records missing symbol/subject skipped, and an empty fetch flagged not silent.
"""

from datetime import datetime, timezone

from nse_algo_trader.news_sentiment.news_item_types import NewsSourceTier
from nse_algo_trader.news_sentiment.nse_announcements_source import (
    NseAnnouncementsSource,
    parse_announcement_records,
)

NOW = datetime(2026, 7, 26, 18, 0, 0, tzinfo=timezone.utc)

# Real-shape records captured from the live NSE endpoint (research/145).
REAL_SHAPE_RECORDS = [
    {
        "symbol": "SMCGLOBAL", "sm_name": "SMC Global Securities Limited",
        "desc": "Outcome of Board Meeting",
        "attchmntText": "Smc Global Securities Limited has submitted the financial results for Jun 30, 2026.",
        "attchmntFile": "https://nsearchives.nseindia.com/corporate/SMCGLOBAL_26072026_Outcome.pdf",
        "an_dt": "26-Jul-2026 21:31:57", "sort_date": "2026-07-26 21:31:57", "sm_isin": "INE103C01036",
    },
    {
        "symbol": "LALPATHLAB", "sm_name": "Dr. Lal PathLabs Limited", "desc": "Change in Director(s)",
        "attchmntText": "Change in directorate.",
        "attchmntFile": "", "sort_date": "2026-07-26 20:10:00",
    },
    {"symbol": "", "desc": "Missing symbol — must be skipped", "sort_date": "2026-07-26 19:00:00"},
]


def test_parses_symbol_subject_tier_and_ist_to_utc():
    items = parse_announcement_records(REAL_SHAPE_RECORDS, "nse_announcements_equities",
                                       "NSE corporate announcements (equities)", fetched_at=NOW)
    assert len(items) == 2  # the third (no symbol) skipped
    smc = items[0]
    assert smc.title == "SMCGLOBAL: Outcome of Board Meeting"
    assert smc.tier == NewsSourceTier.EXCHANGE_FILING.value
    assert smc.url.endswith("SMCGLOBAL_26072026_Outcome.pdf")
    # 21:31:57 IST → 16:01:57 UTC (IST = UTC+5:30).
    assert smc.published_at == datetime(2026, 7, 26, 16, 1, 57, tzinfo=timezone.utc)


def test_missing_attachment_falls_back_to_announcements_page_url():
    items = parse_announcement_records(REAL_SHAPE_RECORDS, "sid", "name", fetched_at=NOW)
    lal = [i for i in items if i.title.startswith("LALPATHLAB")][0]
    assert lal.url.startswith("https://www.nseindia.com/companies-listing/")


def test_poll_uses_fetch_seam_and_reports_freshness():
    def fake_fetch(index):
        return REAL_SHAPE_RECORDS

    source = NseAnnouncementsSource(indices=("equities",), fetch_json=fake_fetch)
    results = source.poll(NOW)
    assert len(results) == 1
    assert results[0].is_usable
    assert len(results[0].items) == 2
    assert results[0].source_id == "nse_announcements_equities"


def test_empty_fetch_flagged_not_silent():
    source = NseAnnouncementsSource(indices=("equities",), fetch_json=lambda index: [])
    results = source.poll(NOW)
    assert not results[0].is_usable
    assert "no announcement records" in results[0].fetch_error


def test_fetch_error_on_one_index_never_breaks_poll():
    def boom(index):
        raise RuntimeError("nse handshake failed")

    source = NseAnnouncementsSource(indices=("equities",), fetch_json=boom)
    results = source.poll(NOW)
    assert not results[0].is_usable
    assert "nse handshake failed" in results[0].fetch_error
