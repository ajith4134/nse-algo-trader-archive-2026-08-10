"""Trunk IX · PREDICTIVE CORE / ACTIVE INFERENCE — the currency (docs/research/32-36).

Active-inference organs over the bot's prediction stream: it already has the prequential forecast
score (per-trade pre-mortem + world-model scoreboard elsewhere). Here:
- SURPRISE / FREE-ENERGY monitor — the agent minimises surprise (−log p of outcomes = free energy);
  monitor per-mechanism Bayesian surprise + flag the anomalously-surprising mechanism (world-model
  failing) via a compact Page-Hinkley change detector.
- ENSEMBLE WORLD-MODELS — combine the per-mechanism forecasts into one ensemble prediction + measure
  disagreement (variance = model uncertainty).
"""

from __future__ import annotations

from nse_algo_trader.predictive_core.surprise_monitor import (
    SurpriseReport,
    monitor_surprise,
)
from nse_algo_trader.predictive_core.ensemble_world_model import (
    EnsembleForecast,
    build_ensemble_forecast,
)

__all__ = [
    "EnsembleForecast",
    "SurpriseReport",
    "build_ensemble_forecast",
    "monitor_surprise",
]
