"""World-model scoreboard — trade-INDEPENDENT forecast quality (Layer 7.5 slice 4; research/108).

Is the bot's model of the MARKET good, separate from whether it made money? Two trade-independent
reads from memory:
  * FORECAST SKILL — the prequential log-loss (bits) / Brier over the bot's win-probability
    forecasts (a proper score; < 1.0 bit beats an always-0.5 forecaster). This grades PREDICTIONS,
    not P&L.
  * REGIME-MODEL RESOLUTION — the spread of hit-rates across the bot's market-regime labels. If
    trending / range / indecisive sessions have materially different outcomes, the regime model
    carries real information; if identical, the label is noise.
The bot's world model is "informative" when its forecasts beat a coin-flip AND its regime labels
resolve. A bot can make money by luck with a poor model, or have a sound model with a thin edge —
this isolates the model. PURE (no I/O); reads only the injected `ExperienceMemory`.
"""

from __future__ import annotations

from dataclasses import dataclass

_COIN_FLIP_LOG_LOSS_BITS = 1.0
_INFORMATIVE_REGIME_RESOLUTION = 0.05  # ≥5pp hit-rate spread across regimes = informative


@dataclass(frozen=True)
class WorldModelScoreboard:
    """Trade-independent world-model quality. `regime_resolution` is the max−min hit-rate across
    regimes; `world_model_informative` requires beating a coin-flip forecaster AND a resolving
    regime model. Any field is None when there isn't enough data to score it."""

    forecast_experiments: int
    forecast_log_loss_bits: float | None
    forecast_brier: float | None
    regime_resolution: float | None
    world_model_informative: bool | None
    verdict: str


def score_world_model(experience_memory) -> WorldModelScoreboard:
    """Grade the bot's trade-independent forecasts: prequential forecast skill + regime-model
    resolution → an 'informative model?' verdict."""
    forecast = experience_memory.prequential_forecast_score()
    regimes = experience_memory.calibration_by_market_regime(minimum_experiments=1)
    hit_rates = [c.hit_rate for c in regimes if c.hit_rate is not None]
    resolution = (max(hit_rates) - min(hit_rates)) if len(hit_rates) >= 2 else None

    log_loss = forecast.mean_log_loss_bits
    beats_coin_flip = None if log_loss is None else log_loss < _COIN_FLIP_LOG_LOSS_BITS
    regime_informative = (
        None if resolution is None else resolution >= _INFORMATIVE_REGIME_RESOLUTION
    )

    if beats_coin_flip is None:
        informative: bool | None = None
    elif regime_informative is None:
        informative = beats_coin_flip
    else:
        informative = beats_coin_flip and regime_informative

    return WorldModelScoreboard(
        forecast_experiments=forecast.experiment_count,
        forecast_log_loss_bits=log_loss,
        forecast_brier=forecast.mean_brier,
        regime_resolution=resolution,
        world_model_informative=informative,
        verdict=_verdict(log_loss, beats_coin_flip, resolution, informative),
    )


def _verdict(
    log_loss: float | None,
    beats_coin_flip: bool | None,
    resolution: float | None,
    informative: bool | None,
) -> str:
    if log_loss is None:
        return "gathering: no graded forecasts yet"
    skill = (
        f"forecast {log_loss:.2f} bits ({'beats' if beats_coin_flip else 'below'} a coin-flip)"
    )
    regime = (
        "regime model not yet resolvable" if resolution is None
        else f"regime hit-rate spread {resolution:.0%} "
             f"({'informative' if resolution >= _INFORMATIVE_REGIME_RESOLUTION else 'noise'})"
    )
    stance = (
        "world model INFORMATIVE" if informative
        else "world model NOT yet informative"
    )
    return f"{stance}: {skill}; {regime}"
