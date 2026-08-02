"""Hermetic tests for the S4a headline extractor (Trunk II SENSES, research/143).

`extract_headlines_from_html` is the PURE extractor shared by both rungs of the S4b acquisition
ladder (fast static fetch + Chromium render). Fixtures are trimmed real-shape Moneycontrol listing
HTML (Rule F prefers real samples): confirms article anchors are extracted, nav/promo/short links
filtered, relative hrefs resolved, and duplicates collapsed to the longest title.
"""

from datetime import datetime, timezone

from nse_algo_trader.news_sentiment.rendered_news_page_registry import RenderTargetSite
from nse_algo_trader.news_sentiment.rendered_news_page_source import extract_headlines_from_html

NOW = datetime(2026, 7, 26, 12, 0, 0, tzinfo=timezone.utc)

SITE = RenderTargetSite(
    source_id="moneycontrol_markets_rendered",
    source_name="Moneycontrol — Markets (rendered)",
    tier="public_news",
    listing_url="https://www.moneycontrol.com/news/business/markets/",
    article_url_substring="/news/business/",
    min_title_words=5,
)

# Trimmed real-shape listing HTML: 2 real headline anchors, a nav link (filtered by the substring),
# a too-short link (filtered by min_title_words), and a duplicate (collapsed to the longest title).
REAL_SHAPE_HTML = """
<html><body>
<ul>
  <li class="clearfix"><a href="/news/business/markets/chartist-talk-is-23600-key-12345.html">
     Chartist Talk: Is 23,600 likely to remain key battleground for Nifty</a></li>
  <li class="clearfix"><a href="/news/business/ipo/ipo-action-9-public-issues-67890.html">
     IPO Action: 9 public issues worth Rs 11,707-crore to hit Dalal Street</a></li>
  <li><a href="/markets/indian-indices/">Markets</a></li>
  <li><a href="/news/business/markets/short-98765.html">Live blog</a></li>
  <li class="clearfix"><a href="https://www.moneycontrol.com/news/business/markets/chartist-talk-is-23600-key-12345.html">
     Chartist Talk: Is 23,600 likely to remain key battleground for Nifty EXTENDED</a></li>
</ul>
</body></html>
"""


def test_extracts_real_headlines_and_filters_noise():
    items = extract_headlines_from_html(REAL_SHAPE_HTML, SITE, fetched_at=NOW)
    titles = [i.title for i in items]
    assert any("Chartist Talk" in t for t in titles)
    assert any("IPO Action" in t for t in titles)
    assert "Markets" not in titles      # nav link filtered by the article-url substring
    assert "Live blog" not in titles    # too short, filtered by min_title_words


def test_relative_hrefs_resolved_to_absolute():
    items = extract_headlines_from_html(REAL_SHAPE_HTML, SITE, fetched_at=NOW)
    assert all(i.url.startswith("https://www.moneycontrol.com/") for i in items)


def test_duplicate_url_collapses_to_longest_title():
    items = extract_headlines_from_html(REAL_SHAPE_HTML, SITE, fetched_at=NOW)
    chartist = [i for i in items if "Chartist Talk" in i.title]
    assert len(chartist) == 1              # relative + absolute dup collapsed
    assert "EXTENDED" in chartist[0].title  # kept the longer title


def test_empty_html_yields_nothing():
    assert extract_headlines_from_html("<html><body></body></html>", SITE, fetched_at=NOW) == ()
