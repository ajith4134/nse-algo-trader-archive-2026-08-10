"""Curiosity engine orchestrator (research/164 §7/§10; Trunk XII INTRINSIC MOTIVATION).

Ties the layers into the organism's "wants to learn" drive: RAW experience → per-cell error series
(reader) → learning-progress + boredom (estimator, carried state) + count-based novelty (cold-start) →
a per-(strategy × regime) EXPLORATION PRIORITY `(0.7·Q_LP + 0.3·novelty)·boredom` → a softmax LP-bandit
plan (temperature annealed down as trade history grows) → per-REGIME priorities that steer which market
regime the replay curriculum trains on next (the safe, decision-grade consumer — it changes what the bot
LEARNS FROM, never live sizing). Carried state (Q_LP, boredom, trade watermark) via the engine store.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from nse_algo_trader.intrinsic_motivation.count_based_novelty import (
    enumerate_cell_novelties,
    novelty_bonus,
)
from nse_algo_trader.intrinsic_motivation.curiosity_engine_store import (
    CuriosityEngineStore,
    CuriosityState,
)
from nse_algo_trader.intrinsic_motivation.curiosity_experience_reader import (
    build_curiosity_observation,
    default_experience_row_source,
)
from nse_algo_trader.intrinsic_motivation.learning_progress_estimator import (
    MIN_WINDOW,
    update_cell_learning_state,
)

# Priority combination + selection (research/164 §7/§10).
LP_WEIGHT = 0.7                  # weight on tracked learning progress (the primary signal)
NOVELTY_WEIGHT = 0.3             # weight on count-based novelty (cold-start driver)
SOFTMAX_T0 = 1.0                 # initial selection temperature (explore-heavy)
SOFTMAX_T_MIN = 0.1              # floor temperature (never fully greedy)
SOFTMAX_ANNEAL_SCALE = 500.0     # trades over which T decays toward the floor
MATURE_TRADE_COUNT = 2 * MIN_WINDOW  # ≥ this many trades → the plan is data-mature (else pure cold-start)


@dataclass(frozen=True)
class CellExplorationPriority:
    """One (strategy × regime) cell's exploration verdict — the decision-grade per-cell output."""

    strategy_tag: str
    market_regime: str
    priority: float                 # (0.7·Q_LP + 0.3·novelty)·boredom
    select_probability: float       # softmax share of this cell in the exploration plan
    learning_progress: float | None
    q_learning_progress: float
    novelty: float
    boredom_multiplier: float
    competence: float
    sample_count: int
    is_trusted_lp: bool             # ≥ 2·MIN_WINDOW samples → LP is meaningful
    is_unobserved: bool             # never-traded strategy×regime combination


@dataclass(frozen=True)
class ExplorationPlan:
    """The full curiosity output: ranked cell priorities + per-regime aggregation for the replay selector."""

    cell_priorities: tuple[CellExplorationPriority, ...]     # ranked, highest priority first
    regime_priority: dict[str, float] = field(default_factory=dict)   # max cell priority per regime
    temperature: float = SOFTMAX_T0
    total_trades_seen: int = 0
    is_mature: bool = False          # enough history for LP to be meaningful (else cold-start novelty only)

    @property
    def top_cell(self) -> CellExplorationPriority | None:
        return self.cell_priorities[0] if self.cell_priorities else None

    def most_curious_regime(self) -> str | None:
        """The market regime the engine most wants the replay curriculum to train on next."""
        if not self.regime_priority:
            return None
        return max(self.regime_priority.items(), key=lambda kv: kv[1])[0]


class CuriosityEngine:
    """Computes the exploration plan from experience + carried learning state; serves regime priorities.

    `experience_row_source` is the DI seam (Rule J): production reads the real `experience_nodes` table;
    tests inject canned rows."""

    def __init__(self, experience_row_source=default_experience_row_source,
                 store: CuriosityEngineStore | None = None):
        self._experience_row_source = experience_row_source
        self._store = store or CuriosityEngineStore()
        self._state: CuriosityState = self._store.load()

    def _temperature(self, total_trades: int) -> float:
        """Anneal T from T0 toward the floor as history grows (explore early, exploit later)."""
        return max(SOFTMAX_T_MIN, SOFTMAX_T0 / (1.0 + total_trades / SOFTMAX_ANNEAL_SCALE))

    def compute_exploration_plan(self, persist: bool = True) -> ExplorationPlan:
        rows = list(self._experience_row_source())
        observation = build_curiosity_observation(rows)
        novelty_by_key = {(c.strategy_tag, c.market_regime): c
                          for c in enumerate_cell_novelties(observation)}

        temperature = self._temperature(observation.total_samples)
        raw: list[CellExplorationPriority] = []
        new_cell_states = dict(self._state.cell_states)

        # observed cells: fold in learning progress + boredom (carried state), combine with novelty
        for cell in observation.cells:
            prior = self._state.state_for(cell.strategy_tag, cell.market_regime)
            reading = update_cell_learning_state(cell, prior)
            state = reading.new_state
            nov = novelty_bonus(cell.sample_count)
            priority = (LP_WEIGHT * state.q_learning_progress + NOVELTY_WEIGHT * nov) * state.boredom_multiplier
            raw.append(CellExplorationPriority(
                strategy_tag=cell.strategy_tag, market_regime=cell.market_regime, priority=priority,
                select_probability=0.0, learning_progress=reading.learning_progress,
                q_learning_progress=state.q_learning_progress, novelty=nov,
                boredom_multiplier=state.boredom_multiplier, competence=state.competence,
                sample_count=cell.sample_count, is_trusted_lp=reading.is_trusted, is_unobserved=False))
            new_cell_states[CuriosityState.cell_state_key(cell.strategy_tag, cell.market_regime)] = state

        # unobserved cells (never-traded strategy×regime): pure novelty (cold-start exploration targets)
        for cn in novelty_by_key.values():
            if not cn.is_unobserved:
                continue
            priority = NOVELTY_WEIGHT * cn.novelty   # Q_LP=0, boredom=1 for a never-seen cell
            raw.append(CellExplorationPriority(
                strategy_tag=cn.strategy_tag, market_regime=cn.market_regime, priority=priority,
                select_probability=0.0, learning_progress=None, q_learning_progress=0.0,
                novelty=cn.novelty, boredom_multiplier=1.0, competence=0.0, sample_count=0,
                is_trusted_lp=False, is_unobserved=True))

        cell_priorities = self._apply_softmax(raw, temperature)
        regime_priority: dict[str, float] = {}
        for cp in cell_priorities:
            regime_priority[cp.market_regime] = max(regime_priority.get(cp.market_regime, 0.0), cp.priority)

        if persist:
            self._state.cell_states = new_cell_states
            self._state.total_trades_seen = observation.total_samples
            import contextlib
            with contextlib.suppress(Exception):
                self._store.save(self._state)  # persistence failure must not break the loop (Rule O.3)

        return ExplorationPlan(
            cell_priorities=tuple(cell_priorities), regime_priority=regime_priority,
            temperature=temperature, total_trades_seen=observation.total_samples,
            is_mature=observation.total_samples >= MATURE_TRADE_COUNT)

    @staticmethod
    def _apply_softmax(raw: list[CellExplorationPriority], temperature: float) -> list[CellExplorationPriority]:
        """Softmax the priorities into selection probabilities (numerically stable), then rank."""
        if not raw:
            return []
        priorities = [cp.priority for cp in raw]
        peak = max(priorities)
        exps = [math.exp((p - peak) / max(temperature, SOFTMAX_T_MIN)) for p in priorities]
        total = sum(exps) or 1.0
        scored = [
            CellExplorationPriority(
                strategy_tag=cp.strategy_tag, market_regime=cp.market_regime, priority=cp.priority,
                select_probability=e / total, learning_progress=cp.learning_progress,
                q_learning_progress=cp.q_learning_progress, novelty=cp.novelty,
                boredom_multiplier=cp.boredom_multiplier, competence=cp.competence,
                sample_count=cp.sample_count, is_trusted_lp=cp.is_trusted_lp, is_unobserved=cp.is_unobserved)
            for cp, e in zip(raw, exps, strict=True)
        ]
        return sorted(scored, key=lambda cp: cp.priority, reverse=True)
