"""Yang-Zhang realized-volatility estimator + intraday volatility-expansion detector.

The Yang-Zhang (2000) estimator is the minimum-variance, drift-independent realized-vol
estimator that correctly accounts for the OVERNIGHT/inter-bar GAP — the exact reason it is
chosen for NSE, whose sessions open with pre-open-auction and GIFT-Nifty-driven gaps that a
close-to-close or Parkinson estimator mis-measures (docs/research/174 §3, B18 spec A3).

It decomposes total variance into three orthogonal pieces:

    σ²_YZ = σ²_overnight + k · σ²_open_close + (1 − k) · σ²_rogers_satchell

where, over a window of `n` bars:
  · σ²_overnight       = sample variance of  ln(open_t / close_{t-1})   (the gap term)
  · σ²_open_close      = sample variance of  ln(close_t / open_t)       (the intrabar drift)
  · σ²_rogers_satchell = mean of  ln(H/C)·ln(H/O) + ln(L/C)·ln(L/O)     (drift-free range term)
  · k = 0.34 / (1.34 + (n + 1)/(n − 1))                                 (variance-minimising weight)

Applied to intraday bars, "overnight" is the gap between CONSECUTIVE bars (close_{t-1} → open_t),
so the estimator captures both the micro-gaps between 5-minute bars and the session-open gap.

The `detect_intraday_volatility_expansion` wrapper compares the latest windowed RV against its own
rolling band (mean + z·std of the trailing RV series) so the 0-DTE engine can fire the
"vol-expansion" entry trigger when realized volatility breaks OUT of its recent regime.

Maturity ladder (Rule Q): every function ABSTAINS with a counted reason when it has fewer bars than
its estimator/window needs — never emits a confident-looking number over too little data.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from nse_algo_trader.market_data.market_data_types import PriceBar

#: Yang-Zhang needs a variance over the window, so at least this many bars (2 gaps → n≥3, but a
#: stable variance needs more; 6 mirrors the smallest window over which the k-weight is meaningful).
MINIMUM_BARS_FOR_YANG_ZHANG = 6

#: The vol-expansion detector needs a trailing RV SERIES to form a band; each RV point consumes a
#: full estimator window, so the band needs (window + series) bars. Kept modest so it warms
#: within the first ~hour of 5-minute bars on expiry day.
DEFAULT_REALIZED_VOLATILITY_WINDOW_BARS = 12
DEFAULT_EXPANSION_BAND_SERIES_LENGTH = 12
DEFAULT_EXPANSION_BAND_Z = 2.0


def _log(numerator: float, denominator: float) -> float | None:
    """Natural log of a price ratio, or None if either price is non-positive (degenerate bar)."""
    if numerator <= 0.0 or denominator <= 0.0:
        return None
    return math.log(numerator / denominator)


def compute_yang_zhang_realized_volatility(bars: list[PriceBar]) -> float | None:
    """The Yang-Zhang realized volatility over `bars`, in the SAME per-bar units as the returns
    (not annualised — the 0-DTE engine compares like-with-like intraday, so scaling is deferred to
    the caller). Returns None (abstains) when fewer than `MINIMUM_BARS_FOR_YANG_ZHANG` usable bars
    exist or the inputs are degenerate, so a hiccup never emits a fake-confident 0.0.
    """
    if len(bars) < MINIMUM_BARS_FOR_YANG_ZHANG:
        return None

    overnight_log_returns: list[float] = []
    open_close_log_returns: list[float] = []
    rogers_satchell_terms: list[float] = []

    for previous_bar, current_bar in zip(bars[:-1], bars[1:], strict=True):
        overnight = _log(current_bar.open_price, previous_bar.close_price)
        open_close = _log(current_bar.close_price, current_bar.open_price)
        high_over_close = _log(current_bar.high_price, current_bar.close_price)
        high_over_open = _log(current_bar.high_price, current_bar.open_price)
        low_over_close = _log(current_bar.low_price, current_bar.close_price)
        low_over_open = _log(current_bar.low_price, current_bar.open_price)
        if None in (
            overnight, open_close,
            high_over_close, high_over_open, low_over_close, low_over_open,
        ):
            continue  # skip the degenerate bar pair rather than poison the whole estimate
        overnight_log_returns.append(overnight)  # type: ignore[arg-type]
        open_close_log_returns.append(open_close)  # type: ignore[arg-type]
        rogers_satchell_terms.append(
            high_over_close * high_over_open + low_over_close * low_over_open  # type: ignore[operator]
        )

    sample_size = len(rogers_satchell_terms)
    if sample_size < MINIMUM_BARS_FOR_YANG_ZHANG - 1:
        return None

    overnight_variance = _sample_variance(overnight_log_returns)
    open_close_variance = _sample_variance(open_close_log_returns)
    rogers_satchell_variance = sum(rogers_satchell_terms) / sample_size
    if overnight_variance is None or open_close_variance is None:
        return None

    yang_zhang_weight = 0.34 / (1.34 + (sample_size + 1) / (sample_size - 1))
    total_variance = (
        overnight_variance
        + yang_zhang_weight * open_close_variance
        + (1.0 - yang_zhang_weight) * rogers_satchell_variance
    )
    # Rogers-Satchell is a sum of signed products and can, on a tiny degenerate window, push the
    # combination marginally negative; clamp at zero so sqrt is always defined.
    return math.sqrt(max(total_variance, 0.0))


def _sample_variance(values: list[float]) -> float | None:
    """Unbiased (n−1) sample variance, or None if fewer than two values."""
    count = len(values)
    if count < 2:
        return None
    mean_value = sum(values) / count
    return sum((value - mean_value) ** 2 for value in values) / (count - 1)


@dataclass(frozen=True)
class VolatilityExpansionReading:
    """The vol-expansion trigger's verdict for one underlying at one look.

    `is_expanding` is True only when the latest realized vol breaks ABOVE its own trailing band —
    the signal the 0-DTE engine uses to fire a long-gamma/directional entry. When the estimator
    cannot form a reading it abstains: `is_expanding=False` with a populated `abstain_reason`.
    """

    is_expanding: bool
    current_realized_volatility: float | None
    band_mean: float | None
    band_upper_threshold: float | None
    abstain_reason: str | None


def detect_intraday_volatility_expansion(
    bars: list[PriceBar],
    realized_volatility_window_bars: int = DEFAULT_REALIZED_VOLATILITY_WINDOW_BARS,
    band_series_length: int = DEFAULT_EXPANSION_BAND_SERIES_LENGTH,
    band_z: float = DEFAULT_EXPANSION_BAND_Z,
) -> VolatilityExpansionReading:
    """Compute a rolling Yang-Zhang RV series over the trailing bars and report whether the LATEST
    RV has expanded beyond `band_mean + band_z · band_std`. Abstains (never asserts expansion) until
    enough bars exist to form both the estimator window and the band series.
    """
    # The band must reflect vol BEFORE the current window. Consecutive rolling windows overlap by
    # (window − 1) bars, so the (window − 1) RV points just before the current one share bars with
    # it and would leak the burst into its own baseline. Those overlapping points are excluded from
    # the band, so `bars_needed` carries that gap explicitly.
    overlap_guard = realized_volatility_window_bars - 1
    bars_needed = realized_volatility_window_bars + overlap_guard + band_series_length
    if len(bars) < bars_needed:
        return VolatilityExpansionReading(
            is_expanding=False,
            current_realized_volatility=None,
            band_mean=None,
            band_upper_threshold=None,
            abstain_reason=(
                f"warming up: have {len(bars)} bars, need {bars_needed} "
                f"({realized_volatility_window_bars} window + {overlap_guard} overlap-guard "
                f"+ {band_series_length} band)"
            ),
        )

    realized_volatility_series: list[float] = []
    for window_end in range(realized_volatility_window_bars, len(bars) + 1):
        window = bars[window_end - realized_volatility_window_bars : window_end]
        realized_volatility = compute_yang_zhang_realized_volatility(window)
        if realized_volatility is not None:
            realized_volatility_series.append(realized_volatility)

    # Exclude the current point AND the `overlap_guard` points that share bars with it, so the band
    # is the pre-burst baseline.
    non_overlapping_band_pool = realized_volatility_series[: -(overlap_guard + 1)] if overlap_guard else realized_volatility_series[:-1]
    if len(non_overlapping_band_pool) < band_series_length:
        return VolatilityExpansionReading(
            is_expanding=False,
            current_realized_volatility=(
                realized_volatility_series[-1] if realized_volatility_series else None
            ),
            band_mean=None,
            band_upper_threshold=None,
            abstain_reason="too many degenerate bars to form a stable RV band",
        )

    current_realized_volatility = realized_volatility_series[-1]
    trailing = non_overlapping_band_pool[-band_series_length:]
    band_mean = sum(trailing) / len(trailing)
    band_standard_deviation = math.sqrt(
        sum((value - band_mean) ** 2 for value in trailing) / (len(trailing) - 1)
    )
    band_upper_threshold = band_mean + band_z * band_standard_deviation

    return VolatilityExpansionReading(
        is_expanding=current_realized_volatility > band_upper_threshold,
        current_realized_volatility=current_realized_volatility,
        band_mean=band_mean,
        band_upper_threshold=band_upper_threshold,
        abstain_reason=None,
    )
