"""Hermetic tests for S3 per-source reliability scoring (Trunk II SENSES, research/146).

Pure scorer — no I/O. Confirms the tier-trust ladder (filings > news > social), the freshness track
(stale penalises, fresh boosts), provisional flagging when only the prior speaks, board ranking, and
Stouffer corroboration raising combined confidence above any single source.
"""

from nse_algo_trader.news_sentiment.news_item_types import NewsSourceTier
from nse_algo_trader.news_sentiment.news_source_reliability import (
    SourceObservation,
    build_reliability_board,
    combine_source_confidences,
    source_reliability,
)


def _obs(tier, **kw):
    return SourceObservation(source_id=kw.get("sid", "s"), source_name=kw.get("name", "S"),
                             tier=tier, item_count=kw.get("n", 0),
                             fresh_polls=kw.get("fresh", 0), stale_polls=kw.get("stale", 0),
                             corroborated_items=kw.get("corr", 0))


def test_tier_prior_ladder_filings_beats_news_beats_social():
    filing = source_reliability(_obs(NewsSourceTier.EXCHANGE_FILING.value)).reliability
    news = source_reliability(_obs(NewsSourceTier.PUBLIC_NEWS.value)).reliability
    social = source_reliability(_obs(NewsSourceTier.SOCIAL.value)).reliability
    assert filing > news > social
    assert filing >= 0.85 and social <= 0.35   # official trusted, social untrusted-until-proven


def test_stale_penalises_and_fresh_boosts():
    base = source_reliability(_obs(NewsSourceTier.PUBLIC_NEWS.value)).reliability
    stale = source_reliability(_obs(NewsSourceTier.PUBLIC_NEWS.value, stale=5)).reliability
    fresh = source_reliability(_obs(NewsSourceTier.PUBLIC_NEWS.value, fresh=5)).reliability
    assert stale < base < fresh


def test_provisional_when_no_evidence():
    r = source_reliability(_obs(NewsSourceTier.PUBLIC_NEWS.value))
    assert r.is_provisional
    r2 = source_reliability(_obs(NewsSourceTier.PUBLIC_NEWS.value, fresh=1))
    assert not r2.is_provisional


def test_board_ranks_by_reliability_then_volume():
    obs = [
        _obs(NewsSourceTier.PUBLIC_NEWS.value, sid="mc", name="MC", n=100),
        _obs(NewsSourceTier.EXCHANGE_FILING.value, sid="nse", name="NSE", n=20),
        _obs(NewsSourceTier.SOCIAL.value, sid="tg", name="TG", n=5),
    ]
    board = build_reliability_board(obs)
    assert [b.source_id for b in board] == ["nse", "mc", "tg"]  # filings top despite lower volume


def test_stouffer_corroboration_beats_single_source():
    single = combine_source_confidences([0.6])
    corroborated = combine_source_confidences([0.6, 0.6, 0.6])
    assert corroborated > single          # independent corroboration raises confidence
    assert combine_source_confidences([]) == 0.0
