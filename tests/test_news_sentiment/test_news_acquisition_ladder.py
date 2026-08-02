"""Hermetic tests for the S4b fast-first acquisition ladder (Trunk II SENSES, research/144).

Both rungs are DI seams — tests inject fake fast/render fetchers (no curl_cffi / no browser). Confirms:
the ladder prefers the FAST rung, falls back to RENDER only when fast yields nothing, records the
winning method, reports a usable FeedPollResult, and one failing site never breaks the poll.
"""

from datetime import datetime, timezone

from nse_algo_trader.news_sentiment.news_acquisition_ladder import (
    FETCH_METHOD_FAST,
    FETCH_METHOD_RENDER,
    LadderNewsAcquisitionSource,
)
from nse_algo_trader.news_sentiment.rendered_news_page_registry import RenderTargetSite

NOW = datetime(2026, 7, 26, 12, 0, 0, tzinfo=timezone.utc)

SITE = RenderTargetSite(
    source_id="moneycontrol_markets_rendered",
    source_name="Moneycontrol — Markets",
    tier="public_news",
    listing_url="https://www.moneycontrol.com/news/business/markets/",
    article_url_substring="/news/business/",
    min_title_words=5,
)

HTML_WITH_HEADLINES = """
<ul><li><a href="/news/business/markets/nifty-support-at-23600-111.html">
  Nifty holds key support at 23,600 as banks lead the recovery today</a></li></ul>
"""


def test_prefers_fast_rung_when_fast_yields_headlines():
    def fast(url):
        return HTML_WITH_HEADLINES

    def render(url):
        raise AssertionError("render must NOT be called when fast succeeds")

    source = LadderNewsAcquisitionSource((SITE,), fast_fetch=fast, render_fetch=render)
    results = source.poll(NOW)
    assert results[0].is_usable
    assert len(results[0].items) == 1
    assert source.last_methods[SITE.source_id] == FETCH_METHOD_FAST


def test_falls_back_to_render_when_fast_empty():
    calls = {"render": 0}

    def fast(url):
        return "<html><body>no articles here</body></html>"  # yields no headlines

    def render(url):
        calls["render"] += 1
        return HTML_WITH_HEADLINES

    source = LadderNewsAcquisitionSource((SITE,), fast_fetch=fast, render_fetch=render)
    results = source.poll(NOW)
    assert calls["render"] == 1                       # render WAS invoked as fallback
    assert results[0].is_usable
    assert source.last_methods[SITE.source_id] == FETCH_METHOD_RENDER


def test_both_rungs_empty_flags_not_silent():
    source = LadderNewsAcquisitionSource(
        (SITE,), fast_fetch=lambda u: "", render_fetch=lambda u: "")
    results = source.poll(NOW)
    assert not results[0].is_usable
    assert "no headlines" in results[0].fetch_error
    assert source.last_methods[SITE.source_id] == "none"


def test_one_failing_site_never_breaks_poll():
    def boom(url):
        raise RuntimeError("network down")

    source = LadderNewsAcquisitionSource((SITE,), fast_fetch=boom, render_fetch=boom)
    results = source.poll(NOW)
    assert len(results) == 1
    assert not results[0].is_usable
    assert "network down" in results[0].fetch_error
