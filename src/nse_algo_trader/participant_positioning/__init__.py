"""Participant-wise positioning (the opponent ledger) — Layer 10 §10.

Reads NSE's daily participant-wise open-interest report (Client/DII/FII/Pro)
and derives "who is on the other side" directional / divergence signals. The
real NSE archive fetcher and the pure read model sit behind one swappable
source protocol. See docs/research/47 and docs/flowcharts/10_memory_reflection.md.
"""

from nse_algo_trader.participant_positioning.market_positioning_bias import (
    institutional_positioning_opposes_entry,
)
from nse_algo_trader.participant_positioning.opponent_ledger import (
    OpponentLedgerReading,
    read_opponent_ledger,
)
from nse_algo_trader.participant_positioning.participant_positioning_source import (
    ParticipantCategory,
    ParticipantOpenInterestRow,
    ParticipantPositioningSnapshot,
    ParticipantPositioningSource,
)

__all__ = [
    "institutional_positioning_opposes_entry",
    "OpponentLedgerReading",
    "ParticipantCategory",
    "ParticipantOpenInterestRow",
    "ParticipantPositioningSnapshot",
    "ParticipantPositioningSource",
    "read_opponent_ledger",
]
