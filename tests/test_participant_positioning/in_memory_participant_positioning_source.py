"""A tests-only in-memory ParticipantPositioningSource (Rule J DI seam fake).

Lives under tests/ ONLY — it is never imported by src/, so the injected test
data is structurally unable to reach the live path. Production wires the real
NseParticipantPositioningSource. This fake lets the opponent-ledger read model
and its consumers be verified hermetically against injected snapshots.
"""

from datetime import date

from nse_algo_trader.participant_positioning import (
    ParticipantPositioningSnapshot,
)


class InMemoryParticipantPositioningSource:
    """Serves pre-loaded snapshots by date; returns None for unknown dates
    (mimicking NSE's 404-on-holiday behaviour)."""

    def __init__(
        self,
        snapshots_by_date: dict[date, ParticipantPositioningSnapshot],
        volume_by_date: dict[date, ParticipantPositioningSnapshot] | None = None,
    ) -> None:
        self._snapshots_by_date = dict(snapshots_by_date)
        self._volume_by_date = dict(volume_by_date or {})

    def positioning_on(
        self, trade_date: date
    ) -> ParticipantPositioningSnapshot | None:
        return self._snapshots_by_date.get(trade_date)

    def volume_on(
        self, trade_date: date
    ) -> ParticipantPositioningSnapshot | None:
        return self._volume_by_date.get(trade_date)
