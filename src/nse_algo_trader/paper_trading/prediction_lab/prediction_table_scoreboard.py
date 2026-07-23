"""Per-table scoreboard — the lab's headline calibration numbers.

Accumulates graded predictions and reports, per prediction table and
overall: how many predictions came true (hit rate), the mean predicted
win-probability vs the actual win rate (calibration gap), and the Brier
score (PLAN §9). The central falsification check lives here: the
CONFIDENT-WIN table's actual win rate must beat the CONFIDENT-LOSS
table's — if it doesn't, the bot's confidence is an illusion.
"""

from dataclasses import dataclass, field

from nse_algo_trader.paper_trading.prediction_lab.prediction_outcome_grading import (
    GradedPrediction,
)
from nse_algo_trader.paper_trading.prediction_lab.prediction_record import (
    PredictionLabeledTable,
)


@dataclass(frozen=True)
class TableScore:
    prediction_count: int
    prediction_hit_rate: float  # fraction of predictions that came true
    mean_win_probability: float
    actual_win_rate: float
    brier_score: float  # lower is better; 0 = perfect, 0.25 = always-0.5 guess


class PredictionTableScoreboard:
    def __init__(self) -> None:
        self._graded_by_table: dict[PredictionLabeledTable, list[GradedPrediction]] = {
            table: [] for table in PredictionLabeledTable
        }

    def add_graded_prediction(self, graded: GradedPrediction) -> None:
        self._graded_by_table[graded.record.assigned_table].append(graded)

    def score_for_table(self, table: PredictionLabeledTable) -> TableScore | None:
        graded_list = self._graded_by_table[table]
        return _score(graded_list)

    def overall_score(self) -> TableScore | None:
        all_graded = [g for lst in self._graded_by_table.values() for g in lst]
        return _score(all_graded)

    def confident_win_beats_confident_loss(self) -> bool | None:
        """The core falsification check. None if either table is empty."""
        win_score = self.score_for_table(PredictionLabeledTable.CONFIDENT_WIN)
        loss_score = self.score_for_table(PredictionLabeledTable.CONFIDENT_LOSS)
        if win_score is None or loss_score is None:
            return None
        return win_score.actual_win_rate > loss_score.actual_win_rate


def _score(graded_list: list[GradedPrediction]) -> TableScore | None:
    if not graded_list:
        return None
    count = len(graded_list)
    return TableScore(
        prediction_count=count,
        prediction_hit_rate=sum(g.prediction_was_correct for g in graded_list) / count,
        mean_win_probability=sum(g.record.win_probability for g in graded_list) / count,
        actual_win_rate=sum(
            g.actual_outcome.value == "win" for g in graded_list
        )
        / count,
        brier_score=sum(g.brier_contribution for g in graded_list) / count,
    )
