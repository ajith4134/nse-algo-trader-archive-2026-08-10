"""§53 ADVANCED — VPIN order-flow toxicity (hermetic). A consistently one-directional flow
scores HIGH VPIN (toxic); a balanced oscillating flow scores LOW; edge cases return None."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from nse_algo_trader.market_data.market_data_types import BarInterval, PriceBar
from nse_algo_trader.market_data.vpin_order_flow_toxicity import (
    BucketFlow,
    compute_vpin,
    equal_volume_buckets,
)

IST = ZoneInfo("Asia/Kolkata")


def _bars(closes, volume=1000):
    base = datetime(2026, 7, 24, 9, 15, tzinfo=IST)
    return [PriceBar(
        instrument_token=1, timestamp=base + timedelta(minutes=i), interval=BarInterval.MINUTE_1,
        open_price=c, high_price=c + 1, low_price=c - 1, close_price=c, volume=volume,
        open_interest=None) for i, c in enumerate(closes)]


def test_toxic_one_directional_flow_scores_high():
    # steady large UP moves (small variance) → every bar classified ~all-buy → VPIN ≈ 1.
    closes = [100.0]
    for i in range(30):
        closes.append(closes[-1] + 10 + (0.5 if i % 2 else -0.5))
    reading = compute_vpin(_bars(closes), bucket_count=5)
    assert reading.vpin is not None and reading.vpin > 0.8


def test_balanced_flow_scores_low():
    # alternating ±10 → buys and sells offset within each bucket → low VPIN.
    closes = [100.0]
    for i in range(30):
        closes.append(closes[-1] + (10 if i % 2 == 0 else -10))
    reading = compute_vpin(_bars(closes), bucket_count=5)
    assert reading.vpin is not None and reading.vpin < 0.5


def test_toxic_beats_balanced():
    up = [100.0]
    for i in range(30):
        up.append(up[-1] + 10 + (0.5 if i % 2 else -0.5))
    bal = [100.0]
    for i in range(30):
        bal.append(bal[-1] + (10 if i % 2 == 0 else -10))
    assert compute_vpin(_bars(up), bucket_count=5).vpin > compute_vpin(_bars(bal), bucket_count=5).vpin


def test_too_few_bars_is_none():
    assert compute_vpin(_bars([100.0])).vpin is None
    assert compute_vpin([]).vpin is None


def test_zero_volume_is_none():
    assert compute_vpin(_bars([100, 101, 102, 103], volume=0)).vpin is None


def test_equal_volume_buckets_split_boundary():
    # two bars of 100 vol each, bucket size 150 → one full bucket (150), 50 dropped.
    classified = [(80.0, 20.0), (30.0, 70.0)]  # bar1 buy-heavy, bar2 sell-heavy
    buckets = equal_volume_buckets(classified, bucket_volume=150.0)
    assert len(buckets) == 1
    assert abs(buckets[0].total_volume - 150.0) < 1e-6


def test_bucket_imbalance():
    assert BucketFlow(buy_volume=100, sell_volume=0).order_imbalance == 1.0  # fully toxic
    assert BucketFlow(buy_volume=50, sell_volume=50).order_imbalance == 0.0  # balanced
