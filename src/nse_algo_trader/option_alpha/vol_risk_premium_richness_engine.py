"""Vol-Risk-Premium richness engine — the cross-sectional "is option premium rich or cheap?" signal.

Replaces the perpetually-``None`` IV-rank gate (needs ~60 sessions of per-name ATM-IV history the store does
not have) with a signal built from the **Variance Risk Premium** the regime engine already produces every
cycle: ``VRP = ATM_IV − forecast_realized_vol``. VRP needs no long IV history, so premium-harvest structures
(iron condor / strangle / credit spread) — the Θ engine that earns in FLAT markets — can finally fire.

The engine is a Bayesian-shrinkage percentile estimator over TWO axes (SOTA analog: Qlib cross-sectional
factor normalisation + James-Stein shrinkage):

* **time-series** — where a name's current VRP sits in its OWN rolling VRP history (carried state);
* **cross-section** — where it sits among ALL names this cycle (the whole universe ranked against itself).

They are blended by a shrinkage weight ``w = n/(n+k)`` in the name's history length ``n`` — a thin name leans
on the cross-section, a mature name on its own history. The output ``richness ∈ [0,1]`` is a percentile by
construction, so the downstream rich/cheap thresholds are self-calibrating (a tercile cut is a data-derived
quantile, not a magic constant).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy import stats

_HISTORY_TRIM = 400  # ~ >1y of sessions kept per name (carried state)
_SHRINKAGE_K = 20.0  # history length at which time-series and cross-section are weighted equally
_MIN_CROSS_SECTION = 3  # need a few names before a cross-sectional percentile means anything


@dataclass(frozen=True)
class VolRichnessInput:
    """Per-underlying inputs for one cycle (pulled from the regime engine + IV surface)."""

    underlying: str
    trade_date: str
    variance_risk_premium: float | None  # ATM_IV − forecast RV (None if IV unavailable)
    realized_vol: float


@dataclass(frozen=True)
class VolRichnessState:
    """The decision-grade richness verdict for one underlying."""

    underlying: str
    vrp: float | None
    realized_vol: float
    richness: float | None  # [0,1] percentile — high = premium RICH (sell), low = CHEAP (buy vol)
    time_series_percentile: float | None
    cross_section_percentile: float | None
    n_history: int
    maturity: str  # "gathering" | "earned" (per-name history sufficiency)
    basis: str

    def is_rich(self, high: float = 0.66) -> bool:
        """Premium is rich enough to favour NET SELLING (top-tercile richness by default)."""
        return self.richness is not None and self.richness >= high

    def is_cheap(self, low: float = 0.34) -> bool:
        """Premium is cheap enough to favour BUYING vol (bottom-tercile richness by default)."""
        return self.richness is not None and self.richness <= low


class VrpHistoryStore:
    """Persists each underlying's rolling VRP + realized-vol history — the carried state richness is measured against."""

    def __init__(self, store_dir: Path):
        self._dir = Path(store_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, underlying: str) -> Path:
        safe = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in str(underlying)) or "_"
        return self._dir / f"vrp_{safe}.json"

    def append_and_load(self, underlying: str, trade_date: str, vrp: float, realized_vol: float) -> list[float]:
        """Idempotently record today's VRP (keyed by date) and return the trimmed chronological VRP series."""
        path = self._path(underlying)
        history: dict[str, dict] = {}
        if path.exists():
            try:
                history = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError):
                history = {}
        history[trade_date] = {"vrp": float(vrp), "rv": float(realized_vol)}
        trimmed = dict(sorted(history.items())[-_HISTORY_TRIM:])
        path.write_text(json.dumps(trimmed))
        return [row["vrp"] for _, row in sorted(trimmed.items())]


class VolRiskPremiumRichnessEngine:
    """Serves a cross-sectional + time-series VRP richness percentile per underlying (carried state)."""

    def __init__(self, store: VrpHistoryStore, shrinkage_k: float = _SHRINKAGE_K):
        self._store = store
        self._k = shrinkage_k

    def assess_universe(self, inputs: list[VolRichnessInput]) -> dict[str, VolRichnessState]:
        """One cross-sectional pass: update each name's history, rank cross-sectionally, blend → richness."""
        priced = [i for i in inputs if i.variance_risk_premium is not None]
        cross_vrps = np.asarray(
            [float(v) for i in priced if (v := i.variance_risk_premium) is not None], dtype=np.float64)
        have_cross = len(priced) >= _MIN_CROSS_SECTION

        out: dict[str, VolRichnessState] = {}
        for item in inputs:
            if item.variance_risk_premium is None:
                out[item.underlying] = VolRichnessState(
                    item.underlying, None, item.realized_vol, None, None, None, 0, "gathering",
                    "no VRP (implied vol unavailable)")
                continue
            vrp = float(item.variance_risk_premium)
            history = self._store.append_and_load(item.underlying, item.trade_date, vrp, item.realized_vol)
            n = len(history)

            p_ts = self._time_series_percentile(vrp, history)
            p_cs = float(stats.percentileofscore(cross_vrps, vrp, kind="mean") / 100.0) if have_cross else None
            richness = self._shrink(p_ts, p_cs, n)
            maturity = "earned" if n >= self._k else "gathering"
            basis = self._basis(p_ts, p_cs, n)
            out[item.underlying] = VolRichnessState(
                item.underlying, vrp, item.realized_vol, richness, p_ts, p_cs, n, maturity, basis)
        return out

    @staticmethod
    def _time_series_percentile(vrp: float, history: list[float]) -> float | None:
        # need ≥2 distinct points for a meaningful self-percentile; 1 point → undefined (lean on cross-section)
        if len(history) < 2:
            return None
        return float(stats.percentileofscore(np.array(history, dtype=float), vrp, kind="mean") / 100.0)

    def _shrink(self, p_ts: float | None, p_cs: float | None, n: int) -> float | None:
        """Blend the two percentiles by history-length shrinkage; fall back to whichever exists."""
        if p_ts is None and p_cs is None:
            return None
        if p_ts is None:
            return p_cs
        if p_cs is None:
            return p_ts
        w = n / (n + self._k)  # more own history → trust the time-series percentile more
        return float(w * p_ts + (1.0 - w) * p_cs)

    @staticmethod
    def _basis(p_ts: float | None, p_cs: float | None, n: int) -> str:
        if p_ts is None and p_cs is not None:
            return f"cross-section only (n={n} own history)"
        if p_ts is not None and p_cs is None:
            return f"time-series only (n={n})"
        return f"shrinkage blend (n={n})"
