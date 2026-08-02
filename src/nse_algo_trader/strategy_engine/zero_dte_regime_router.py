"""B32 · 0-DTE expiry-day structure router — which defined-risk option structure to deploy NOW.

The operator wants option trades across EVERY regime, not just on an Opening Range Breakout. This
router is the fix: it takes the union of several triggers (intraday vol-expansion, dealer-gamma
positioning, ADX regime, expiry-day time-window, and the kept ORB signal) and maps the live regime to
ONE defined-risk structure (docs/research/174 §3–§4):

  · S1 DIRECTIONAL_LONG_OPTION — buy an ATM CE/PE in the move's direction. For a TRENDING /
        short-gamma (dealers amplify) / ORB-confirmed / pre-close-gamma-ramp state.
  · S2 LONG_STRADDLE          — buy ATM CE+PE. For a vol-EXPANSION with NO clear direction (event-like)
        — profit from a large move either way.
  · S3 SHORT_PREMIUM_SPREAD   — sell a defined-risk spread (iron fly / credit spread). For a PINNED /
        long-gamma (dealers dampen) / IV-rich / near-max-pain state — harvest 0-DTE theta.
  · ABSTAIN                   — no structure has an edge in the current state (counted, never a silent
        no-op; Rule K).

Every branch is defined-risk (Rule: no naked short on 0-DTE). The router is a PURE function over
already-computed signals, so it is testable without a feed, a clock, or a broker.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from nse_algo_trader.indicators.dealer_gamma_exposure import (
    DealerGammaExposureReading,
    DealerGammaRegime,
)
from nse_algo_trader.indicators.yang_zhang_realized_volatility import (
    VolatilityExpansionReading,
)
from nse_algo_trader.strategy_engine.session_strategy_regime_gate import MarketRegime
from nse_algo_trader.strategy_engine.strategy_signal_types import SignalDirection


class ZeroDteStructure(str, Enum):
    DIRECTIONAL_LONG_OPTION = "directional_long_option"  # S1
    LONG_STRADDLE = "long_straddle"                       # S2
    SHORT_PREMIUM_SPREAD = "short_premium_spread"         # S3
    ABSTAIN = "abstain"


class ZeroDteEntryTrigger(str, Enum):
    OPENING_RANGE_BREAKOUT = "opening_range_breakout"
    VOLATILITY_EXPANSION = "volatility_expansion"
    DEALER_GAMMA_FLOW = "dealer_gamma_flow"
    TIME_WINDOW = "time_window"
    NONE = "none"


class ExpiryDayTimeWindow(str, Enum):
    """Expiry-day intraday clock structure (docs/research/174 §2)."""

    OPEN_BURST = "open_burst"                 # ~09:20–10:00 — highest realized vol
    MIDDAY_LULL = "midday_lull"               # ~11:00–13:30 — pin gravitation
    PRE_CLOSE_GAMMA_RAMP = "pre_close_gamma_ramp"  # ~14:00+ — gamma accelerates into expiry
    OTHER = "other"


@dataclass(frozen=True)
class ZeroDteRouterInputs:
    """All already-computed signals the router folds into a structure choice."""

    adx_regime: MarketRegime
    volatility_expansion: VolatilityExpansionReading
    dealer_gamma: DealerGammaExposureReading
    #: direction of the current intraday thrust, or None if the move is two-sided/ambiguous.
    momentum_direction: SignalDirection | None
    #: the kept ORB signal's direction, or None if ORB did not fire this look.
    opening_range_breakout_direction: SignalDirection | None
    time_window: ExpiryDayTimeWindow
    #: from the IV-rank engine — True/False when earned, None while it abstains (<60 obs).
    implied_volatility_is_rich: bool | None
    #: spot sitting near the max-pain / highest-OI strike (pin gravitation).
    near_max_pain: bool


@dataclass(frozen=True)
class ZeroDteRouterDecision:
    structure: ZeroDteStructure
    #: set only for DIRECTIONAL_LONG_OPTION (which side to buy); None otherwise.
    direction: SignalDirection | None
    trigger: ZeroDteEntryTrigger
    reason: str


def route_zero_dte_structure(inputs: ZeroDteRouterInputs) -> ZeroDteRouterDecision:
    """Map the live expiry-day regime to ONE defined-risk structure. Priority order is deliberate:
    an explicit ORB signal is honoured first (kept, per operator), then a directional trend, then an
    ambiguous vol-expansion (straddle), then a pin (short premium); otherwise abstain."""
    gamma_regime = inputs.dealer_gamma.regime
    is_vol_expanding = inputs.volatility_expansion.is_expanding
    is_trending = inputs.adx_regime is MarketRegime.TRENDING
    is_range_bound = inputs.adx_regime is MarketRegime.RANGE_BOUND
    dealers_amplify = gamma_regime is DealerGammaRegime.SHORT_GAMMA_TREND
    dealers_dampen = gamma_regime is DealerGammaRegime.LONG_GAMMA_PIN

    # 1) ORB kept — an explicit breakout is the strongest directional tell.
    if inputs.opening_range_breakout_direction is not None:
        return ZeroDteRouterDecision(
            structure=ZeroDteStructure.DIRECTIONAL_LONG_OPTION,
            direction=inputs.opening_range_breakout_direction,
            trigger=ZeroDteEntryTrigger.OPENING_RANGE_BREAKOUT,
            reason="ORB breakout — buy the directional 0-DTE option in the break direction",
        )

    # 2) Directional trend — a known-direction thrust that dealers amplify or ADX calls trending,
    #    confirmed by vol-expansion or the pre-close gamma ramp.
    trend_confirmed = is_vol_expanding or (
        inputs.time_window is ExpiryDayTimeWindow.PRE_CLOSE_GAMMA_RAMP
    )
    if (
        inputs.momentum_direction is not None
        and (dealers_amplify or is_trending)
        and trend_confirmed
    ):
        why = "short-gamma (dealers amplify)" if dealers_amplify else "ADX trending"
        return ZeroDteRouterDecision(
            structure=ZeroDteStructure.DIRECTIONAL_LONG_OPTION,
            direction=inputs.momentum_direction,
            trigger=(
                ZeroDteEntryTrigger.DEALER_GAMMA_FLOW
                if dealers_amplify
                else ZeroDteEntryTrigger.VOLATILITY_EXPANSION
            ),
            reason=f"directional 0-DTE: {why} + confirmed thrust",
        )

    # 3) Ambiguous vol-expansion — a big move is coming but direction is unclear → long straddle.
    if is_vol_expanding and inputs.momentum_direction is None and not dealers_dampen:
        return ZeroDteRouterDecision(
            structure=ZeroDteStructure.LONG_STRADDLE,
            direction=None,
            trigger=ZeroDteEntryTrigger.VOLATILITY_EXPANSION,
            reason="vol-expansion with no clear direction — long straddle (move either way)",
        )

    # 4) Pin — dealers dampen or ADX range-bound, with IV rich or spot near max-pain → short premium.
    pin_state = dealers_dampen or is_range_bound
    pin_confirm = (inputs.implied_volatility_is_rich is True) or inputs.near_max_pain
    if pin_state and pin_confirm:
        why = "long-gamma (dealers dampen)" if dealers_dampen else "ADX range-bound"
        confirm = "IV rich" if inputs.implied_volatility_is_rich is True else "near max-pain"
        return ZeroDteRouterDecision(
            structure=ZeroDteStructure.SHORT_PREMIUM_SPREAD,
            direction=None,
            trigger=ZeroDteEntryTrigger.DEALER_GAMMA_FLOW,
            reason=f"short-premium 0-DTE: {why} + {confirm} — harvest theta on a pin",
        )

    return ZeroDteRouterDecision(
        structure=ZeroDteStructure.ABSTAIN,
        direction=None,
        trigger=ZeroDteEntryTrigger.NONE,
        reason=(
            "no 0-DTE edge: "
            f"regime={inputs.adx_regime.value}, gamma={gamma_regime.value}, "
            f"vol_expanding={is_vol_expanding}, momentum={'yes' if inputs.momentum_direction else 'no'}"
        ),
    )
