"""Which strategy arm should trade this index, right now?

The operator's requirement: *"all algorithms, and AI chooses which to follow based on their
performance as more trades are opened and closed."*

## The constraint that dictates every design choice

Edge here is **5-20% of per-trade noise SD** at **~2.5-7.5 closed trades/day/arm**, while intraday
regimes turn over in **days to ~2 weeks**. Plain Thompson Sampling needs ~390 trades/arm to resolve a
10-point win-rate gap (~4 months) and ~4,360 for a 3-point gap (~3.5 years). Every textbook
algorithm hits the same wall: the memory needed to be *confident* is longer than the memory that is
still *relevant*.

So this is not a textbook algorithm. It is Thompson Sampling plus four safeguards, all concurrent,
each answering a specific documented failure:

1. **Hierarchical empirical-Bayes shrinkage** — a cell's mean is pulled toward its arm's
   cross-context mean, which is itself pulled toward the grand mean, with strength inverse to that
   cell's evidence. A brand-new cell therefore inherits real information instead of a flat prior.
   This is what moves per-cell sample needs from *years* to *weeks* (James-Stein; Dimmery-Bakshy-
   Sekhon KDD 2019, validated across 17 Facebook experiments — the benefit GROWS with arm count).
2. **Time-based discounting** (in the store) — honest forgetting, rather than change-point
   detection, which the research shows is strictly HARDER than the comparison it would simplify at
   this noise level.
3. **Burn-in cap** — while any arm in a context is thin, selection is uniform among the thin arms,
   so an early lucky arm cannot monopolise before the others have been given a fair hearing.
4. **A permanent epsilon-floor** — never phased out, so a temporarily-losing arm is never starved of
   the data needed to prove whether it was genuinely bad or merely unlucky.

**The property that matters most is the NEGATIVE one:** on a stream with no true edge, this must NOT
concentrate. A selector that converges on a winner but also "converges" on noise is worse than
uniform allocation, because it is confidently wrong. That is an explicit test.

Randomness is injected so behaviour is reproducible in tests.

See `docs/research/b18_adaptive_arm_selector_design_2026-07-27.md`.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import datetime

from nse_algo_trader.paper_trading.arm_selection_posterior_store import (
    BURN_IN_EFFECTIVE_SAMPLES,
    ArmPosteriorCell,
    ArmSelectionPosteriorStore,
)

#: Share of selections that stay uniformly random FOREVER. Not a decayed schedule: a losing arm must
#: keep receiving evidence, or "it lost" becomes unfalsifiable.
PERMANENT_EXPLORATION_FLOOR = 0.12

#: Pseudo-observations of prior strength. A cell needs roughly this much evidence before its own
#: mean outweighs its parent's — the knob that trades cold-start safety against responsiveness.
SHRINKAGE_PRIOR_STRENGTH = 8.0

#: Used while every cell is too thin to estimate dispersion. In rupees: a plausible per-trade spread.
FALLBACK_REWARD_DISPERSION = 500.0


@dataclass(frozen=True)
class ArmSelection:
    """The chosen arm AND the reasoning — every field exists so a dashboard can explain the pick."""

    chosen_arm: str
    posterior_mean_reward: float
    posterior_standard_deviation: float
    effective_sample_count: float
    was_forced_exploration: bool
    was_burn_in: bool
    selection_reason: str


def shrink_toward_parent(
    cell_mean: float,
    cell_sample_count: float,
    parent_mean: float,
    prior_strength: float = SHRINKAGE_PRIOR_STRENGTH,
) -> float:
    """Empirical-Bayes shrinkage: `(n·cell + k·parent) / (n + k)`.

    With no evidence the result IS the parent mean (never a flat zero); with abundant evidence the
    parent's influence vanishes. This is the mechanism that lets a new (arm, index, regime) cell
    start from what the arm has done elsewhere instead of from ignorance.
    """
    total_weight = cell_sample_count + prior_strength
    if total_weight <= 0.0:
        return parent_mean
    return (cell_sample_count * cell_mean + prior_strength * parent_mean) / total_weight


def _pooled_dispersion(cells: list[ArmPosteriorCell]) -> float:
    dispersions = [
        cell.reward_standard_deviation
        for cell in cells
        if cell.effective_sample_count > 1.0 and cell.reward_standard_deviation > 0.0
    ]
    if not dispersions:
        return FALLBACK_REWARD_DISPERSION
    return sum(dispersions) / len(dispersions)


class AdaptiveArmSelector:
    """Hierarchical, discounted, contextual Thompson Sampling with burn-in and a permanent floor."""

    def __init__(
        self,
        store: ArmSelectionPosteriorStore,
        arm_names: tuple[str, ...],
        random_source: random.Random | None = None,
        exploration_floor: float = PERMANENT_EXPLORATION_FLOOR,
        prior_strength: float = SHRINKAGE_PRIOR_STRENGTH,
    ) -> None:
        if not arm_names:
            raise ValueError("a selector needs at least one arm")
        self._store = store
        self._arm_names = tuple(arm_names)
        self._random = random_source or random.Random()
        self._exploration_floor = exploration_floor
        self._prior_strength = prior_strength

    def select_arm(self, context_key: str, as_of: datetime) -> ArmSelection:
        """Choose an arm for this context. Never blocks on open trades (delayed rewards land later)."""
        all_cells = self._store.load_all_cells(as_of)
        context_cells = {
            arm: self._store.load_cell(arm, context_key, as_of)
            for arm in self._arm_names
        }
        grand_mean = _weighted_mean(all_cells)
        dispersion = _pooled_dispersion(all_cells)

        # (1) Permanent floor — checked FIRST so it can never be skipped by an earlier return.
        if self._random.random() < self._exploration_floor:
            arm = self._random.choice(self._arm_names)
            cell = context_cells[arm]
            return self._selection(
                arm, cell, grand_mean, dispersion, all_cells,
                forced=True, burn_in=False,
                reason=f"forced exploration ({self._exploration_floor:.0%} floor) — keeps every "
                       "arm falsifiable",
            )

        # (2) Burn-in — while any arm here is thin, spread uniformly across the THIN ones so an
        #     early lucky arm cannot monopolise before the others have been heard.
        thin_arms = [
            arm for arm, cell in context_cells.items() if not cell.is_past_burn_in
        ]
        if thin_arms:
            arm = self._random.choice(thin_arms)
            cell = context_cells[arm]
            return self._selection(
                arm, cell, grand_mean, dispersion, all_cells,
                forced=False, burn_in=True,
                reason=(
                    f"burn-in: {len(thin_arms)} of {len(self._arm_names)} arms under "
                    f"{BURN_IN_EFFECTIVE_SAMPLES:.0f} effective samples in this context "
                    f"(have {cell.effective_sample_count:.1f})"
                ),
            )

        # (3) Thompson sampling over the SHRUNK posteriors.
        best_arm, best_draw = self._arm_names[0], -math.inf
        for arm in self._arm_names:
            mean, deviation = self._shrunk_posterior(
                context_cells[arm], grand_mean, dispersion, all_cells
            )
            draw = self._random.gauss(mean, deviation)
            if draw > best_draw:
                best_arm, best_draw = arm, draw
        cell = context_cells[best_arm]
        return self._selection(
            best_arm, cell, grand_mean, dispersion, all_cells,
            forced=False, burn_in=False,
            reason=f"Thompson draw {best_draw:.1f} highest across {len(self._arm_names)} arms",
        )

    def _arm_parent_mean(
        self, arm_name: str, all_cells: list[ArmPosteriorCell], grand_mean: float
    ) -> float:
        """The arm's cross-context mean, itself shrunk toward the grand mean — level 2 of the
        hierarchy. Without this, an arm new to one index would ignore everything it has done on the
        other four."""
        arm_cells = [cell for cell in all_cells if cell.arm_name == arm_name]
        if not arm_cells:
            return grand_mean
        arm_samples = sum(cell.effective_sample_count for cell in arm_cells)
        return shrink_toward_parent(
            _weighted_mean(arm_cells), arm_samples, grand_mean, self._prior_strength
        )

    def _shrunk_posterior(
        self,
        cell: ArmPosteriorCell,
        grand_mean: float,
        dispersion: float,
        all_cells: list[ArmPosteriorCell],
    ) -> tuple[float, float]:
        parent_mean = self._arm_parent_mean(cell.arm_name, all_cells, grand_mean)
        mean = shrink_toward_parent(
            cell.mean_reward, cell.effective_sample_count, parent_mean, self._prior_strength
        )
        # Posterior SD shrinks as evidence accrues; the prior strength keeps it finite at n=0.
        deviation = dispersion / math.sqrt(
            max(1e-9, cell.effective_sample_count + self._prior_strength)
        )
        return mean, max(1e-9, deviation)

    def _selection(
        self, arm, cell, grand_mean, dispersion, all_cells, forced, burn_in, reason
    ) -> ArmSelection:
        mean, deviation = self._shrunk_posterior(cell, grand_mean, dispersion, all_cells)
        return ArmSelection(
            chosen_arm=arm,
            posterior_mean_reward=mean,
            posterior_standard_deviation=deviation,
            effective_sample_count=cell.effective_sample_count,
            was_forced_exploration=forced,
            was_burn_in=burn_in,
            selection_reason=reason,
        )


def _weighted_mean(cells: list[ArmPosteriorCell]) -> float:
    total_samples = sum(cell.effective_sample_count for cell in cells)
    if total_samples <= 0.0:
        return 0.0
    return sum(cell.reward_sum for cell in cells) / total_samples


#: How hard a loss is penalised relative to an equal-sized gain when it updates a posterior.
#: 1.0 would be raw mean P&L. Above 1.0 makes the selector tail-aware.
DOWNSIDE_LOSS_AVERSION = 2.0


def tail_aware_reward(net_profit_after_costs: float) -> float:
    """Convert a closed trade's cost-net P&L into the reward the selector actually learns from.

    SPEC §3 requires this, and the reason is specific to what the arms DO. A premium-selling arm wins
    often and small and loses rarely and large. Under raw mean P&L its many small wins outvote its
    few large losses long before enough tail events have occurred to reveal the true distribution —
    so the selector would confidently favour exactly the arm whose risk it has not yet observed.

    Penalising losses at `DOWNSIDE_LOSS_AVERSION` x makes the statistic a mean-semivariance-style
    proxy: it converges on the same ordering as raw P&L for symmetric arms, but refuses to reward a
    skewed arm until its losses have actually been paid for.

    Deliberately monotone (a better trade is never scored worse) so it cannot invert the ordering of
    two arms that differ only in magnitude.
    """
    profit = float(net_profit_after_costs)
    if not math.isfinite(profit):
        return 0.0
    return profit if profit >= 0.0 else profit * DOWNSIDE_LOSS_AVERSION
