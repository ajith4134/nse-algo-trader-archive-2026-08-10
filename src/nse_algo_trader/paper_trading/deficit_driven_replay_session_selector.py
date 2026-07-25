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
