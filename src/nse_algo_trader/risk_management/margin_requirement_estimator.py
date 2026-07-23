"""Conservative margin-requirement estimates for v1 position types.

Deliberately simple upper-bound models (`docs/research/07` §D.3): the
exchange's real SPAN+exposure numbers come from the broker's margin API
in Layer 6 — until then Risk sizes positions against estimates that are
designed to only ever OVER-state the requirement:

- Recognized defined-risk spread: margin benefit means the true
  requirement is at most around the structural max loss — we charge the
  full structural max loss plus a safety buffer.
- Intraday cash equity: SEBI peak-margin floor is 20% of notional (max
  5x intraday leverage) — we charge a configurable fraction that
  defaults to a stricter 25%.

Naked short options have NO estimator on purpose: v1 rejects them
outright, so pricing their margin would only invite their use.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class MarginEstimateConfig:
    defined_risk_spread_safety_buffer_fraction: float = 0.10
    intraday_cash_margin_fraction: float = 0.25  # stricter than SEBI's 20% floor


def estimate_defined_risk_spread_margin(
    worst_case_structural_loss: float,
    config: MarginEstimateConfig = MarginEstimateConfig(),
) -> float:
    return worst_case_structural_loss * (
        1.0 + config.defined_risk_spread_safety_buffer_fraction
    )


def estimate_intraday_cash_margin(
    entry_price: float,
    share_quantity: int,
    config: MarginEstimateConfig = MarginEstimateConfig(),
) -> float:
    return entry_price * share_quantity * config.intraday_cash_margin_fraction
