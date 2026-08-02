"""Dealer gamma exposure (GEX) from the live option chain — the pin-vs-trend regime signal.

GEX estimates how much option-dealer hedging will DAMPEN or AMPLIFY spot moves, following the
SqueezeMetrics gamma-exposure method (docs/research/174 §3). Per strike, the naive dealer-position
convention is: dealers are LONG call gamma and SHORT put gamma. Their hedge of that gamma is what
moves the tape:

  · GEX > 0  (net long gamma)  → dealers SELL rallies / BUY dips → spot is PINNED / mean-reverts.
                                  The 0-DTE router prefers short-premium (S3) here.
  · GEX < 0  (net short gamma) → dealers BUY rallies / SELL dips → spot TRENDS / moves amplify.
                                  The router prefers directional / long-gamma (S1/S2) here.

Per-strike dollar-gamma exposure (per 1% underlying move):

    strike_gex = (call_gamma · call_open_interest − put_gamma · put_open_interest)
                 · contract_multiplier · spot²  · 0.01

summed across strikes. Gamma is computed from the live per-strike IV with the in-repo Black-Scholes
`compute_black_scholes_gamma` (reuse, not a vendored lib). Abstains (Rule Q) when the chain is empty
or carries no usable IV, rather than reporting a false-confident 0.0 that would look like a balanced
book.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from nse_algo_trader.indicators.black_scholes_implied_volatility import (
    compute_black_scholes_gamma,
)


@dataclass(frozen=True)
class OptionChainStrikeInputs:
    """One strike's live inputs for the GEX sum. IVs are the market's per-side implied vols
    (decimals, e.g. 0.18); open interest is in contracts; `contract_multiplier` is the lot size."""

    strike_price: float
    call_implied_volatility: float | None
    put_implied_volatility: float | None
    call_open_interest: int
    put_open_interest: int
    contract_multiplier: int


class DealerGammaRegime(str, Enum):
    LONG_GAMMA_PIN = "long_gamma_pin"       # GEX > 0 → dampened → prefer short premium
    SHORT_GAMMA_TREND = "short_gamma_trend"  # GEX < 0 → amplified → prefer directional/long-gamma
    NEUTRAL = "neutral"                       # |GEX| below the significance floor
    UNKNOWN = "unknown"                       # abstained: no usable chain


@dataclass(frozen=True)
class DealerGammaExposureReading:
    """The chain-wide GEX verdict for one underlying at one look."""

    total_gamma_exposure: float | None
    regime: DealerGammaRegime
    contributing_strike_count: int
    abstain_reason: str | None


#: |GEX| below this fraction of the largest single-strike |contribution| is treated as a balanced
#: book (NEUTRAL) rather than a weak directional read — avoids routing on noise near the flip point.
_NEUTRAL_BAND_FRACTION_OF_PEAK_STRIKE = 0.10


def compute_dealer_gamma_exposure(
    underlying_spot_price: float,
    time_to_expiry_years: float,
    chain_strikes: list[OptionChainStrikeInputs],
) -> DealerGammaExposureReading:
    """Chain-wide signed dealer gamma exposure + its pin/trend regime classification. `time_to_expiry
    _years` may be tiny on expiry day; the caller clamps it (as the pricing path already does) so
    gamma stays finite. Abstains when no strike carries usable IV/OI."""
    if underlying_spot_price <= 0.0 or not chain_strikes:
        return DealerGammaExposureReading(
            total_gamma_exposure=None,
            regime=DealerGammaRegime.UNKNOWN,
            contributing_strike_count=0,
            abstain_reason="no spot or empty chain",
        )

    spot_squared_per_percent = underlying_spot_price * underlying_spot_price * 0.01
    total_gamma_exposure = 0.0
    contributing_strike_count = 0
    peak_absolute_strike_contribution = 0.0

    for strike in chain_strikes:
        strike_contribution = 0.0
        used_strike = False
        if strike.call_implied_volatility is not None and strike.call_open_interest > 0:
            call_gamma = compute_black_scholes_gamma(
                underlying_spot_price, strike.strike_price,
                time_to_expiry_years, strike.call_implied_volatility,
            )
            strike_contribution += call_gamma * strike.call_open_interest
            used_strike = True
        if strike.put_implied_volatility is not None and strike.put_open_interest > 0:
            put_gamma = compute_black_scholes_gamma(
                underlying_spot_price, strike.strike_price,
                time_to_expiry_years, strike.put_implied_volatility,
            )
            strike_contribution -= put_gamma * strike.put_open_interest
            used_strike = True
        if not used_strike:
            continue
        strike_contribution *= strike.contract_multiplier * spot_squared_per_percent
        total_gamma_exposure += strike_contribution
        contributing_strike_count += 1
        peak_absolute_strike_contribution = max(
            peak_absolute_strike_contribution, abs(strike_contribution)
        )

    if contributing_strike_count == 0:
        return DealerGammaExposureReading(
            total_gamma_exposure=None,
            regime=DealerGammaRegime.UNKNOWN,
            contributing_strike_count=0,
            abstain_reason="no strike carried usable IV and open interest",
        )

    neutral_band = _NEUTRAL_BAND_FRACTION_OF_PEAK_STRIKE * peak_absolute_strike_contribution
    if abs(total_gamma_exposure) <= neutral_band:
        regime = DealerGammaRegime.NEUTRAL
    elif total_gamma_exposure > 0.0:
        regime = DealerGammaRegime.LONG_GAMMA_PIN
    else:
        regime = DealerGammaRegime.SHORT_GAMMA_TREND

    return DealerGammaExposureReading(
        total_gamma_exposure=total_gamma_exposure,
        regime=regime,
        contributing_strike_count=contributing_strike_count,
        abstain_reason=None,
    )
