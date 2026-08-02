"""B32 · 0-DTE carried risk-state — the fast time-stop + daily loss cap the live path enforces.

0-DTE options decay FAST, so the engine needs two risk controls beyond the system's existing
end-of-day square-off (which already force-closes every option from 15:15 IST — reused, not rebuilt):

  1. A per-position TIME-STOP — a 0-DTE position not resolved within `time_stop_minutes` is cut, so
     a thesis that has not played out stops bleeding theta while waiting for a natural target/stop.
  2. A daily 0-DTE LOSS CAP — once cumulative realised 0-DTE loss for the day breaches the cap, NO new
     0-DTE entries open that day (theta days bleed via many small losses; the cap halts the bleed).

This object is the single carrier of that state across scan passes. Pure logic (no clock, feed, or
broker) so the whole policy is testable; the live path calls `register_opened` on entry,
`time_stopped_position_ids` each pass, and `record_closed` on every 0-DTE close. State auto-rolls at a
new session date so the loss cap is per-day.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta


@dataclass(frozen=True)
class ZeroDteRiskConfig:
    #: minutes after entry at which an unresolved 0-DTE position is force-cut.
    time_stop_minutes: int = 45
    #: cumulative realised 0-DTE LOSS (rupees, positive number) for the day past which no new 0-DTE
    #: entry opens. Default sized for the paper account; the live path may override from config.
    daily_loss_cap_rupees: float = 25_000.0


@dataclass
class ZeroDteRiskState:
    config: ZeroDteRiskConfig = field(default_factory=ZeroDteRiskConfig)
    _opened_at_by_position_id: dict[str, datetime] = field(default_factory=dict)
    _realized_pnl_today: float = 0.0
    _session_date: date | None = None

    def _roll_session_if_new_day(self, now: datetime) -> None:
        """Reset the per-day loss tally when the session date changes (the cap is per-day)."""
        if self._session_date != now.date():
            self._session_date = now.date()
            self._realized_pnl_today = 0.0

    def register_opened(self, position_id: str, opened_at: datetime) -> None:
        self._roll_session_if_new_day(opened_at)
        self._opened_at_by_position_id[position_id] = opened_at

    def time_stopped_position_ids(self, now: datetime) -> list[str]:
        """Open 0-DTE positions whose time-stop deadline has passed — the live path force-closes these."""
        deadline_age = timedelta(minutes=self.config.time_stop_minutes)
        return [
            position_id
            for position_id, opened_at in self._opened_at_by_position_id.items()
            if now - opened_at >= deadline_age
        ]

    def record_closed(self, position_id: str, realized_pnl: float, now: datetime) -> None:
        """Drop a closed position from the open set and fold its realised P&L into the day's tally."""
        self._roll_session_if_new_day(now)
        self._opened_at_by_position_id.pop(position_id, None)
        self._realized_pnl_today += realized_pnl

    def permits_new_entry(self, now: datetime) -> bool:
        """False once the day's cumulative 0-DTE LOSS has breached the cap — halts new entries only,
        never blocks closing/square-off of existing positions."""
        self._roll_session_if_new_day(now)
        return self.realized_loss_today() < self.config.daily_loss_cap_rupees

    def realized_loss_today(self) -> float:
        """The day's realised 0-DTE LOSS as a positive number (0.0 if the day is net positive)."""
        return max(-self._realized_pnl_today, 0.0)

    def remaining_loss_budget(self, now: datetime) -> float:
        self._roll_session_if_new_day(now)
        return max(self.config.daily_loss_cap_rupees - self.realized_loss_today(), 0.0)

    def open_position_count(self) -> int:
        return len(self._opened_at_by_position_id)
