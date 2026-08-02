"""B32 · 0-DTE entry planner — assemble every router signal from the live ladder + bars, then plan.

This is the integration core of the 0-DTE expiry-day engine (docs/research/174 §10 part 5): given ONE
underlying's expiry-day option ladder, live premia/OI/IV, and its spot bars, it computes all router
inputs (ADX regime · Yang-Zhang vol-expansion · dealer-gamma GEX · intraday momentum · kept ORB ·
expiry-day time-window · IV-rank rich/cheap · max-pain proximity), routes to a defined-risk structure,
builds the legs, and returns a PLAN with the structure's defined max-loss per lot.

Pure — no clock, feed, broker, or state. The live path (part 5b) assembles the inputs from the feed
and carries the placement + time-stop + square-off + daily-loss-cap state. Kept pure so the whole
routing decision is testable hermetically (Rule J) before a single order is placed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time

from nse_algo_trader.indicators.average_directional_index import (
    compute_average_directional_index,
)
from nse_algo_trader.indicators.dealer_gamma_exposure import (
    OptionChainStrikeInputs,
    compute_dealer_gamma_exposure,
)
from nse_algo_trader.indicators.yang_zhang_realized_volatility import (
    DEFAULT_REALIZED_VOLATILITY_WINDOW_BARS,
    detect_intraday_volatility_expansion,
)
from nse_algo_trader.market_data.market_data_types import PriceBar
from nse_algo_trader.strategy_engine.implied_volatility_rank import rank_implied_volatility
from nse_algo_trader.strategy_engine.opening_range_breakout_strategy import (
    detect_opening_range_breakout,
)
from nse_algo_trader.strategy_engine.session_strategy_regime_gate import (
    classify_adx_market_regime,
)
from nse_algo_trader.strategy_engine.strategy_signal_types import SignalDirection
from nse_algo_trader.strategy_engine.zero_dte_option_structures import (
    ZeroDteStructureLegs,
    build_directional_long_option,
    build_long_straddle,
    build_short_premium_iron_fly,
)
from nse_algo_trader.strategy_engine.zero_dte_regime_router import (
    ExpiryDayTimeWindow,
    ZeroDteRouterInputs,
    ZeroDteStructure,
    route_zero_dte_structure,
)
from nse_algo_trader.universe_registry.instrument_types import Instrument, OptionRight

_MARKET_CLOSE_IST = time(15, 30)
_SECONDS_PER_YEAR = 365.0 * 24.0 * 60.0 * 60.0
#: floor the expiry-day time-to-expiry so ATM gamma stays finite in the last minutes.
_MINIMUM_TIME_TO_EXPIRY_YEARS = 60.0 / _SECONDS_PER_YEAR
#: net displacement over the RV window beyond which the move counts as directional (else straddle).
_DIRECTIONAL_DISPLACEMENT_FRACTION = 0.0015


@dataclass(frozen=True)
class ZeroDtePlannedEntry:
    """The planned 0-DTE entry for one underlying, or an abstention (structure == ABSTAIN)."""

    underlying_symbol: str
    structure: ZeroDteStructure
    direction: SignalDirection | None
    legs: tuple
    defined_risk_per_lot: float
    trigger: str
    reason: str

    @property
    def is_actionable(self) -> bool:
        return self.structure is not ZeroDteStructure.ABSTAIN and bool(self.legs)


def expiry_day_time_window(now: datetime) -> ExpiryDayTimeWindow:
    """Classify the expiry-day intraday clock (docs/research/174 §2)."""
    current = now.time()
    if current < time(10, 0):
        return ExpiryDayTimeWindow.OPEN_BURST
    if time(11, 0) <= current <= time(13, 30):
        return ExpiryDayTimeWindow.MIDDAY_LULL
    if current >= time(14, 0):
        return ExpiryDayTimeWindow.PRE_CLOSE_GAMMA_RAMP
    return ExpiryDayTimeWindow.OTHER


def _time_to_expiry_years(now: datetime) -> float:
    close_dt = datetime.combine(now.date(), _MARKET_CLOSE_IST, tzinfo=now.tzinfo)
    seconds = (close_dt - now).total_seconds()
    return max(seconds / _SECONDS_PER_YEAR, _MINIMUM_TIME_TO_EXPIRY_YEARS)


def _latest_adx(spot_bars: list[PriceBar]) -> float | None:
    series = compute_average_directional_index(spot_bars)
    for value in reversed(series.adx):
        if value is not None:
            return value
    return None


def _intraday_momentum_direction(spot_bars: list[PriceBar]) -> SignalDirection | None:
    """Signed net displacement over the RV window; None if the move is too small to call a side."""
    window = DEFAULT_REALIZED_VOLATILITY_WINDOW_BARS
    if len(spot_bars) <= window:
        return None
    reference = spot_bars[-window - 1].close_price
    latest = spot_bars[-1].close_price
    if reference <= 0.0:
        return None
    displacement = (latest - reference) / reference
    if displacement > _DIRECTIONAL_DISPLACEMENT_FRACTION:
        return SignalDirection.LONG
    if displacement < -_DIRECTIONAL_DISPLACEMENT_FRACTION:
        return SignalDirection.SHORT
    return None


def _strike_step(option_ladder: list[Instrument]) -> float:
    strikes = sorted({o.strike_price for o in option_ladder if o.strike_price is not None})
    gaps = [b - a for a, b in zip(strikes[:-1], strikes[1:], strict=True) if b > a]
    return min(gaps) if gaps else 0.0


def _near_max_pain(
    option_ladder: list[Instrument], open_interest_by_token: dict[int, int], spot_price: float
) -> bool:
    """Approximate the pin as the highest total-OI strike; near if spot sits within one strike step."""
    oi_by_strike: dict[float, int] = {}
    for option in option_ladder:
        if option.strike_price is None:
            continue
        oi_by_strike[option.strike_price] = (
            oi_by_strike.get(option.strike_price, 0)
            + open_interest_by_token.get(option.instrument_token, 0)
        )
    if not any(oi_by_strike.values()):
        return False
    pin_strike = max(oi_by_strike, key=lambda k: oi_by_strike[k])
    step = _strike_step(option_ladder)
    return step > 0.0 and abs(spot_price - pin_strike) <= step


def _dealer_gamma_reading(
    option_ladder: list[Instrument], spot_price: float, time_to_expiry_years: float,
    open_interest_by_token: dict[int, int], implied_volatility_by_token: dict[int, float],
):
    call_iv: dict[float, float] = {}
    put_iv: dict[float, float] = {}
    call_oi: dict[float, int] = {}
    put_oi: dict[float, int] = {}
    multiplier: dict[float, int] = {}
    for option in option_ladder:
        strike = option.strike_price
        if strike is None:
            continue
        multiplier[strike] = option.lot_size
        iv = implied_volatility_by_token.get(option.instrument_token)
        oi = open_interest_by_token.get(option.instrument_token, 0)
        if option.option_right is OptionRight.CALL:
            if iv is not None:
                call_iv[strike] = iv
            call_oi[strike] = oi
        else:
            if iv is not None:
                put_iv[strike] = iv
            put_oi[strike] = oi
    chain = [
        OptionChainStrikeInputs(
            strike_price=strike,
            call_implied_volatility=call_iv.get(strike),
            put_implied_volatility=put_iv.get(strike),
            call_open_interest=call_oi.get(strike, 0),
            put_open_interest=put_oi.get(strike, 0),
            contract_multiplier=multiplier[strike],
        )
        for strike in multiplier
    ]
    return compute_dealer_gamma_exposure(spot_price, time_to_expiry_years, chain)


def _implied_volatility_is_rich(
    underlying_symbol: str, option_ladder: list[Instrument], spot_price: float,
    implied_volatility_by_token: dict[int, float],
    historical_atm_iv_by_date: dict[date, float],
) -> bool | None:
    atm_call = min(
        (o for o in option_ladder
         if o.option_right is OptionRight.CALL and o.strike_price is not None),
        key=lambda o: abs(o.strike_price - spot_price),  # type: ignore[operator]
        default=None,
    )
    if atm_call is None:
        return None
    current_iv = implied_volatility_by_token.get(atm_call.instrument_token)
    if not current_iv or current_iv <= 0.0:
        return None
    ranking = rank_implied_volatility(underlying_symbol, current_iv, historical_atm_iv_by_date)
    if not ranking.is_usable:
        return None
    return ranking.is_rich


def plan_zero_dte_entry(
    underlying_symbol: str,
    spot_instrument: Instrument,
    spot_price: float,
    spot_bars: list[PriceBar],
    option_ladder: list[Instrument],
    premium_by_token: dict[int, float],
    open_interest_by_token: dict[int, int],
    implied_volatility_by_token: dict[int, float],
    historical_atm_iv_by_date: dict[date, float],
    now: datetime,
    lots: int = 1,
) -> ZeroDtePlannedEntry:
    """Assemble every router input for one 0-DTE underlying, route to a structure, and build its
    defined-risk legs. Returns an ABSTAIN plan (with reason) when no structure fits or a builder
    cannot form legs — never a silent no-op (Rule K)."""
    time_to_expiry_years = _time_to_expiry_years(now)
    today_bars = [b for b in spot_bars if b.timestamp.date() == now.date()]

    orb_signal = detect_opening_range_breakout(today_bars, spot_instrument) if today_bars else None
    router_inputs = ZeroDteRouterInputs(
        adx_regime=classify_adx_market_regime(_latest_adx(spot_bars)),
        volatility_expansion=detect_intraday_volatility_expansion(spot_bars),
        dealer_gamma=_dealer_gamma_reading(
            option_ladder, spot_price, time_to_expiry_years,
            open_interest_by_token, implied_volatility_by_token,
        ),
        momentum_direction=_intraday_momentum_direction(spot_bars),
        opening_range_breakout_direction=orb_signal.direction if orb_signal else None,
        time_window=expiry_day_time_window(now),
        implied_volatility_is_rich=_implied_volatility_is_rich(
            underlying_symbol, option_ladder, spot_price,
            implied_volatility_by_token, historical_atm_iv_by_date,
        ),
        near_max_pain=_near_max_pain(option_ladder, open_interest_by_token, spot_price),
    )
    decision = route_zero_dte_structure(router_inputs)

    if decision.structure is ZeroDteStructure.ABSTAIN:
        return _plan_from_abstention(underlying_symbol, decision.reason)

    built = _build_structure_legs(decision, option_ladder, spot_price, premium_by_token, lots)
    if built.abstain_reason is not None:
        return _plan_from_abstention(underlying_symbol, built.abstain_reason)

    return ZeroDtePlannedEntry(
        underlying_symbol=underlying_symbol,
        structure=decision.structure,
        direction=decision.direction,
        legs=built.legs,
        defined_risk_per_lot=built.defined_risk_per_lot,
        trigger=decision.trigger.value,
        reason=decision.reason,
    )


def _build_structure_legs(
    decision, option_ladder: list[Instrument], spot_price: float,
    premium_by_token: dict[int, float], lots: int,
) -> ZeroDteStructureLegs:
    if decision.structure is ZeroDteStructure.DIRECTIONAL_LONG_OPTION:
        return build_directional_long_option(
            option_ladder, spot_price, decision.direction, premium_by_token, lots
        )
    if decision.structure is ZeroDteStructure.LONG_STRADDLE:
        return build_long_straddle(option_ladder, spot_price, premium_by_token, lots)
    return build_short_premium_iron_fly(option_ladder, spot_price, premium_by_token, lots=lots)


def _plan_from_abstention(underlying_symbol: str, reason: str) -> ZeroDtePlannedEntry:
    return ZeroDtePlannedEntry(
        underlying_symbol=underlying_symbol,
        structure=ZeroDteStructure.ABSTAIN,
        direction=None,
        legs=(),
        defined_risk_per_lot=0.0,
        trigger="none",
        reason=reason,
    )
