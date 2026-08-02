"""Per-source reliability scoring for the news sense (Trunk II SENSES S3; research/146). PURE — no I/O.

The user's keystone guardrail: every news source earns a learned reliability so a low-trust source
can't move the entry gate alone, and corroborating independents combine to cross threshold. Reuses
the in-house trust primitives (no new OSS):
  • beta-reputation — XIII `epistemics.misinformation_resistance` formula (good+1)/(good+bad+2),
    here TIER-SEEDED so a source starts where its class deserves and moves as evidence accrues;
  • Stouffer's Z — `sentience.cross_modal_binding` pattern (Σ ppf(conf)/√n) to combine corroboration.

Reliability uses signals available WITHOUT a market outcome: the TIER prior + the FRESHNESS track
(a source that keeps going stale — the Moneycontrol-RSS trap — is down-weighted) + corroboration.
The outcome-driven α/β accrual (did the source's claim resolve true?) is market-gated and QUEUED
(research/146 §Rule K), like the council/society reputation accrual.
"""

from __future__ import annotations

from dataclasses import dataclass

from nse_algo_trader.news_sentiment.news_item_types import NewsSourceTier

# Tier priors as beta pseudo-counts (good0, bad0) — the advisory-until-proven ladder (research/140).
_TIER_PRIORS: dict = {
    NewsSourceTier.EXCHANGE_FILING.value: (9.0, 1.0),   # official filings — primary truth (~0.90)
    NewsSourceTier.PUBLIC_NEWS.value: (3.0, 2.0),       # mainstream news — modest prior (~0.60)
    NewsSourceTier.BROKER_RESEARCH.value: (2.0, 2.0),   # broker/TradingView — neutral (~0.50)
    NewsSourceTier.SOCIAL.value: (1.0, 3.0),            # X/Telegram — untrusted, earns it (~0.25)
}
_DEFAULT_PRIOR = (1.0, 1.0)


@dataclass(frozen=True)
class SourceObservation:
    """What we know about one source WITHOUT market outcomes: volume + freshness + corroboration."""

    source_id: str
    source_name: str
    tier: str
    item_count: int = 0
    fresh_polls: int = 0        # times this source delivered fresh, usable items
    stale_polls: int = 0        # times this source was staleness-rejected (the trap)
    corroborated_items: int = 0  # items independently corroborated by another source


@dataclass(frozen=True)
class SourceReliability:
    source_id: str
    source_name: str
    tier: str
    reliability: float          # beta posterior mean in [0,1]
    evidence_count: int         # fresh+stale+corroborated observations beyond the prior
    item_count: int
    is_provisional: bool        # True when only the tier prior speaks (no evidence yet)
    summary: str = ""


def _tier_prior(tier: str) -> tuple:
    return _TIER_PRIORS.get(tier, _DEFAULT_PRIOR)


def source_reliability(observation: SourceObservation) -> SourceReliability:
    """Tier-seeded beta-reputation folding in the freshness track + corroboration (all outcome-free)."""
    good0, bad0 = _tier_prior(observation.tier)
    good = good0 + observation.fresh_polls + observation.corroborated_items
    bad = bad0 + observation.stale_polls
    reliability = good / (good + bad)
    evidence = observation.fresh_polls + observation.stale_polls + observation.corroborated_items
    provisional = evidence == 0
    note = "tier prior only" if provisional else (
        f"{observation.fresh_polls} fresh / {observation.stale_polls} stale / "
        f"{observation.corroborated_items} corroborated")
    return SourceReliability(
        source_id=observation.source_id,
        source_name=observation.source_name,
        tier=observation.tier,
        reliability=reliability,
        evidence_count=evidence,
        item_count=observation.item_count,
        is_provisional=provisional,
        summary=f"{observation.source_name}: reliability {reliability:.0%} ({note})",
    )


def build_reliability_board(observations) -> tuple:
    """Rank sources by reliability (desc), tie-broken by item volume (desc)."""
    scored = [source_reliability(o) for o in observations]
    scored.sort(key=lambda s: (s.reliability, s.item_count), reverse=True)
    return tuple(scored)


def combine_source_confidences(reliabilities) -> float:
    """Stouffer's Z over independent sources' reliabilities — corroboration raises combined confidence
    above any single source (reuses the cross_modal_binding pattern). A lone source keeps its own."""
    from scipy.stats import norm

    values = [r for r in reliabilities if r is not None]
    if not values:
        return 0.0
    clip = 1e-6
    zs = [norm.ppf(min(1 - clip, max(clip, v))) for v in values]
    combined_z = sum(zs) / (len(zs) ** 0.5)
    return float(norm.cdf(combined_z))
