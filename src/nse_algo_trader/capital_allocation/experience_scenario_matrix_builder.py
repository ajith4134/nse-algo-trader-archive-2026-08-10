"""Scenario-matrix data pipeline (research/163 §2/§4/§8 module 2; research/162 §9 thin-data honesty).

Turns RAW closed-trade history from `memory_reflection.experience_memory` into the empirical P&L
scenario matrix `r` (S scenarios × N candidates) the Mean-CVaR LP consumes, plus each candidate's mean
edge and the honest per-candidate real-sample count. Each candidate's scenarios are its own historical
`realized_return_fraction` samples, matched by a coarse key (strategy · instrument_kind · direction) so a
new candidate inherits the empirical distribution of trades that resemble it.

THIN-DATA REALITY (research/162 §9): with ~1 session-day of history the raw per-candidate samples are
few, so we BOOTSTRAP-resample each candidate's empirical distribution to a common scenario count S. This
is a real resampling of the observed distribution, not synthetic invention. Because the trades were not
jointly observed, the joint scenario matrix assumes cross-candidate INDEPENDENCE unless a co-movement key
is supplied — a documented modelling choice (Rule O), flagged so CVaR is never over-claimed. When the min
real-sample count is below the caller's floor the caller falls back to the parametric MV mode.

The `scenario_source` is a DI seam (Rule J): production passes the real `ExperienceMemory`; tests inject
a fake returning canned records. `build_scenario_matrix` is otherwise PURE.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from nse_algo_trader.capital_allocation.allocation_candidate import AllocationCandidate


@dataclass(frozen=True)
class ScenarioMatrix:
    """The empirical scenario matrix + the metadata the optimiser needs to pick a mode honestly."""

    returns_matrix: np.ndarray          # S × N, per-scenario return fractions (column j = candidate j)
    candidate_ids: tuple[str, ...]      # column order
    empirical_mu: np.ndarray            # N, per-candidate mean historical return (for reference/blend)
    min_real_sample_count: int          # the SMALLEST per-candidate raw sample count (data sufficiency)
    per_candidate_sample_counts: dict[str, int]
    assumed_independent: bool           # True → no co-movement key supplied; CVaR assumes independence


def scenario_key(candidate: AllocationCandidate) -> tuple[str, str, str]:
    """The coarse key a candidate's historical scenarios are matched on."""
    return (candidate.underlying, candidate.instrument_kind, str(candidate.direction).lower())


def _pnl_scale(records: list[dict]) -> float:
    """Robust self-scaling denominator for the realized-P&L → pseudo-return proxy: the median absolute
    P&L across records that lack a return fraction. Makes a typical scenario O(1) and comparable across
    candidates independent of account size (research/163 §4). Floored so we never divide by ~0."""
    magnitudes: list[float] = []
    for record in records:
        if record.get("realized_return_fraction") is not None:
            continue
        pnl = record.get("realized_pnl")
        if pnl is None or not np.isfinite(pnl):
            continue
        magnitudes.append(abs(float(pnl)))
    return float(np.median(magnitudes)) if magnitudes else 1.0


def _records_to_return_samples(records: list[dict]) -> dict[tuple[str, str, str], list[float]]:
    """Group raw experience dicts into return-scenario samples keyed by (identity, kind, direction).

    experience_memory keys trades by `strategy_tag`/`mechanism_name`, not underlying, so we match on the
    kind+direction axis (always present) and fall back to the strategy tag as the coarse identity — this
    is the resemblance class a fresh candidate inherits. Scenario value = `realized_return_fraction` when
    present; otherwise the realized-P&L PROXY `realized_pnl / median|pnl|` (a dimensionless self-scaled
    return, documented in research/163 §4 — the live `recent_closed_experiences` dicts carry P&L, not a
    return fraction). Non-finite values are dropped (Rule O.4).
    """
    scale = max(_pnl_scale(records), 1e-9)
    grouped: dict[tuple[str, str, str], list[float]] = {}
    for record in records:
        ret = record.get("realized_return_fraction")
        if ret is None:
            pnl = record.get("realized_pnl")
            if pnl is None or not np.isfinite(pnl):
                continue
            ret = float(pnl) / scale
        if not np.isfinite(ret):
            continue
        kind = str(record.get("instrument_kind", "")).strip()
        direction = str(record.get("direction", "")).strip().lower()
        identity = str(record.get("strategy_tag") or record.get("mechanism_name") or "").strip()
        key = (identity, kind, direction)
        grouped.setdefault(key, []).append(float(ret))
    return grouped


def _match_samples_for(candidate: AllocationCandidate,
                       grouped: dict[tuple[str, str, str], list[float]]) -> list[float]:
    """The historical return samples that resemble this candidate, widening the match if the exact
    (identity, kind, direction) bucket is empty: → (kind, direction) → (kind) → all. Wider matches are
    a real (if coarser) empirical prior, better than an empty scenario set."""
    kind = candidate.instrument_kind
    direction = str(candidate.direction).lower()
    exact = [s for (ident, k, d), samples in grouped.items()
             if k == kind and d == direction and ident == candidate.underlying for s in samples]
    if exact:
        return exact
    by_kind_dir = [s for (_, k, d), samples in grouped.items()
                   if k == kind and d == direction for s in samples]
    if by_kind_dir:
        return by_kind_dir
    by_kind = [s for (_, k, _d), samples in grouped.items() if k == kind for s in samples]
    if by_kind:
        return by_kind
    return [s for samples in grouped.values() for s in samples]


def build_scenario_matrix(candidates: list[AllocationCandidate], records: list[dict],
                          scenario_count: int = 512, rng_seed: int = 0) -> ScenarioMatrix:
    """RAW experience records → the S×N scenario matrix (bootstrap-resampled to `scenario_count`).

    `records` are experience_memory dicts (from `recent_closed_experiences`). Each candidate's column is
    a bootstrap resample of its matched historical return samples; a candidate that already carries its
    own `pnl_scenario_returns` uses those directly (still bootstrapped to S). Deterministic under
    `rng_seed` (no wall-clock randomness — reproducible verification).
    """
    if not candidates:
        return ScenarioMatrix(np.empty((0, 0)), (), np.empty(0), 0, {}, assumed_independent=True)

    grouped = _records_to_return_samples(records)
    rng = np.random.default_rng(rng_seed)
    columns: list[np.ndarray] = []
    empirical_mu: list[float] = []
    sample_counts: dict[str, int] = {}

    for candidate in candidates:
        samples = list(candidate.pnl_scenario_returns) or _match_samples_for(candidate, grouped)
        samples = [s for s in samples if np.isfinite(s)]
        sample_counts[candidate.candidate_id] = len(samples)
        if not samples:
            # No empirical basis at all: a degenerate zero-return, zero-variance column. The caller sees
            # min_real_sample_count == 0 and treats the whole solve as un-trustworthy (falls back / stays
            # advisory). Never invent a return.
            columns.append(np.zeros(scenario_count))
            empirical_mu.append(0.0)
            continue
        sample_array = np.asarray(samples, dtype=float)
        empirical_mu.append(float(sample_array.mean()))
        columns.append(rng.choice(sample_array, size=scenario_count, replace=True))

    returns_matrix = np.column_stack(columns) if columns else np.empty((scenario_count, 0))
    min_real = min(sample_counts.values()) if sample_counts else 0
    return ScenarioMatrix(
        returns_matrix=returns_matrix,
        candidate_ids=tuple(c.candidate_id for c in candidates),
        empirical_mu=np.asarray(empirical_mu, dtype=float),
        min_real_sample_count=min_real,
        per_candidate_sample_counts=sample_counts,
        assumed_independent=True,
    )
