"""Learning-Progress estimator (research/164 §1-§3; Trunk XII). The heart of the curiosity engine.

Learning Progress (Oudeyer-Kaplan-Hafner 2007 IAC): a cell is INTERESTING not when its prediction error
is high (that includes irreducible noise — the "noisy-TV" trap) but when its error is DECREASING — the
model is still learning there. Per (strategy × regime) cell we compute, over its time-ordered Brier-error
series, `LP = ⟨error⟩_prior_window − ⟨error⟩_recent_window` (positive = improving). LP is UNTRUSTED until
the cell has ≥ 2·MIN_WINDOW trades (region-splitting: never compare across dissimilar cells). We track it
non-stationarily as `Q_LP ← Q_LP + α(|LP| − Q_LP)` (|LP| per SAGG-RIAC — both fresh improvement AND
regime-drift degradation re-trigger interest), and a BOREDOM counter that decays priority on cells whose
LP has gone flat (mastered-and-stable → IAC's LP→0). Carried STATE per cell (Q_LP, boredom) lives in
`CellLearningState`, persisted by the engine store. PURE — the estimator takes state in and returns new
state out; no I/O.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from nse_algo_trader.intrinsic_motivation.curiosity_experience_reader import CellErrorSeries

# Windowing + tracking constants (research/164 §1/§10 — trading-scaled from IAC's robotics defaults).
MIN_WINDOW = 8                    # smallest window; LP needs ≥ 2·MIN_WINDOW trades to be trusted
Q_LP_RECENCY_ALPHA = 0.3          # exponential-recency weight for the non-stationary Q_LP estimate
BOREDOM_KAPPA = 0.5               # decay rate of the boredom multiplier per consecutive bored window
LP_BORED_THRESHOLD = 0.01         # |LP| below this = "no more to learn here right now" → a bored window


@dataclass(frozen=True)
class CellLearningState:
    """Carried per-cell curiosity state (persisted across ticks/sessions)."""

    q_learning_progress: float = 0.0      # Q_LP — the tracked |learning progress|
    consecutive_bored_windows: int = 0    # how many recent updates had |LP| < threshold
    samples_at_last_update: int = 0       # cell sample_count when Q_LP was last updated (fire once/window)
    last_recent_error_mean: float = 1.0   # most-recent-window mean error (for competence display)

    @property
    def boredom_multiplier(self) -> float:
        """exp(−κ·bored_windows) ∈ (0, 1]: mastered-and-stable cells decay in exploration priority."""
        return math.exp(-BOREDOM_KAPPA * self.consecutive_bored_windows)

    @property
    def competence(self) -> float:
        """1 − recent mean Brier error ∈ [0, 1] — how well the model currently predicts this cell."""
        return max(0.0, 1.0 - self.last_recent_error_mean)


@dataclass(frozen=True)
class LearningProgressReading:
    """One cell's LP evaluation this update: the raw LP, the trust gate, and the new carried state."""

    cell_key: tuple[str, str]
    learning_progress: float | None       # None when the cell is below the trust gate (too few samples)
    is_trusted: bool                       # ≥ 2·MIN_WINDOW samples → LP is meaningful
    new_state: CellLearningState


def compute_learning_progress(errors_in_time_order: tuple[float, ...],
                              window: int = MIN_WINDOW) -> float | None:
    """LP = mean(prior window) − mean(recent window). None when fewer than 2·window samples exist.

    Positive LP = error fell between the prior and recent windows = the model is still LEARNING this cell.
    Negative LP = error rose (regime drift / concept change) — SAGG-RIAC treats |LP| as interest, so the
    engine re-explores a degrading cell too."""
    n = len(errors_in_time_order)
    if n < 2 * window:
        return None
    recent = errors_in_time_order[-window:]
    prior = errors_in_time_order[-2 * window:-window]
    return (sum(prior) / window) - (sum(recent) / window)


def update_cell_learning_state(cell: CellErrorSeries, prior_state: CellLearningState) -> LearningProgressReading:
    """Fold this cell's current error series into its carried learning state → a new state + LP reading.

    Only advances Q_LP/boredom when at least one NEW trade has arrived since the last update (so repeated
    reads within a window don't double-count), and only when the trust gate (≥ 2·MIN_WINDOW) is met."""
    lp = compute_learning_progress(cell.errors_in_time_order)
    recent_mean = (sum(cell.errors_in_time_order[-MIN_WINDOW:]) / min(len(cell.errors_in_time_order), MIN_WINDOW)
                   if cell.errors_in_time_order else 1.0)

    if lp is None:
        # below the trust gate: keep Q_LP as-is, just refresh the competence readout
        new_state = CellLearningState(
            q_learning_progress=prior_state.q_learning_progress,
            consecutive_bored_windows=prior_state.consecutive_bored_windows,
            samples_at_last_update=cell.sample_count,
            last_recent_error_mean=recent_mean,
        )
        return LearningProgressReading(cell.cell_key, None, is_trusted=False, new_state=new_state)

    if cell.sample_count <= prior_state.samples_at_last_update:
        # no new trades since the last update — don't re-fold (avoid double-counting the same window)
        return LearningProgressReading(cell.cell_key, lp, is_trusted=True, new_state=prior_state)

    q_new = prior_state.q_learning_progress + Q_LP_RECENCY_ALPHA * (abs(lp) - prior_state.q_learning_progress)
    bored = prior_state.consecutive_bored_windows + 1 if abs(lp) < LP_BORED_THRESHOLD else 0
    new_state = CellLearningState(
        q_learning_progress=q_new,
        consecutive_bored_windows=bored,
        samples_at_last_update=cell.sample_count,
        last_recent_error_mean=recent_mean,
    )
    return LearningProgressReading(cell.cell_key, lp, is_trusted=True, new_state=new_state)
