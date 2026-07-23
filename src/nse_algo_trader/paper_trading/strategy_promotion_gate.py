"""Deflated-Sharpe-Ratio promotion gate (PLAN §5).

No strategy reaches live-capital candidacy on a good-looking backtest
alone. This gate applies Bailey & López de Prado's Probabilistic and
Deflated Sharpe Ratios: it asks "given how many strategy variants we
tried (multiple testing), and given these returns' skew/kurtosis, what is
the probability the true Sharpe exceeds the deflated benchmark?" — and
demands enough trades and a high confidence before it says PROMOTE.

Deliberately conservative: on thin evidence (few trades, one symbol) it
REJECTS, which is the correct behaviour. CPCV (Combinatorial Purged
Cross-Validation) is the companion gate and a later slice — it needs the
backtest-fold harness; the interface here is where it will plug in.
"""

import math
from dataclasses import dataclass
from enum import Enum
from statistics import NormalDist

_STANDARD_NORMAL = NormalDist()
_EULER_MASCHERONI = 0.5772156649015329


class StrategyPromotionOutcome(str, Enum):
    PROMOTE_TO_LIVE_CANDIDATE = "promote_to_live_candidate"
    REJECT_INSUFFICIENT_TRADES = "reject_insufficient_trades"
    REJECT_DEFLATED_SHARPE_TOO_LOW = "reject_deflated_sharpe_too_low"


@dataclass(frozen=True)
class StrategyPromotionConfig:
    minimum_trades: int = 30
    deflated_sharpe_confidence_threshold: float = 0.95


@dataclass(frozen=True)
class StrategyPromotionDecision:
    outcome: StrategyPromotionOutcome
    trade_count: int
    per_trade_sharpe_ratio: float
    probabilistic_sharpe_ratio: float  # PSR vs 0
    deflated_sharpe_ratio: float  # PSR vs the multiple-testing benchmark
    promoted: bool


def compute_sharpe_ratio(per_trade_returns: list[float]) -> float:
    if len(per_trade_returns) < 2:
        return 0.0
    mean_return = sum(per_trade_returns) / len(per_trade_returns)
    variance = sum((r - mean_return) ** 2 for r in per_trade_returns) / (
        len(per_trade_returns) - 1
    )
    standard_deviation = math.sqrt(variance)
    if standard_deviation == 0.0:
        return 0.0
    return mean_return / standard_deviation


def _sample_skewness(values: list[float], mean: float, std: float) -> float:
    n = len(values)
    if std == 0.0 or n < 3:
        return 0.0
    return sum(((v - mean) / std) ** 3 for v in values) / n


def _sample_kurtosis(values: list[float], mean: float, std: float) -> float:
    """Non-excess kurtosis (normal distribution = 3)."""
    n = len(values)
    if std == 0.0 or n < 4:
        return 3.0
    return sum(((v - mean) / std) ** 4 for v in values) / n


def compute_probabilistic_sharpe_ratio(
    per_trade_returns: list[float], benchmark_sharpe_ratio: float = 0.0
) -> float:
    """P(true Sharpe > benchmark), correcting for skew/kurtosis and sample
    size (Bailey & López de Prado)."""
    observation_count = len(per_trade_returns)
    if observation_count < 2:
        return 0.0
    estimated_sharpe = compute_sharpe_ratio(per_trade_returns)
    mean_return = sum(per_trade_returns) / observation_count
    standard_deviation = math.sqrt(
        sum((r - mean_return) ** 2 for r in per_trade_returns)
        / (observation_count - 1)
    )
    skewness = _sample_skewness(per_trade_returns, mean_return, standard_deviation)
    kurtosis = _sample_kurtosis(per_trade_returns, mean_return, standard_deviation)

    denominator = math.sqrt(
        1.0
        - skewness * estimated_sharpe
        + ((kurtosis - 1.0) / 4.0) * estimated_sharpe**2
    )
    if denominator == 0.0:
        return 0.0
    psr_z = (
        (estimated_sharpe - benchmark_sharpe_ratio)
        * math.sqrt(observation_count - 1)
    ) / denominator
    return _STANDARD_NORMAL.cdf(psr_z)


def estimate_deflated_sharpe_benchmark(
    sharpe_std_across_trials: float, number_of_trials: int
) -> float:
    """The expected MAXIMUM Sharpe from `number_of_trials` random trials —
    the bar a real strategy must clear to not be a multiple-testing
    artifact."""
    if number_of_trials < 2 or sharpe_std_across_trials <= 0.0:
        return 0.0
    return sharpe_std_across_trials * (
        (1.0 - _EULER_MASCHERONI)
        * _STANDARD_NORMAL.inv_cdf(1.0 - 1.0 / number_of_trials)
        + _EULER_MASCHERONI
        * _STANDARD_NORMAL.inv_cdf(1.0 - 1.0 / (number_of_trials * math.e))
    )


def compute_deflated_sharpe_ratio(
    per_trade_returns: list[float],
    sharpe_std_across_trials: float,
    number_of_trials: int,
) -> float:
    benchmark = estimate_deflated_sharpe_benchmark(
        sharpe_std_across_trials, number_of_trials
    )
    return compute_probabilistic_sharpe_ratio(per_trade_returns, benchmark)


def evaluate_strategy_for_promotion(
    per_trade_returns: list[float],
    number_of_strategy_trials: int,
    sharpe_std_across_trials: float,
    config: StrategyPromotionConfig = StrategyPromotionConfig(),
) -> StrategyPromotionDecision:
    trade_count = len(per_trade_returns)
    sharpe = compute_sharpe_ratio(per_trade_returns)
    psr = compute_probabilistic_sharpe_ratio(per_trade_returns)
    dsr = compute_deflated_sharpe_ratio(
        per_trade_returns, sharpe_std_across_trials, number_of_strategy_trials
    )

    if trade_count < config.minimum_trades:
        outcome = StrategyPromotionOutcome.REJECT_INSUFFICIENT_TRADES
    elif dsr < config.deflated_sharpe_confidence_threshold:
        outcome = StrategyPromotionOutcome.REJECT_DEFLATED_SHARPE_TOO_LOW
    else:
        outcome = StrategyPromotionOutcome.PROMOTE_TO_LIVE_CANDIDATE

    return StrategyPromotionDecision(
        outcome=outcome,
        trade_count=trade_count,
        per_trade_sharpe_ratio=sharpe,
        probabilistic_sharpe_ratio=psr,
        deflated_sharpe_ratio=dsr,
        promoted=(outcome is StrategyPromotionOutcome.PROMOTE_TO_LIVE_CANDIDATE),
    )
