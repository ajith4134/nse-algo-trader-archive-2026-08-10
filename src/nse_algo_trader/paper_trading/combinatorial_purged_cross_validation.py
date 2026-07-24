"""Combinatorial Purged Cross-Validation (CPCV) — the DSR gate's companion (PLAN §5).

A single backtest gives one Sharpe; that one number is easy to overfit to.
CPCV (Bailey & López de Prado, *Advances in Financial Machine Learning*)
splits the return series into N contiguous groups, then forms every
combination of k test groups — C(N,k) out-of-sample "backtest paths" — and
measures a Sharpe on each. The spread of those path Sharpes is an empirical
estimate of how much the Sharpe moves under resampling, which is exactly
the variance-of-trials the Deflated Sharpe Ratio needs to deflate against.
An embargo drops the groups adjacent to each test group so information
doesn't leak across the train/test boundary.

Reference implementation surveyed: `purgedcv` (MIT) — it implements
`CombinatorialPurgedCV` as an sklearn splitter (for model cross-validation
over features/labels). Our need is different (a distribution over a fixed
strategy's return series), so this is a compact adaptation of the same
algorithm rather than a vendoring of the sklearn splitter.
"""

import itertools
from dataclasses import dataclass
from statistics import pstdev

from nse_algo_trader.paper_trading.strategy_promotion_gate import (
    StrategyPromotionConfig,
    StrategyPromotionDecision,
    compute_sharpe_ratio,
    evaluate_strategy_for_promotion,
)


@dataclass(frozen=True)
class CpcvConfig:
    group_count: int = 6  # N contiguous groups the series is split into
    test_group_count: int = 2  # k test groups per combination
    embargo_group_count: int = 1  # groups adjacent to a test group excluded from its path


def partition_returns_into_groups(
    per_period_returns: list[float], group_count: int
) -> list[list[float]]:
    if group_count < 2 or len(per_period_returns) < group_count:
        raise ValueError("need at least `group_count` returns and group_count >= 2")
    base_size, remainder = divmod(len(per_period_returns), group_count)
    groups: list[list[float]] = []
    cursor = 0
    for group_index in range(group_count):
        this_size = base_size + (1 if group_index < remainder else 0)
        groups.append(per_period_returns[cursor : cursor + this_size])
        cursor += this_size
    return groups


def compute_cpcv_backtest_path_sharpes(
    per_period_returns: list[float], config: CpcvConfig = CpcvConfig()
) -> list[float]:
    """One out-of-sample Sharpe per combination of test groups.

    The OOS path for a combination is the concatenation of ALL its test
    groups' realized returns. Purge/embargo (López de Prado) removes TRAINING
    observations near a test boundary to stop label leakage — but this is a
    label-free realized-returns series with no per-path model training, so
    there is nothing to purge and the embargo must NOT shrink the OOS path
    itself (research/41 fix: it previously dropped adjacent test groups,
    corrupting the trial distribution the Deflated-Sharpe gate deflates
    against). `embargo_group_count` is retained for a future label-based CV.
    """
    groups = partition_returns_into_groups(per_period_returns, config.group_count)
    path_sharpes: list[float] = []
    for test_group_indices in itertools.combinations(
        range(config.group_count), config.test_group_count
    ):
        path_returns = [
            r for group_index in test_group_indices for r in groups[group_index]
        ]
        if len(path_returns) >= 2:
            path_sharpes.append(compute_sharpe_ratio(path_returns))
    return path_sharpes


def evaluate_strategy_with_cpcv_gate(
    per_period_returns: list[float],
    cpcv_config: CpcvConfig = CpcvConfig(),
    promotion_config: StrategyPromotionConfig = StrategyPromotionConfig(),
) -> StrategyPromotionDecision:
    """Runs CPCV to estimate the trial-Sharpe distribution empirically, then
    deflates against it via the Deflated-Sharpe promotion gate — so the
    multiple-testing correction uses real resampled paths, not an assumed
    variance."""
    path_sharpes = compute_cpcv_backtest_path_sharpes(per_period_returns, cpcv_config)
    number_of_paths = max(len(path_sharpes), 2)
    sharpe_std_across_paths = pstdev(path_sharpes) if len(path_sharpes) > 1 else 0.0
    return evaluate_strategy_for_promotion(
        per_period_returns,
        number_of_strategy_trials=number_of_paths,
        sharpe_std_across_trials=sharpe_std_across_paths,
        config=promotion_config,
    )
