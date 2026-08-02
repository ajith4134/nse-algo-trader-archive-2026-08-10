"""Market breadth + cross-market context (Trunk II SENSES; research/137).

A market-INTERNALS sense over the whole cash universe: how broadly is the market moving?
- CORRELATION / BREADTH — advancers vs decliners, A-D ratio, % advancing, and cross-sectional return
  DISPERSION (stocks moving together vs apart). Broad participation vs a narrow move.
- CROSS-MARKET CONTEXT — is the aggregate (median) market move CONFIRMED by breadth, or a narrow
  divergence (headline up but most stocks down = a fragile few-leaders rally)?
Sourcing (research/137): A-D / McClellan are standard formulas; no Python lib does cross-sectional
breadth (ta-lib/pandas-ta are single-series) — built from formula. PURE (no I/O).
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import fmean, pstdev


@dataclass(frozen=True)
class SymbolReturn:
    symbol: str
    return_fraction: float


@dataclass(frozen=True)
class MarketBreadthReport:
    total: int
    advancers: int
    decliners: int
    breadth_pct: float          # % of symbols advancing
    advance_decline_ratio: float
    dispersion: float           # cross-sectional stdev of returns (co-movement: low = correlated)
    is_broad: bool              # broad participation (breadth strongly one-sided)
    summary: str = ""


@dataclass(frozen=True)
class CrossMarketContext:
    market_return: float        # MEAN symbol return — the equal-weighted "market" move (index proxy)
    breadth_pct: float
    confirms: bool              # breadth agrees with the sign of the market move
    divergence: bool            # market move NOT confirmed by breadth (narrow rally / hidden weakness)
    summary: str = ""


def compute_market_breadth(
    returns: list, broad_threshold: float = 0.60
) -> MarketBreadthReport:
    """Market breadth over per-symbol daily returns. `is_broad` when the advancing/declining split is
    strongly one-sided (≥ broad_threshold either way)."""
    usable = [r for r in returns if r.return_fraction == r.return_fraction]  # drop NaN
    total = len(usable)
    if total == 0:
        return MarketBreadthReport(0, 0, 0, 0.0, 0.0, 0.0, False, "no symbols to measure breadth")
    advancers = sum(1 for r in usable if r.return_fraction > 0)
    decliners = sum(1 for r in usable if r.return_fraction < 0)
    breadth_pct = advancers / total
    ad_ratio = advancers / decliners if decliners else float(advancers)
    dispersion = pstdev([r.return_fraction for r in usable]) if total > 1 else 0.0
    is_broad = breadth_pct >= broad_threshold or breadth_pct <= (1 - broad_threshold)
    summary = (
        f"{advancers} advancing / {decliners} declining of {total} ({breadth_pct:.0%} advancing, "
        f"A/D {ad_ratio:.2f}); dispersion {dispersion:.2%} — "
        + ("BROAD participation" if is_broad else "narrow / mixed")
    )
    return MarketBreadthReport(
        total=total, advancers=advancers, decliners=decliners, breadth_pct=breadth_pct,
        advance_decline_ratio=ad_ratio, dispersion=dispersion, is_broad=is_broad, summary=summary,
    )


def assess_cross_market_context(returns: list) -> CrossMarketContext:
    """Is the aggregate (equal-weighted MEAN) market move confirmed by breadth? A move up on weak
    breadth (a few big winners carrying the index while most stocks fall — a narrow rally), or down
    on strong breadth (hidden strength), is a DIVERGENCE — the headline isn't backed by the internals."""
    usable = [r for r in returns if r.return_fraction == r.return_fraction]
    if not usable:
        return CrossMarketContext(0.0, 0.0, False, False, "no data for cross-market context")
    market_return = fmean(r.return_fraction for r in usable)
    breadth_pct = sum(1 for r in usable if r.return_fraction > 0) / len(usable)
    # confirmation: the market move sign agrees with the majority direction of stocks.
    if market_return > 0:
        confirms = breadth_pct >= 0.55
    elif market_return < 0:
        confirms = breadth_pct <= 0.45
    else:
        confirms = 0.45 <= breadth_pct <= 0.55
    divergence = not confirms
    summary = (
        f"market (equal-weighted mean) {market_return:+.2%}, breadth {breadth_pct:.0%} advancing — "
        + ("CONFIRMED by breadth" if confirms
           else "DIVERGENCE: the move is not backed by the internals")
    )
    return CrossMarketContext(
        market_return=market_return, breadth_pct=breadth_pct, confirms=confirms,
        divergence=divergence, summary=summary,
    )
