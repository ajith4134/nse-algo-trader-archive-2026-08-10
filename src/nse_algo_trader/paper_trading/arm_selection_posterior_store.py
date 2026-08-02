"""What the selector REMEMBERS about each strategy arm — and how it forgets.

A **cell** is `(arm, index, regime bucket)`. Per cell this keeps only the sufficient statistics a
Gaussian posterior needs — effective sample count, reward sum, reward-square sum — so the whole
memory is a few numbers per cell rather than every trade ever taken.

## Why forgetting is time-based, not observation-based

The obvious implementation decays statistics by a factor on every new observation. That is wrong
here: it forgets FASTER in a busy week and SLOWER in a quiet one, which is precisely backwards.
"Forget stale regimes" is a statement about elapsed calendar time, not about how many trades
happened to fire. So decay is `0.5 ** (days_elapsed / half_life_days)`, applied whenever a cell is
touched. A cell nobody has traded for a month carries about half the weight it did, whether that
month held 200 trades or none.

Default half-life is 21 trading days — the 4-8 week effective memory the B18 research recommends,
which is the outer bound of plausible regime persistence for intraday options.

## Why it is persisted

Edge is 5-20% of per-trade noise at a few trades/day/arm, so useful evidence takes weeks to accrue.
This service restarts often (every deploy). An in-memory posterior would silently reset that
evidence to zero on each restart and the selector would spend its life in burn-in.

## Delayed rewards

A trade opens now and closes hours later. Joulani et al. (ICML 2013) show that in the stochastic
setting delay costs only ADDITIVE regret and needs no synchronisation — so `record_pending_trade`
logs the cell at open and `resolve_pending_trade` applies the reward whenever it arrives.
**Selection is never blocked on open trades.**

See `docs/research/b18_adaptive_arm_selector_design_2026-07-27.md`.
"""

from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

DEFAULT_ARM_POSTERIOR_DB_PATH = Path(
    "~/.nse_algo_trader/arm_selection_posterior.sqlite3"
).expanduser()

#: Elapsed trading days after which a cell's accrued evidence carries half its former weight.
DEFAULT_EVIDENCE_HALF_LIFE_DAYS = 21.0

#: Below this effective sample count a cell is "thin" and the selector must not exploit it.
BURN_IN_EFFECTIVE_SAMPLES = 15.0

_CREATE_CELL_TABLE = """
CREATE TABLE IF NOT EXISTS arm_posterior_cell (
    arm_name TEXT NOT NULL,
    context_key TEXT NOT NULL,
    effective_sample_count REAL NOT NULL,
    reward_sum REAL NOT NULL,
    reward_square_sum REAL NOT NULL,
    last_updated_at TEXT NOT NULL,
    PRIMARY KEY (arm_name, context_key)
)
"""

_CREATE_PENDING_TABLE = """
CREATE TABLE IF NOT EXISTS arm_pending_trade (
    trade_id TEXT PRIMARY KEY,
    arm_name TEXT NOT NULL,
    context_key TEXT NOT NULL,
    opened_at TEXT NOT NULL
)
"""


@dataclass(frozen=True)
class ArmPosteriorCell:
    """One arm's discounted evidence in one context."""

    arm_name: str
    context_key: str
    effective_sample_count: float
    reward_sum: float
    reward_square_sum: float

    @property
    def mean_reward(self) -> float:
        if self.effective_sample_count <= 0.0:
            return 0.0
        return self.reward_sum / self.effective_sample_count

    @property
    def reward_standard_deviation(self) -> float:
        """Dispersion of this cell's rewards. 0.0 when too thin to estimate — callers pool instead
        of trusting a one-sample variance."""
        if self.effective_sample_count <= 1.0:
            return 0.0
        variance = (
            self.reward_square_sum / self.effective_sample_count
        ) - self.mean_reward**2
        return math.sqrt(max(0.0, variance))

    @property
    def is_past_burn_in(self) -> bool:
        return self.effective_sample_count >= BURN_IN_EFFECTIVE_SAMPLES


def evidence_decay_factor(
    days_elapsed: float, half_life_days: float = DEFAULT_EVIDENCE_HALF_LIFE_DAYS
) -> float:
    """How much of a cell's weight survives `days_elapsed`. Always in (0, 1]."""
    if days_elapsed <= 0.0 or half_life_days <= 0.0:
        return 1.0
    return float(0.5 ** (days_elapsed / half_life_days))


class ArmSelectionPosteriorStore:
    """Durable, time-discounted sufficient statistics per (arm, context) cell."""

    def __init__(
        self,
        db_file_path: Path = DEFAULT_ARM_POSTERIOR_DB_PATH,
        half_life_days: float = DEFAULT_EVIDENCE_HALF_LIFE_DAYS,
    ) -> None:
        db_file_path.parent.mkdir(parents=True, exist_ok=True)
        # The service constructs this on the MAIN thread, but it is used from the loop thread
        # (record/resolve on trade open/close) AND from the publish path that builds the dashboard
        # surface. SQLite refuses cross-thread use by default, which surfaced as
        # "SQLite objects created in a thread can only be used in that same thread" — a failure that
        # would have silently broken the reward feedback on the first option trade. Access here is
        # short, immediately-committed writes plus reads, which SQLite serialises safely.
        self._connection = sqlite3.connect(str(db_file_path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute(_CREATE_CELL_TABLE)
        self._connection.execute(_CREATE_PENDING_TABLE)
        self._connection.commit()
        self._half_life_days = half_life_days

    def close(self) -> None:
        self._connection.close()

    # -- evidence ---------------------------------------------------------

    def record_reward(
        self, arm_name: str, context_key: str, reward: float, observed_at: datetime
    ) -> None:
        """Fold one closed-trade reward into a cell, decaying prior evidence by elapsed time first.

        Decaying BEFORE adding is what makes the new observation carry full weight while older
        evidence fades — the order matters and is the whole point of the discount.
        """
        if not math.isfinite(float(reward)):
            return
        row = self._connection.execute(
            "SELECT effective_sample_count, reward_sum, reward_square_sum, last_updated_at "
            "FROM arm_posterior_cell WHERE arm_name=? AND context_key=?",
            (arm_name, context_key),
        ).fetchone()

        if row is None:
            count, total, square_total = 0.0, 0.0, 0.0
        else:
            decay = evidence_decay_factor(
                _days_between(row["last_updated_at"], observed_at), self._half_life_days
            )
            count = row["effective_sample_count"] * decay
            total = row["reward_sum"] * decay
            square_total = row["reward_square_sum"] * decay

        self._connection.execute(
            "INSERT OR REPLACE INTO arm_posterior_cell VALUES (?,?,?,?,?,?)",
            (
                arm_name, context_key,
                count + 1.0,
                total + float(reward),
                square_total + float(reward) ** 2,
                observed_at.isoformat(),
            ),
        )
        self._connection.commit()

    def load_cell(
        self, arm_name: str, context_key: str, as_of: datetime
    ) -> ArmPosteriorCell:
        """A cell's evidence decayed to `as_of`. An unseen cell reads as empty, never as an error."""
        row = self._connection.execute(
            "SELECT effective_sample_count, reward_sum, reward_square_sum, last_updated_at "
            "FROM arm_posterior_cell WHERE arm_name=? AND context_key=?",
            (arm_name, context_key),
        ).fetchone()
        if row is None:
            return ArmPosteriorCell(arm_name, context_key, 0.0, 0.0, 0.0)
        decay = evidence_decay_factor(
            _days_between(row["last_updated_at"], as_of), self._half_life_days
        )
        return ArmPosteriorCell(
            arm_name=arm_name,
            context_key=context_key,
            effective_sample_count=row["effective_sample_count"] * decay,
            reward_sum=row["reward_sum"] * decay,
            reward_square_sum=row["reward_square_sum"] * decay,
        )

    def load_all_cells(self, as_of: datetime) -> list[ArmPosteriorCell]:
        """Every cell, decayed — the input the hierarchical shrinkage pools over."""
        return [
            self.load_cell(row["arm_name"], row["context_key"], as_of)
            for row in self._connection.execute(
                "SELECT arm_name, context_key FROM arm_posterior_cell"
            )
        ]

    # -- delayed rewards --------------------------------------------------

    def record_pending_trade(
        self, trade_id: str, arm_name: str, context_key: str, opened_at: datetime
    ) -> None:
        """Log which cell owns a trade that has just OPENED. Never blocks selection."""
        self._connection.execute(
            "INSERT OR REPLACE INTO arm_pending_trade VALUES (?,?,?,?)",
            (trade_id, arm_name, context_key, opened_at.isoformat()),
        )
        self._connection.commit()

    def resolve_pending_trade(
        self, trade_id: str, reward: float, closed_at: datetime
    ) -> bool:
        """Apply a reward to whichever cell opened this trade, however late it arrives.

        Returns False for an unknown trade_id rather than silently crediting the wrong cell.
        """
        row = self._connection.execute(
            "SELECT arm_name, context_key FROM arm_pending_trade WHERE trade_id=?",
            (trade_id,),
        ).fetchone()
        if row is None:
            return False
        self.record_reward(row["arm_name"], row["context_key"], reward, closed_at)
        self._connection.execute(
            "DELETE FROM arm_pending_trade WHERE trade_id=?", (trade_id,)
        )
        self._connection.commit()
        return True

    def pending_trade_count(self) -> int:
        return self._connection.execute(
            "SELECT COUNT(*) AS n FROM arm_pending_trade"
        ).fetchone()["n"]


def _days_between(earlier_iso: str, later: datetime) -> float:
    try:
        earlier = datetime.fromisoformat(earlier_iso)
    except (TypeError, ValueError):
        return 0.0
    if earlier.tzinfo is None and later.tzinfo is not None:
        earlier = earlier.replace(tzinfo=later.tzinfo)
    elif earlier.tzinfo is not None and later.tzinfo is None:
        later = later.replace(tzinfo=earlier.tzinfo)
    return max(0.0, (later - earlier).total_seconds() / 86400.0)


@dataclass(frozen=True)
class ArmEvidenceSummary:
    """One arm's accrued evidence across every context — the dashboard's read.

    `contexts_past_burn_in` vs `context_count` is the Rule-Q "have N / need M": until a context
    clears burn-in the selector is deliberately still exploring it, and the operator should be able
    to see that rather than wonder why allocation looks random.
    """

    arm_name: str
    context_count: int
    contexts_past_burn_in: int
    total_effective_samples: float
    mean_reward: float

    @property
    def is_armed(self) -> bool:
        """True once at least one context has enough evidence for the selector to exploit it."""
        return self.contexts_past_burn_in > 0


def summarise_arm_evidence(
    cells: list[ArmPosteriorCell], arm_names: tuple[str, ...]
) -> list[ArmEvidenceSummary]:
    """Fold decayed cells into one row per arm. Arms with no evidence still appear (count 0) so a
    silent, never-selected arm is visible rather than absent."""
    summaries = []
    for arm_name in arm_names:
        arm_cells = [cell for cell in cells if cell.arm_name == arm_name]
        total_samples = sum(cell.effective_sample_count for cell in arm_cells)
        total_reward = sum(cell.reward_sum for cell in arm_cells)
        summaries.append(
            ArmEvidenceSummary(
                arm_name=arm_name,
                context_count=len(arm_cells),
                contexts_past_burn_in=sum(1 for c in arm_cells if c.is_past_burn_in),
                total_effective_samples=total_samples,
                mean_reward=(total_reward / total_samples) if total_samples > 0 else 0.0,
            )
        )
    return summaries
