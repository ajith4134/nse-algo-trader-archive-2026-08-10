"""Trunk XIII · EPISTEMICS — truth & uncertainty (the strongest cognitive trunk; docs/research/32-36).

Organs that keep the system's beliefs honest: calibration, assumption registry, skill-vs-luck court,
evidence provenance, forecasting tournament (built elsewhere), and — here — the epistemic-DEFENSE
branches: CONTRADICTION RESOLUTION (a global belief contradicted by regime-conditional evidence is
resolved toward the specific evidence) and DECEPTION/MISINFORMATION RESISTANCE (per-source
beta-reputation flags over-trusted-but-unreliable sources — the epistemic immune system).
"""

from __future__ import annotations

from nse_algo_trader.epistemics.contradiction_resolver import (
    Contradiction,
    ContradictionReport,
    resolve_contradictions,
)
from nse_algo_trader.epistemics.misinformation_resistance import (
    MisinfoReport,
    SourceCredibility,
    assess_source_credibility,
)

__all__ = [
    "Contradiction",
    "ContradictionReport",
    "MisinfoReport",
    "SourceCredibility",
    "assess_source_credibility",
    "resolve_contradictions",
]
