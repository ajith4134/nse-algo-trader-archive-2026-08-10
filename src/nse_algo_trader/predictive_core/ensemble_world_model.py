"""Ensemble world-models (Trunk IX; research/134) — combine forecasts, measure disagreement.

Rather than trust one mechanism's forecast, combine the per-mechanism win-probabilities into ONE
ensemble prediction (n-weighted mean) and measure the DISAGREEMENT (variance across members) — the
epistemic/model uncertainty. High disagreement = the world-models don't agree = the system should act
with less confidence. Sourcing (research/133): no fitting library at any weight (sklearn needs fitted
estimators, BayesBlend needs MCMC, `properscoring` abandoned) → built bespoke on stdlib `statistics`.
PURE (no I/O).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EnsembleForecast:
    ensemble_prediction: float   # n-weighted mean predicted win-probability across mechanisms
    disagreement: float          # n-weighted standard deviation across members (model uncertainty)
    member_count: int
    high_disagreement: bool
    summary: str = ""


def build_ensemble_forecast(
    board: list, high_disagreement_threshold: float = 0.15
) -> EnsembleForecast:
    """Combine the per-mechanism forecasts into an ensemble prediction + its disagreement. `board` =
    CalibrationBoardRow-like (`.experiment_count`, `.predicted_win_rate`)."""
    members = [(r.predicted_win_rate, r.experiment_count) for r in board if r.experiment_count > 0]
    if not members:
        return EnsembleForecast(0.0, 0.0, 0, False, "no members to ensemble")

    total_n = sum(n for _, n in members)
    mean = sum(p * n for p, n in members) / total_n
    variance = sum(n * (p - mean) ** 2 for p, n in members) / total_n
    disagreement = variance ** 0.5
    high = disagreement >= high_disagreement_threshold and len(members) >= 2

    summary = (
        f"ensemble prediction {mean:.0%} across {len(members)} world-models; disagreement "
        f"±{disagreement:.0%}"
        + (" — HIGH (models disagree; act with less confidence)" if high else " (models broadly agree)")
    )
    return EnsembleForecast(
        ensemble_prediction=mean, disagreement=disagreement, member_count=len(members),
        high_disagreement=high, summary=summary,
    )
