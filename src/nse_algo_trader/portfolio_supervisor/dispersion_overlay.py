"""Dispersion overlay — the cross-bot desk that only exists because bots 2 & 3 coexist (§8b, Rule P).

Index implied vol trades RICH to the weighted implied vol of its constituents, because index options price
in a correlation premium (constituents don't all move together, but the index sells insurance against them
all moving together). A **dispersion** trade harvests that premium: SHORT index-option vol + LONG a basket
of single-stock-option vol when implied correlation is high; the reverse when it is low. This is a
supervisor-level overlay — it reads the INDEX-OPT bot's index IV surface and the STOCK-OPT bot's per-name IV
surfaces (already computed by those bots) and proposes the paired structure. The whole is more than the
parts: neither bot alone can see the implied-correlation signal.

Implied correlation is backed out from ``ρ_implied = (σ_index² − Σ wᵢ² σᵢ²) / (Σᵢ≠ⱼ wᵢ wⱼ σᵢ σⱼ)`` (the
standard index-variance decomposition). The overlay abstains unless it has enough constituents and a
meaningful edge vs the realised-correlation baseline (carried state) — never a naked short-vol trade on a
thin or stale surface.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

_MIN_CONSTITUENTS = 5
_RICH_CORRELATION = 0.55  # implied ρ above this → index vol rich → SELL index / BUY constituents
_CHEAP_CORRELATION = 0.25  # below this → BUY index / SELL constituents
_MIN_HISTORY_FOR_EDGE = 30  # sessions of implied-ρ history before the edge is "earned"


@dataclass(frozen=True)
class DispersionSignal:
    """The dispersion desk's decision for one index vs its constituents."""

    index_underlying: str
    implied_correlation: float
    index_iv: float
    basket_iv: float  # weighted-average constituent IV
    n_constituents: int
    action: str  # "sell_index_buy_constituents" | "buy_index_sell_constituents" | "abstain"
    conviction: float  # [0,1]
    correlation_percentile: float | None  # vs the index's own implied-ρ history (None until earned)
    rationale: str
    field_notes: dict = field(default_factory=dict)


class ImpliedCorrelationStore:
    """Persists each index's rolling implied-correlation history — the edge baseline (carried state)."""

    def __init__(self, store_dir: Path):
        self._dir = Path(store_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def append_and_load(self, index_underlying: str, value: float) -> list[float]:
        path = self._dir / f"impl_corr_{index_underlying.replace('/', '_')}.json"
        history: list[float] = []
        if path.exists():
            try:
                history = json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                history = []
        history.append(float(value))
        history = history[-400:]
        path.write_text(json.dumps(history))
        return history


def implied_correlation(index_iv: float, weights: list[float], constituent_ivs: list[float]) -> float:
    """Back out implied average correlation from the index-variance decomposition. Clamped to [-1, 1]."""
    index_var = index_iv * index_iv
    own = sum((w * w) * (s * s) for w, s in zip(weights, constituent_ivs, strict=False))
    cross = 0.0
    n = len(weights)
    for i in range(n):
        for j in range(n):
            if i != j:
                cross += weights[i] * weights[j] * constituent_ivs[i] * constituent_ivs[j]
    if cross <= 1e-9:
        return 0.0
    return float(max(-1.0, min(1.0, (index_var - own) / cross)))


class DispersionOverlay:
    """Reads the two option bots' surfaces, backs out implied correlation, and proposes the dispersion trade."""

    def __init__(self, store: ImpliedCorrelationStore | None = None):
        self._store = store

    def assess(
        self,
        index_underlying: str,
        index_iv: float,
        constituent_ivs: dict[str, float],
        weights: dict[str, float] | None = None,
    ) -> DispersionSignal:
        names = [s for s, iv in constituent_ivs.items() if iv and iv > 0]
        if index_iv <= 0 or len(names) < _MIN_CONSTITUENTS:
            return DispersionSignal(index_underlying, 0.0, index_iv, 0.0, len(names), "abstain", 0.0, None,
                                    "too few constituents / no index IV")

        raw_w = [(weights or {}).get(s, 1.0) for s in names]
        total = sum(raw_w) or 1.0
        w = [x / total for x in raw_w]
        ivs = [constituent_ivs[s] for s in names]
        basket_iv = sum(wi * si for wi, si in zip(w, ivs, strict=False))
        rho = implied_correlation(index_iv, w, ivs)

        percentile: float | None = None
        earned = False
        if self._store is not None:
            history = self._store.append_and_load(index_underlying, rho)
            if len(history) >= _MIN_HISTORY_FOR_EDGE:
                percentile = float(sum(1 for h in history if h <= rho) / len(history))
                earned = True

        if rho >= _RICH_CORRELATION:
            action, conv = "sell_index_buy_constituents", min(1.0, (rho - _RICH_CORRELATION) / 0.3 + 0.4)
            rationale = f"implied ρ {rho:.2f} rich → sell index vol, buy constituent vol (harvest correlation premium)"
        elif rho <= _CHEAP_CORRELATION:
            action, conv = "buy_index_sell_constituents", min(1.0, (_CHEAP_CORRELATION - rho) / 0.3 + 0.4)
            rationale = f"implied ρ {rho:.2f} cheap → buy index vol, sell constituent vol"
        else:
            action, conv, rationale = "abstain", 0.0, f"implied ρ {rho:.2f} in the neutral band → abstain"

        # gate on an EARNED edge vs the index's own history where available (percentile confirms the extreme)
        not_extreme = percentile is not None and (
            (action.startswith("sell_index") and percentile < 0.7)
            or (action.startswith("buy_index") and percentile > 0.3)
        )
        if action != "abstain" and earned and not_extreme:
            action, conv, rationale = "abstain", 0.0, rationale + " — but not extreme vs history"

        return DispersionSignal(
            index_underlying, round(rho, 4), round(index_iv, 4), round(basket_iv, 4), len(names),
            action, round(conv, 4), percentile, rationale,
            field_notes={"earned": earned, "index_minus_basket_iv": round(index_iv - basket_iv, 4)},
        )
