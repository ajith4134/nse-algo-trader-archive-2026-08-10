"""Value-drift detection (Trunk XIV AXIOLOGY; research/153). PURE — no I/O.

Watches whether the system's REALIZED behaviour is drifting from its stated values: it splits the
realized-return series into an earlier BASELINE window and a RECENT window and flags drift when a
recent RISK component (volatility / max-drawdown / tail CVaR) exceeds the baseline by a threshold —
i.e. the system is taking more risk than its values sanction. A value-alignment CONSCIENCE signal (the
queued consumer: trim/defer when values drift). Reuses the risk measures from `explicit_utility_function`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from nse_algo_trader.axiology.explicit_utility_function import _cvar_tail_loss, _max_drawdown

import statistics

_DEFAULT_DRIFT_THRESHOLD = 0.25   # a recent risk metric > baseline × (1 + 0.25) is drift
_MIN_WINDOW = 10                   # need at least this many trades per window to judge


@dataclass(frozen=True)
class RiskProfile:
    volatility: float
    max_drawdown: float
    tail_loss_cvar5: float


@dataclass(frozen=True)
class ValueDriftReport:
    is_drifting: bool
    drifting_components: tuple = field(default_factory=tuple)  # names of the drifted risk metrics
    baseline: RiskProfile | None = None
    recent: RiskProfile | None = None
    sample_size: int = 0
    summary: str = ""


def _risk_profile(returns) -> RiskProfile:
    return RiskProfile(
        volatility=statistics.pstdev(returns) if len(returns) > 1 else 0.0,
        max_drawdown=_max_drawdown(returns),
        tail_loss_cvar5=_cvar_tail_loss(returns),
    )


def detect_value_drift(returns, recent_fraction: float = 0.4,
                       drift_threshold: float = _DEFAULT_DRIFT_THRESHOLD) -> ValueDriftReport:
    """Compare the recent window's risk profile against the earlier baseline. Ordered oldest→newest."""
    returns = [float(r) for r in returns]
    recent_n = int(len(returns) * recent_fraction)
    baseline_n = len(returns) - recent_n
    if recent_n < _MIN_WINDOW or baseline_n < _MIN_WINDOW:
        return ValueDriftReport(
            is_drifting=False, sample_size=len(returns),
            summary=f"insufficient history for a drift verdict (need ≥{_MIN_WINDOW}/window)")

    baseline = _risk_profile(returns[:baseline_n])
    recent = _risk_profile(returns[baseline_n:])

    drifted = []
    for name, base_val, recent_val in (
        ("volatility", baseline.volatility, recent.volatility),
        ("max_drawdown", baseline.max_drawdown, recent.max_drawdown),
        ("tail_cvar5", baseline.tail_loss_cvar5, recent.tail_loss_cvar5),
    ):
        if base_val > 0 and recent_val > base_val * (1.0 + drift_threshold):
            drifted.append(name)

    is_drifting = bool(drifted)
    if is_drifting:
        summary = ("VALUE DRIFT — recent risk exceeds the stated values on: " + ", ".join(drifted)
                   + f" (recent vol {recent.volatility:.2%} vs baseline {baseline.volatility:.2%}, "
                   f"maxDD {recent.max_drawdown:.2%} vs {baseline.max_drawdown:.2%})")
    else:
        summary = (f"values stable — recent risk within {drift_threshold:.0%} of baseline "
                   f"(vol {recent.volatility:.2%} vs {baseline.volatility:.2%})")
    return ValueDriftReport(
        is_drifting=is_drifting, drifting_components=tuple(drifted), baseline=baseline, recent=recent,
        sample_size=len(returns), summary=summary)
