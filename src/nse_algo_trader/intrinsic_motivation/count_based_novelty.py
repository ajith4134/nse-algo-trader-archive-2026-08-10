"""Count-based novelty bonus (research/164 §3; Trunk XII). The cold-start half of curiosity.

Learning Progress needs ≥ 2·MIN_WINDOW trades before it means anything; below that (and for cells NEVER
traded), the exploration signal comes from a count-based novelty bonus `β/√(N+1)` (Bellemare 2016's
pseudo-count exploration-bonus form — exact even at N=0, so a never-observed (strategy × regime) cell gets
the maximum bonus β). This is what makes the engine drive the bot toward UNOBSERVED regimes at cold-start
(the real data reality: ~1 session-day, all "indecisive" → every other regime is novel). PURE.
"""

from __future__ import annotations

from dataclasses import dataclass

from nse_algo_trader.intrinsic_motivation.curiosity_experience_reader import (
    KNOWN_MARKET_REGIMES,
    CuriosityObservation,
)

NOVELTY_BETA = 1.0    # scale of the novelty bonus; β/√(N+1) → β at N=0, decaying as a cell is sampled


def novelty_bonus(sample_count: int, beta: float = NOVELTY_BETA) -> float:
    """β/√(N+1): maximal (β) for a never-sampled cell, decaying as it accrues trades (Bellemare 2016)."""
    return beta / ((sample_count + 1) ** 0.5)


@dataclass(frozen=True)
class CellNovelty:
    """A (strategy × regime) cell's novelty — including cells that exist only as unobserved combinations."""

    strategy_tag: str
    market_regime: str
    sample_count: int
    novelty: float
    is_unobserved: bool     # True → this strategy×regime combination has never been traded


def enumerate_cell_novelties(observation: CuriosityObservation,
                             beta: float = NOVELTY_BETA) -> list[CellNovelty]:
    """Novelty for every (strategy × regime) cell in the reachable universe — the OBSERVED cells plus the
    unobserved combinations of each seen strategy with each KNOWN regime it has never been tried in.

    The unobserved combinations are the whole point of cold-start curiosity: a strategy proven in one
    regime should be EXPLORED in the regimes it has never met (N=0 → maximum bonus β)."""
    novelties: list[CellNovelty] = []
    seen_keys = set(observation.cells_by_key.keys())

    for cell in observation.cells:
        novelties.append(CellNovelty(
            strategy_tag=cell.strategy_tag, market_regime=cell.market_regime,
            sample_count=cell.sample_count, novelty=novelty_bonus(cell.sample_count, beta),
            is_unobserved=False))

    # every seen strategy × every known regime it has NOT been traded in → an unobserved cell (N=0)
    for strategy in sorted(observation.strategies_seen):
        for regime in KNOWN_MARKET_REGIMES:
            if (strategy, regime) not in seen_keys:
                novelties.append(CellNovelty(
                    strategy_tag=strategy, market_regime=regime, sample_count=0,
                    novelty=novelty_bonus(0, beta), is_unobserved=True))
    return novelties
