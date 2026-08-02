"""How far into profit, and how far into loss, has an open position ACTUALLY been?

Two numbers per open trade, both in rupees, both updated on every price pass:

* **MFE** — Maximum Favourable Excursion: the highest unrealised profit the trade has reached since
  it opened. "The best it ever looked."
* **MAE** — Maximum Adverse Excursion: the worst unrealised loss it has reached. "The worst it ever
  looked."

They are the operator-requested max-profit / max-loss columns on the open-trade tables, and they are
also the evidence base the profit trail is tuned from:

* `MFE` far above realised profit, repeatedly, is proof that TARGETS ARE CAPPING RUNS.
* `MAE` near zero on winners is proof that STOPS ARE WIDER THAN THEY NEED TO BE.

Without them, every exit parameter is a guess. With them persisted onto closed trades, the learning
layer can answer "do we exit too early?" from evidence.

Deliberately expressed in **profit space (rupees), never price space**. The three position types
this serves disagree about which direction of *price* is good — a credit spread profits when the net
premium FALLS — but they all agree that more rupees is better. One monotone quantity, one set of
comparisons, no per-type sign handling downstream.

See `docs/research/b23_profit_trail_and_excursion_design_2026-07-27.md`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class PositionProfitExcursion:
    """The running best/worst unrealised profit of one open position, in rupees.

    Seeded at 0.0 rather than None so a trade that never goes green reports `MFE = 0.0` — an honest
    "it was never in profit" — instead of a missing value the dashboard has to special-case.
    """

    #: Highest unrealised profit reached since the position opened. Non-decreasing, floored at 0.
    maximum_favourable_profit: float = 0.0
    #: Worst unrealised loss reached since the position opened. Non-increasing, capped at 0.
    maximum_adverse_profit: float = 0.0
    #: How many price observations have been folded in — lets the dashboard distinguish
    #: "flat all day" from "never priced" (a stale feed), which look identical otherwise.
    observation_count: int = 0

    def observe_unrealised_profit(self, unrealised_profit: float | None) -> None:
        """Fold one unrealised-profit observation in. Ignores an unavailable price (`None`) and any
        non-finite value rather than corrupting the extremes with a fabricated reading."""
        if unrealised_profit is None:
            return
        profit = float(unrealised_profit)
        if not math.isfinite(profit):
            return
        self.observation_count += 1
        if profit > self.maximum_favourable_profit:
            self.maximum_favourable_profit = profit
        if profit < self.maximum_adverse_profit:
            self.maximum_adverse_profit = profit

    @property
    def has_been_in_profit(self) -> bool:
        return self.maximum_favourable_profit > 0.0

    @property
    def profit_given_back_from_peak(self) -> float:
        """How much of the peak profit is currently unrecoverable knowledge — used only for display;
        the live give-back is computed against the CURRENT profit by the trail engine."""
        return max(0.0, self.maximum_favourable_profit)
