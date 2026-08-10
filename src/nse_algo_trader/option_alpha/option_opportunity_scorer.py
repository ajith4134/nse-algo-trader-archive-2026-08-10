"""Option Opportunity Scorer — scores each profit engine's edge per name, picks the winner, ranks the universe.

Replaces the selectors' FIRST-MATCH branch priority (whichever regime condition matched first won, by
position not by strength) with a principled, scored, cross-sectional choice: for every underlying, score all
five option profit-engines, deploy the one with the strongest edge, and rank the whole universe so the best
opportunities lead. SOTA analog: Qlib's cross-sectional factor model producing a per-instrument selection
score.

The five engines (the independent ways options earn — see the profit taxonomy):
  Θ THETA   — premium harvest (flat/range markets): rich premium + calm regime → sell.
  Δ DELTA   — directional (trend): a confident directional read → capped-risk debit.
  ν VEGA    — long vol (cheap premium expecting expansion): buy vol.
  Γ GAMMA   — realized-movement / 0DTE convexity near expiry.
  RV RELVAL — skew / term-structure relative value.

Each engine score ∈ [0,1] is built from ALREADY-NORMALIZED inputs (percentile richness, conviction ∈ [0,1],
bounded regime probabilities) so there are no raw-scale magic constants; the combination weights are
documented priors that the slice-5 learner will fit from the persisted realised-edge ledger.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import numpy as np
from scipy import stats

_ABSTAIN_FLOOR = 0.20  # a best-engine score below this = no real edge → stand aside (documented prior)
_MIN_CROSS_SECTION_FOR_RV = 3  # need a few names before a relative-value skew percentile means anything


class ProfitEngine(str, Enum):
    THETA = "theta"      # premium harvest — flat/range
    DELTA = "delta"      # directional
    VEGA = "vega"        # long vol — cheap premium
    GAMMA = "gamma"      # realized movement / 0DTE convexity
    RELVALUE = "relvalue"  # skew / term-structure relative value


@dataclass(frozen=True)
class OpportunityFeatures:
    """The per-name feature vector the scorer consumes (assembled from the gathered engine states)."""

    underlying: str
    richness: float | None       # VolRichnessState.richness ∈ [0,1] (rich premium)
    vrp: float | None            # variance risk premium (IV − forecast RV)
    stressed_prob: float         # regime stressed-state probability ∈ [0,1]
    is_range_bound: bool         # calm/elevated non-trending regime
    trend_conviction: float      # directional arbiter conviction ∈ [0,1]
    abs_skew: float              # |25Δ risk reversal|
    abs_term_slope: float        # |term-structure slope|
    is_expiry_day: bool
    pre_event: bool              # event gate blocks naked premium (stock)


@dataclass(frozen=True)
class EngineScores:
    theta: float
    delta: float
    vega: float
    gamma: float
    relvalue: float

    def as_dict(self) -> dict[str, float]:
        return {ProfitEngine.THETA.value: self.theta, ProfitEngine.DELTA.value: self.delta,
                ProfitEngine.VEGA.value: self.vega, ProfitEngine.GAMMA.value: self.gamma,
                ProfitEngine.RELVALUE.value: self.relvalue}


@dataclass(frozen=True)
class OpportunityScore:
    """The scored verdict for one name: per-engine edge, the winner, and its cross-sectional rank."""

    underlying: str
    scores: EngineScores
    best_engine: ProfitEngine | None  # None → abstain (no engine clears the floor)
    best_score: float
    rank_percentile: float | None  # where best_score sits across the universe this cycle

    def tradeable_engines(self) -> list[ProfitEngine]:
        """Engines that clear the edge floor, strongest first — so a bot can fall back to the next-best engine
        when the top engine's optimizer can't synthesize a floor-passing structure (rather than abstain
        outright). Empty when no engine has a real edge (a genuine stand-aside)."""
        ranked = sorted(self.scores.as_dict().items(), key=lambda kv: kv[1], reverse=True)
        return [ProfitEngine(name) for name, score in ranked if score >= _ABSTAIN_FLOOR]


class OpportunityScoreLedger:
    """Persists each cycle's per-name scores + chosen engine — the substrate the slice-5 learner re-weights."""

    def __init__(self, store_dir: Path):
        self._dir = Path(store_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / "opportunity_scores.jsonl"

    def record(self, trade_date: str, scored: dict[str, OpportunityScore]) -> None:
        lines = []
        for u, s in scored.items():
            lines.append(json.dumps({
                "trade_date": trade_date, "underlying": u, "scores": s.scores.as_dict(),
                "best_engine": s.best_engine.value if s.best_engine else None,
                "best_score": round(s.best_score, 4),
                "rank_percentile": None if s.rank_percentile is None else round(s.rank_percentile, 4),
            }))
        if lines:
            with self._path.open("a") as fh:
                fh.write("\n".join(lines) + "\n")
            self._trim()

    def _trim(self, max_lines: int = 200_000) -> None:
        try:
            lines = self._path.read_text().splitlines()
        except OSError:
            return
        if len(lines) > max_lines:
            self._path.write_text("\n".join(lines[-max_lines:]) + "\n")


class OptionOpportunityScorer:
    """Scores the five profit engines per name, argmax-selects, and ranks the universe cross-sectionally."""

    def __init__(self, ledger: OpportunityScoreLedger | None = None, abstain_floor: float = _ABSTAIN_FLOOR):
        self._ledger = ledger
        self._floor = abstain_floor
        self._engine_weights: dict[str, float] = {}  # learned per-engine multipliers (slice 5)

    def rank_universe(
        self, features: list[OpportunityFeatures], trade_date: str | None = None,
        engine_weights: dict[str, float] | None = None,
    ) -> dict[str, OpportunityScore]:
        """Score every name's engines, pick each winner, then rank winners cross-sectionally.

        ``engine_weights`` (slice 5, from the EnginePerformanceLearner) multiplies each engine's score before
        the argmax, so selection tilts toward the engines that have actually paid — the bot learning its edge.
        """
        self._engine_weights = engine_weights or {}
        # RV is a RELATIVE-value signal: a name's skew/term dislocation only counts as edge if it is EXTREME vs
        # the universe (all options carry some skew). Rank both cross-sectionally so RV can't win on normal skew.
        skews = np.asarray([f.abs_skew for f in features], dtype=np.float64)
        terms = np.asarray([f.abs_term_slope for f in features], dtype=np.float64)
        have_cs = len(features) >= _MIN_CROSS_SECTION_FOR_RV
        rv_pct = {}
        for f in features:
            if have_cs:
                p_skew = float(stats.percentileofscore(skews, f.abs_skew, kind="mean") / 100.0)
                p_term = float(stats.percentileofscore(terms, f.abs_term_slope, kind="mean") / 100.0)
                rv_pct[f.underlying] = 0.5 * p_skew + 0.5 * p_term
            else:
                rv_pct[f.underlying] = 0.0  # too few names to judge relative value → no RV edge
        scored_engines = {f.underlying: self._score_engines(f, rv_pct[f.underlying]) for f in features}
        best = {u: self._argmax(s) for u, s in scored_engines.items()}  # (engine|None, score)

        winning_scores = np.asarray([b[1] for b in best.values() if b[0] is not None], dtype=np.float64)
        out: dict[str, OpportunityScore] = {}
        for f in features:
            engine, score = best[f.underlying]
            rank = None
            if engine is not None and len(winning_scores) >= 2:
                rank = float(stats.percentileofscore(winning_scores, score, kind="mean") / 100.0)
            out[f.underlying] = OpportunityScore(
                f.underlying, scored_engines[f.underlying], engine, score, rank)
        if self._ledger is not None and trade_date is not None:
            self._ledger.record(trade_date, out)
        return out

    def _score_engines(self, f: OpportunityFeatures, rv_percentile: float) -> EngineScores:
        richness = f.richness if f.richness is not None else 0.5
        calm = max(0.0, 1.0 - f.stressed_prob)

        # Θ — premium harvest: rich premium × positive VRP × range-bound calm, killed by stress / pre-event.
        vrp_pos = 1.0 if (f.vrp is not None and f.vrp > 0.0) else 0.0
        theta = richness * vrp_pos * calm * (1.0 if f.is_range_bound else 0.6)
        if f.pre_event:
            theta *= 0.3  # naked premium blocked pre-event → only a small defined-risk edge remains

        # Δ — directional: the arbiter's earned conviction, boosted a little in a trending (non-range) regime.
        delta = min(1.0, f.trend_conviction * (1.15 if not f.is_range_bound else 1.0))

        # ν — long vega: buy vol either when it's CHEAP in a calm market (mean-reversion upward) OR when the
        # regime is STRESSED (own the tail). On EXPIRY DAY the cheap-vol/expansion thesis is weak (no time for
        # IV to expand → long premium just bleeds), so damp it there and let Γ/Θ take 0-DTE.
        expiry_damp = 0.25 if f.is_expiry_day else 1.0
        vega = (1.0 - richness) * calm * (0.8 if f.is_range_bound else 1.0) * expiry_damp + 0.6 * f.stressed_prob

        # Γ — gamma: convexity near expiry, best when vol is cheap (long gamma pays if it moves).
        gamma = (0.7 + 0.3 * (1.0 - richness)) if f.is_expiry_day else 0.0

        # RV — skew / term relative value: only the CROSS-SECTIONALLY most-dislocated names (top of the
        # universe's skew/term distribution) carry real edge; normal skew scores ~0.5 and rarely wins.
        relvalue = rv_percentile

        return EngineScores(
            theta=_clip01(theta), delta=_clip01(delta), vega=_clip01(vega),
            gamma=_clip01(gamma), relvalue=_clip01(relvalue))

    def _argmax(self, s: EngineScores) -> tuple[ProfitEngine | None, float]:
        w = self._engine_weights
        pairs = [
            (ProfitEngine.THETA, s.theta), (ProfitEngine.DELTA, s.delta), (ProfitEngine.VEGA, s.vega),
            (ProfitEngine.GAMMA, s.gamma), (ProfitEngine.RELVALUE, s.relvalue),
        ]
        weighted = [(e, sc * float(w.get(e.value, 1.0))) for e, sc in pairs]  # learned tilt (slice 5)
        engine, score = max(weighted, key=lambda p: p[1])
        if score < self._floor:
            return (None, score)  # no engine clears the abstention floor → stand aside
        return (engine, score)


def _clip01(x: float) -> float:
    return float(min(max(x, 0.0), 1.0))
