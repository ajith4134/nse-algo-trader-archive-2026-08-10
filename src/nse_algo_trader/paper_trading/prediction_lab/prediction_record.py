"""The immutable PredictionRecord — written BEFORE a paper trade opens.

The heart of the falsification lab (PLAN §9): every paper trade declares,
up front and unchangeably, what it believes will happen and why. Reality
then grades the belief. Three tables sort trades by prediction:
CONFIDENT-WIN (predicted profitable), CONFIDENT-LOSS (deliberately opened
predicting a LOSS, to prove the bot understands *why* trades lose), and
UNCERTAIN (near-50%, the most informative experiments).
"""

from dataclasses import dataclass
from datetime import date
from enum import Enum

from nse_algo_trader.strategy_engine import SignalDirection


class PredictedTradeOutcome(str, Enum):
    WIN = "win"
    LOSS = "loss"


class PredictionLabeledTable(str, Enum):
    CONFIDENT_WIN = "confident_win"
    CONFIDENT_LOSS = "confident_loss"  # opened predicting a loss, on purpose
    UNCERTAIN = "uncertain"


@dataclass(frozen=True)
class NamedPredictionReason:
    """One machine-readable factor behind the prediction and its claimed
    contribution direction (+ pushes toward WIN, - toward LOSS)."""

    reason_name: str
    observed_value: float
    claimed_contribution: float


@dataclass(frozen=True)
class TradePredictionRecord:
    session_date: date
    instrument_token: int
    strategy_tag: str
    direction: SignalDirection
    predicted_outcome: PredictedTradeOutcome
    win_probability: float  # calibrated 0..1
    assigned_table: PredictionLabeledTable
    expected_reward_multiple: float  # +R if the win thesis is right, -1 at stop
    reasons: tuple[NamedPredictionReason, ...]
    mechanism_name: str  # HOW it is expected to win/lose (graded later)
    predicted_exit_cause: str  # "target" | "stop" | "square_off"
    kill_criteria: str  # the evidence that would falsify the thesis -> exit
    calendar_context: str  # "normal" | "expiry_day" | "event_day" ...

    def __post_init__(self) -> None:
        if not 0.0 <= self.win_probability <= 1.0:
            raise ValueError("win_probability must be in [0, 1]")
        # The CONFIDENT-LOSS table must actually predict a loss, and
        # CONFIDENT-WIN must predict a win — the labels are not cosmetic.
        if (
            self.assigned_table is PredictionLabeledTable.CONFIDENT_WIN
            and self.predicted_outcome is not PredictedTradeOutcome.WIN
        ):
            raise ValueError("CONFIDENT_WIN table requires predicted_outcome WIN")
        if (
            self.assigned_table is PredictionLabeledTable.CONFIDENT_LOSS
            and self.predicted_outcome is not PredictedTradeOutcome.LOSS
        ):
            raise ValueError("CONFIDENT_LOSS table requires predicted_outcome LOSS")
