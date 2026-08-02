"""Pick which historical session to replay next so the curriculum targets the market
regime we've learned LEAST about (§53 slice 5a; research/86).

Given candidate sessions already classified into their market regime, and how many
sessions of each regime we've replayed so far, choose the candidate whose regime has the
lowest coverage — the deficit. Ties break toward the most-recent date (freshest data of
that under-covered regime). PURE (no I/O); the coverage counts come from
`replayed_session_regime_ledger`, and the classification from
`historical_session_market_regime_classifier`.
"""

from __future__ import annotations

from datetime import date

from nse_algo_trader.strategy_engine.session_strategy_regime_gate import MarketRegime


def select_deficit_replay_session(
    classified_candidates: list[tuple[date, MarketRegime]],
    covered_regime_counts: dict[str, int],
) -> date | None:
    """The candidate date whose regime is least-covered so far (deficit-first). Among
    equal coverage, the most-recent date wins. Returns None when there are no candidates.

    `covered_regime_counts` is keyed by `MarketRegime.value`; a regime absent from the map
    counts as 0 coverage (so a never-replayed regime is always preferred)."""
    if not classified_candidates:
        return None
    return min(
        classified_candidates,
        key=lambda candidate: (
            covered_regime_counts.get(candidate[1].value, 0),  # deficit-first (ascending)
            -candidate[0].toordinal(),  # tie-break: most-recent date first
        ),
    )[0]


def select_curiosity_driven_replay_session(
    classified_candidates: list[tuple[date, MarketRegime]],
    regime_exploration_priority: dict[str, float],
) -> date | None:
    """Curiosity-driven upgrade of the deficit selector (Trunk XII; research/164): pick the candidate
    whose regime the curiosity engine most wants to LEARN from — i.e. HIGHEST exploration priority
    (learning-progress + novelty + boredom), not merely least-replayed. Among equal priority, the
    most-recent date wins. `regime_exploration_priority` is keyed by `MarketRegime.value`; a regime
    absent from the map counts as 0 priority. Returns None when there are no candidates.

    This is the safe decision-grade consumer of curiosity — it steers what the bot TRAINS ON (replay
    curriculum), never live sizing. Falls back to coverage-deficit behaviour if no priorities are given."""
    if not classified_candidates:
        return None
    if not regime_exploration_priority:
        return select_deficit_replay_session(classified_candidates, {})
    return max(
        classified_candidates,
        key=lambda candidate: (
            regime_exploration_priority.get(candidate[1].value, 0.0),  # highest curiosity first
            candidate[0].toordinal(),  # tie-break: most-recent date first
        ),
    )[0]
