"""Is this underlying's implied volatility RICH or CHEAP relative to its own history?

The decision this changes: whether an option arm SELLS premium (IV rich) or BUYS it (IV cheap).
Absolute IV is meaningless across underlyings — 14% is expensive for NIFTY and cheap for a mid-cap.
Both measures below normalise IV against the instrument's own past.

Two standard, deliberately different statistics (tastytrade definitions):

* **IV Rank** — where today sits in the [min, max] RANGE of the lookback.
      IVR = 100 x (iv_now - iv_min) / (iv_max - iv_min)
  Sensitive to outliers: one panic spike sets `iv_max` for a year and crushes every later reading.

* **IV Percentile** — the FRACTION OF DAYS the lookback spent below today.
      IVP = 100 x count(iv_day < iv_now) / count(days)
  Robust to outliers, and usually the more honest of the two. Both are reported because they
  disagree in an informative way: high IVR with low IVP means "near the highs, but the highs were
  one spike".

## The abstention that matters most

A percentile is only meaningful if every observation in the window is comparable. On 2024-11-20,
SEBI's one-weekly-expiry-per-exchange framework removed weekly expiries from BANKNIFTY, FINNIFTY and
MIDCPNIFTY. Weekly and monthly ATM IV are **not the same quantity** — different time-to-expiry,
different term-structure point. A 252-day lookback spanning that date is comparing weekly IV against
monthly IV and calling the difference "rank".

So this module **abstains with a reason** rather than emitting a confident-looking number over a
structural break. NIFTY is unaffected (it kept its weeklies) and NIFTYNXT50 is unaffected (it
launched monthly-only in April 2024 and never transitioned) — only the three that actually changed
cadence are gated.

See `docs/research/b18_index_options_ensemble_SPEC_2026-07-27.md` §2 and
`b18_index_options_ensemble_research_2026-07-27.md` §1.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

#: The date SEBI's one-weekly-index-per-exchange framework took effect and weekly expiries were
#: withdrawn from the indices below. Source: SEBI/HO/MRD/TPD-1/P/CIR/2024/132 (1 Oct 2024),
#: effective 2024-11-20; recorded in the B18 research pass.
WEEKLY_EXPIRY_WITHDRAWAL_DATE = date(2024, 11, 20)

#: Underlyings whose ATM-IV series is NOT comparable across `WEEKLY_EXPIRY_WITHDRAWAL_DATE`.
#: NIFTY is absent because it KEPT its weeklies; NIFTYNXT50 is absent because it launched
#: monthly-only (April 2024) and never transitioned. Only these three actually changed cadence.
UNDERLYINGS_WITH_EXPIRY_CADENCE_BREAK: frozenset[str] = frozenset(
    {"BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"}
)

#: Minimum observations before either statistic means anything. Below this the window is too short
#: for a percentile to be more than noise (Rule Q: gate ACTIVATION, never weaken the function).
MINIMUM_OBSERVATIONS_FOR_RANK = 60

#: Standard lookback (one trading year).
DEFAULT_LOOKBACK_TRADING_DAYS = 252


@dataclass(frozen=True)
class ImpliedVolatilityRanking:
    """Where today's IV sits in this underlying's own history — or why we refuse to say.

    `abstained_reason` is not decoration. An arm that receives a fabricated rank sizes a real trade
    on it; an arm that receives an abstention stands aside honestly. Callers MUST check
    `is_usable` before reading the numbers.
    """

    underlying_symbol: str
    implied_volatility_rank: float | None
    implied_volatility_percentile: float | None
    observation_count: int
    abstained_reason: str | None = None

    @property
    def is_usable(self) -> bool:
        return self.abstained_reason is None

    @property
    def is_rich(self) -> bool:
        """Premium-selling condition — both measures agree IV is historically high.

        Requiring BOTH guards against the single-spike artefact that inflates IV Rank alone.
        """
        return (
            self.is_usable
            and (self.implied_volatility_rank or 0.0) >= 50.0
            and (self.implied_volatility_percentile or 0.0) >= 50.0
        )

    @property
    def is_cheap(self) -> bool:
        """Premium-buying condition — both measures agree IV is historically low."""
        return (
            self.is_usable
            and (self.implied_volatility_rank or 100.0) <= 20.0
            and (self.implied_volatility_percentile or 100.0) <= 20.0
        )


def _abstain(underlying_symbol: str, observation_count: int, reason: str):
    return ImpliedVolatilityRanking(
        underlying_symbol=underlying_symbol,
        implied_volatility_rank=None,
        implied_volatility_percentile=None,
        observation_count=observation_count,
        abstained_reason=reason,
    )


def lookback_spans_expiry_cadence_break(
    underlying_symbol: str,
    observation_dates: list[date],
) -> bool:
    """Does this underlying's window straddle the date its expiry cadence changed?

    True only when the underlying actually transitioned AND the window contains observations from
    both sides of the break — a window entirely after the break is perfectly comparable.
    """
    if underlying_symbol not in UNDERLYINGS_WITH_EXPIRY_CADENCE_BREAK:
        return False
    if not observation_dates:
        return False
    return (
        min(observation_dates) < WEEKLY_EXPIRY_WITHDRAWAL_DATE
        <= max(observation_dates)
    )


def rank_implied_volatility(
    underlying_symbol: str,
    current_implied_volatility: float,
    historical_implied_volatility_by_date: dict[date, float],
    lookback_trading_days: int = DEFAULT_LOOKBACK_TRADING_DAYS,
    minimum_observations: int = MINIMUM_OBSERVATIONS_FOR_RANK,
) -> ImpliedVolatilityRanking:
    """Rank today's IV against this underlying's own recent history.

    Pure — no I/O, no clock. Abstains (never guesses) when the window is too short, straddles the
    expiry-cadence break, or is degenerate.
    """
    if current_implied_volatility is None or current_implied_volatility <= 0.0:
        return _abstain(underlying_symbol, 0, "no usable current implied volatility")

    dated_observations = sorted(
        (observed_on, iv)
        for observed_on, iv in historical_implied_volatility_by_date.items()
        if iv is not None and iv > 0.0
    )[-lookback_trading_days:]
    observation_count = len(dated_observations)

    if observation_count < minimum_observations:
        return _abstain(
            underlying_symbol, observation_count,
            f"only {observation_count} IV observations; need {minimum_observations} "
            "before a rank means anything",
        )

    observation_dates = [observed_on for observed_on, _ in dated_observations]
    if lookback_spans_expiry_cadence_break(underlying_symbol, observation_dates):
        return _abstain(
            underlying_symbol, observation_count,
            f"{underlying_symbol} lost weekly expiries on "
            f"{WEEKLY_EXPIRY_WITHDRAWAL_DATE.isoformat()}; this window spans that break, so it "
            "compares weekly IV against monthly IV — not a like-for-like rank",
        )

    observed_ivs = [iv for _, iv in dated_observations]
    lowest, highest = min(observed_ivs), max(observed_ivs)
    if highest <= lowest:
        return _abstain(
            underlying_symbol, observation_count,
            "IV history is degenerate (no range) — a rank would divide by zero",
        )

    rank = 100.0 * (current_implied_volatility - lowest) / (highest - lowest)
    percentile = 100.0 * sum(
        1 for iv in observed_ivs if iv < current_implied_volatility
    ) / observation_count

    return ImpliedVolatilityRanking(
        underlying_symbol=underlying_symbol,
        # Today's IV can sit outside the historical range (a new high/low); clamping keeps the
        # statistic interpretable as a position-in-range without hiding that it is at an extreme.
        implied_volatility_rank=max(0.0, min(rank, 100.0)),
        implied_volatility_percentile=percentile,
        observation_count=observation_count,
        abstained_reason=None,
    )
