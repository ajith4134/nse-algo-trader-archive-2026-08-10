"""VPIN — Volume-Synchronized Probability of Informed Trading (order-flow toxicity), from
OHLCV bars (§53 ADVANCED; research/94).

VPIN measures how ONE-SIDED (toxic / informed) recent order flow is, in [0, 1] — high VPIN
warns that adverse-selection risk is elevated. It needs only price + volume (NO L2 depth), so
it is buildable from our bars today (unlike the depth-gated OFI/queue features).

Algorithm (Easley, López de Prado & O'Hara 2012, "Flow Toxicity and Liquidity in a High-
Frequency World", RFS 25(5)) — implemented from the reference (the public GitHub ports are
small/tick-oriented and untested; see research/94 for the sourcing sweep):
  1. Bulk Volume Classification (BVC): per bar, buy fraction = Φ(ΔP / σ_ΔP) where Φ is the
     standard-normal CDF of the standardized close-to-close change; buy_vol = V·Φ, sell_vol
     = V·(1−Φ).
  2. Equal-volume buckets: accumulate bars into buckets of a fixed `bucket_volume`, splitting
     the boundary bar proportionally.
  3. VPIN = mean over the last N buckets of |Vbuy − Vsell| / Vbucket.
PURE (no I/O); operates on the same `PriceBar` the rest of the pipeline uses.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass

from nse_algo_trader.market_data.market_data_types import PriceBar

_SQRT2 = math.sqrt(2.0)


def _standard_normal_cdf(z: float) -> float:
    """Φ(z) via the error function — buy fraction for a standardized price change."""
    return 0.5 * (1.0 + math.erf(z / _SQRT2))


@dataclass(frozen=True)
class BucketFlow:
    """One equal-volume bucket's classified buy/sell volume."""

    buy_volume: float
    sell_volume: float

    @property
    def total_volume(self) -> float:
        return self.buy_volume + self.sell_volume

    @property
    def order_imbalance(self) -> float:
        """|buy − sell| / total ∈ [0, 1] — the bucket's one-sidedness (0 balanced, 1 toxic)."""
        total = self.total_volume
        return abs(self.buy_volume - self.sell_volume) / total if total > 0 else 0.0


@dataclass(frozen=True)
class VpinReading:
    """The order-flow toxicity read over the most recent buckets."""

    vpin: float | None  # None when there aren't enough bars/volume to form buckets
    bucket_count: int
    bucket_volume: float
    classified_bars: int


def bulk_volume_classified_bars(
    bars: list[PriceBar], sigma_window: int = 50
) -> list[tuple[float, float]]:
    """Per-bar (buy_volume, sell_volume) via Bulk Volume Classification. σ is the std of
    close-to-close changes over a trailing window (min 2 changes); a zero/thin σ → a 50/50
    split (no directional information)."""
    if len(bars) < 2:
        return []
    price_changes = [
        bars[i].close_price - bars[i - 1].close_price for i in range(1, len(bars))
    ]
    classified: list[tuple[float, float]] = []
    for i, change in enumerate(price_changes):
        window = price_changes[max(0, i - sigma_window + 1) : i + 1]
        sigma = statistics.pstdev(window) if len(window) >= 2 else 0.0
        buy_fraction = _standard_normal_cdf(change / sigma) if sigma > 0 else 0.5
        volume = float(bars[i + 1].volume)
        classified.append((volume * buy_fraction, volume * (1.0 - buy_fraction)))
    return classified


def equal_volume_buckets(
    classified_bars: list[tuple[float, float]], bucket_volume: float
) -> list[BucketFlow]:
    """Pack classified per-bar volume into equal-volume buckets of `bucket_volume`, splitting
    a boundary bar proportionally across buckets. Trailing partial volume is dropped (only
    FULL buckets count, per the method)."""
    if bucket_volume <= 0:
        return []
    buckets: list[BucketFlow] = []
    cur_buy = cur_sell = cur_vol = 0.0
    for buy, sell in classified_bars:
        bar_total = buy + sell
        if bar_total <= 0:
            continue
        remaining = bar_total
        buy_rate, sell_rate = buy / bar_total, sell / bar_total
        while remaining > 0:
            room = bucket_volume - cur_vol
            take = min(room, remaining)
            cur_buy += take * buy_rate
            cur_sell += take * sell_rate
            cur_vol += take
            remaining -= take
            if cur_vol >= bucket_volume - 1e-9:
                buckets.append(BucketFlow(cur_buy, cur_sell))
                cur_buy = cur_sell = cur_vol = 0.0
    return buckets


def compute_vpin(
    bars: list[PriceBar],
    bucket_volume: float | None = None,
    bucket_count: int = 50,
    sigma_window: int = 50,
) -> VpinReading:
    """VPIN over the last `bucket_count` equal-volume buckets. When `bucket_volume` is not
    given it is auto-sized to total_volume / bucket_count (so a session forms ~bucket_count
    buckets). Returns `vpin=None` when there are too few bars/volume to form a bucket."""
    classified = bulk_volume_classified_bars(bars, sigma_window)
    total_volume = sum(b + s for b, s in classified)
    if total_volume <= 0:
        return VpinReading(None, 0, 0.0, len(classified))
    if bucket_volume is None or bucket_volume <= 0:
        bucket_volume = total_volume / max(bucket_count, 1)
    buckets = equal_volume_buckets(classified, bucket_volume)
    if not buckets:
        return VpinReading(None, 0, bucket_volume, len(classified))
    recent = buckets[-bucket_count:]
    vpin = sum(b.order_imbalance for b in recent) / len(recent)
    return VpinReading(
        vpin=vpin, bucket_count=len(recent), bucket_volume=bucket_volume,
        classified_bars=len(classified),
    )
