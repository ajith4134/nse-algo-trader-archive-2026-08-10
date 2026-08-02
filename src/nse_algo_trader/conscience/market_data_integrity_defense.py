"""Market-data integrity / adversarial-input defense (Trunk VII; research/121) — CONSCIENCE input
security organ.

An autonomous system's INPUTS are an attack surface (adversarial ML / data poisoning). For this bot
the surface is the market-data feed: a spoofed or corrupt bar — an impossible jump, a zero/negative
price, a crossed candle (high<low), a stale/duplicate timestamp — can trigger a false signal and a
bad trade. This organ screens the bars a decision is built from BEFORE they feed the strategy and
refuses to trade on corrupted data. Distinct from the causal-leakage firewall (which defends
temporal integrity — future data leaking in); this defends VALUE integrity — bad values. PURE (no
I/O) — the state gate calls `screen_bar_series` at the signal-build site.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class IntegrityLimits:
    max_single_bar_move_fraction: float = 0.20  # a >20% one-bar move vs prev close is suspicious
    min_price: float = 0.0                       # prices must be strictly positive


@dataclass(frozen=True)
class BarIntegrityVerdict:
    clean: bool
    anomalies: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SeriesIntegrityVerdict:
    clean: bool
    anomaly_count: int
    anomalies: tuple[str, ...] = field(default_factory=tuple)

    @property
    def reason(self) -> str:
        return "clean market data" if self.clean else "; ".join(self.anomalies[:4])


def screen_bar(
    bar, previous_close: float | None, limits: IntegrityLimits = IntegrityLimits()
) -> BarIntegrityVerdict:
    """Screen one OHLC bar for value-integrity anomalies: positive prices, OHLC consistency, and an
    impossible move vs the previous close."""
    anomalies: list[str] = []
    o, h, l, c = bar.open_price, bar.high_price, bar.low_price, bar.close_price
    if min(o, h, l, c) <= limits.min_price:
        anomalies.append("non-positive-price")
    if h < l:
        anomalies.append("crossed-candle(high<low)")
    if not (l <= o <= h and l <= c <= h):
        anomalies.append("ohlc-inconsistent")
    if previous_close is not None and previous_close > 0:
        move = abs(c - previous_close) / previous_close
        if move > limits.max_single_bar_move_fraction:
            anomalies.append(f"impossible-move({move:.0%})")
    return BarIntegrityVerdict(clean=not anomalies, anomalies=tuple(anomalies))


def screen_bar_series(
    bars, limits: IntegrityLimits = IntegrityLimits()
) -> SeriesIntegrityVerdict:
    """Screen a bar series: each bar's value integrity + timestamp monotonicity (stale/duplicate/
    replayed ticks). Returns the aggregate verdict."""
    anomalies: list[str] = []
    previous_close: float | None = None
    previous_timestamp = None
    for bar in bars:
        verdict = screen_bar(bar, previous_close, limits)
        anomalies.extend(verdict.anomalies)
        if previous_timestamp is not None:
            if bar.timestamp == previous_timestamp:
                anomalies.append("duplicate-timestamp")
            elif bar.timestamp < previous_timestamp:
                anomalies.append("non-monotonic-timestamp")
        previous_timestamp = bar.timestamp
        previous_close = bar.close_price
    return SeriesIntegrityVerdict(
        clean=not anomalies, anomaly_count=len(anomalies), anomalies=tuple(anomalies),
    )
