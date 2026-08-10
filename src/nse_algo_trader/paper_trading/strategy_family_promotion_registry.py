"""L4 — the multi-strategy promotion pipeline: a per-family state machine gated by the L2 validation engine.

Every strategy family (ORB, credit-spread, 0-DTE, intraday mean-reversion, …) earns its way up a ladder
INDEPENDENTLY on its OWN real closed trades — breadth without sprawl, because the validation gate is the
filter that decides which families ever touch capital (redesign §5 promotion pipeline; research/170).

Stages: RESEARCH → PAPER → SHADOW → REDUCED_LIVE → FULL_LIVE (+ HALTED). Paper is always permitted; every
stage from SHADOW up is where an edge is being *proven*; only REDUCED_LIVE/FULL_LIVE touch real money and
additionally need a human go-live flag. A live family whose edge decays is AUTO-DEMOTED to SHADOW — the
antibody for whole families, not just mechanisms.

Advancement is EARNED, never elapsed-time: a family advances only when, on its own trades, the L2 gate says
PROMOTE (honest-N DSR + MinBTL + holdout, deflated by that family's cumulative trial count) AND it has real
regime coverage (seen a drawdown + a vol spike, not just calendar days). Persistent SQLite state so the
ladder survives restarts.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path

_LOGGER = logging.getLogger(__name__)

DEFAULT_STRATEGY_FAMILY_PROMOTION_DB_PATH = Path(
    "~/.nse_algo_trader/strategy_family_promotion.sqlite3"
).expanduser()


class PromotionStage(str, Enum):
    RESEARCH = "research"        # brand-new family; not yet trading even paper
    PAPER = "paper"             # trading paper only; gathering an edge verdict
    SHADOW = "shadow"           # edge earned on paper; trading shadow (signals logged, still no capital)
    REDUCED_LIVE = "reduced_live"  # human-approved; small real capital
    FULL_LIVE = "full_live"     # human-approved; full real capital
    HALTED = "halted"           # explicitly stopped (never acts)


#: The forward ladder (demotion always drops to SHADOW). Index gives the ordering for "at least" checks.
_LADDER = (
    PromotionStage.RESEARCH, PromotionStage.PAPER, PromotionStage.SHADOW,
    PromotionStage.REDUCED_LIVE, PromotionStage.FULL_LIVE,
)
_LADDER_RANK = {stage: i for i, stage in enumerate(_LADDER)}
_LIVE_STAGES = frozenset({PromotionStage.REDUCED_LIVE, PromotionStage.FULL_LIVE})


@dataclass(frozen=True)
class FamilyPromotionState:
    family: str
    stage: PromotionStage
    edge_earned: bool          # did the L2 gate PROMOTE this family on its last eval?
    deflated_sharpe: float
    trades_evaluated: int
    regime_coverage_met: bool
    last_reason: str
    updated_at: str


class StrategyFamilyPromotionRegistry:
    """Per-family promotion-stage store + the earned-advancement / edge-decay-demotion policy."""

    def __init__(
        self,
        db_file_path: Path = DEFAULT_STRATEGY_FAMILY_PROMOTION_DB_PATH,
        now_provider=datetime.now,
    ) -> None:
        db_file_path.parent.mkdir(parents=True, exist_ok=True)
        self._now = now_provider
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(str(db_file_path), check_same_thread=False)
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute(
            """CREATE TABLE IF NOT EXISTS family_promotion (
                family TEXT PRIMARY KEY,
                stage TEXT NOT NULL,
                edge_earned INTEGER NOT NULL,
                deflated_sharpe REAL NOT NULL,
                trades_evaluated INTEGER NOT NULL,
                regime_coverage_met INTEGER NOT NULL,
                last_reason TEXT NOT NULL,
                updated_at TEXT NOT NULL)"""
        )
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()

    def ensure_family(self, family: str, initial_stage: PromotionStage = PromotionStage.PAPER) -> None:
        """Register a family the first time it is seen (default PAPER — paper trading is always allowed)."""
        with self._lock:
            try:
                self._connection.execute(
                    "INSERT OR IGNORE INTO family_promotion VALUES (?,?,?,?,?,?,?,?)",
                    (family, initial_stage.value, 0, 0.0, 0, 0, "registered", self._now().isoformat()),
                )
                self._connection.commit()
            except Exception:  # noqa: BLE001 — never break the loop on a bookkeeping write
                _LOGGER.exception("ensure_family failed for %s", family)

    def stage_of(self, family: str) -> PromotionStage:
        with self._lock:
            row = self._connection.execute(
                "SELECT stage FROM family_promotion WHERE family=?", (family,)
            ).fetchone()
        return PromotionStage(row[0]) if row else PromotionStage.PAPER

    def may_trade_paper(self, family: str) -> bool:
        """Paper trading allowed unless the family is explicitly HALTED."""
        return self.stage_of(family) is not PromotionStage.HALTED

    def may_trade_live(self, family: str) -> bool:
        """Real capital allowed only at REDUCED_LIVE / FULL_LIVE (a human-approved stage)."""
        return self.stage_of(family) in _LIVE_STAGES

    def record_evaluation(
        self,
        family: str,
        edge_promoted: bool,
        deflated_sharpe: float,
        trades_evaluated: int,
        regime_coverage_met: bool,
        manual_go_live_approved: bool = False,
    ) -> PromotionStage:
        """Apply one validation eval to the family's stage and return the new stage.

        Advancement (earned): PAPER→SHADOW needs edge_promoted + regime coverage; SHADOW→REDUCED_LIVE and
        REDUCED_LIVE→FULL_LIVE additionally need the human go-live flag. Demotion: any live/shadow family
        that LOSES its edge (not promoted) drops to SHADOW (never silently keeps trading capital)."""
        self.ensure_family(family)
        current = self.stage_of(family)
        new_stage, reason = self._next_stage(
            current, edge_promoted, regime_coverage_met, manual_go_live_approved
        )
        with self._lock:
            try:
                self._connection.execute(
                    """UPDATE family_promotion SET stage=?, edge_earned=?, deflated_sharpe=?,
                       trades_evaluated=?, regime_coverage_met=?, last_reason=?, updated_at=?
                       WHERE family=?""",
                    (new_stage.value, int(edge_promoted), float(deflated_sharpe), int(trades_evaluated),
                     int(regime_coverage_met), reason, self._now().isoformat(), family),
                )
                self._connection.commit()
            except Exception:  # noqa: BLE001
                _LOGGER.exception("record_evaluation failed for %s", family)
        return new_stage

    @staticmethod
    def _next_stage(
        current: PromotionStage, edge_promoted: bool, regime_coverage_met: bool, manual: bool
    ) -> tuple[PromotionStage, str]:
        if current is PromotionStage.HALTED:
            return current, "halted (manual)"
        # Edge decay: a family past PAPER that loses its edge is demoted to SHADOW (or held at PAPER).
        if not edge_promoted:
            if _LADDER_RANK[current] > _LADDER_RANK[PromotionStage.SHADOW]:
                return PromotionStage.SHADOW, "edge decayed — demoted from live to shadow"
            if current is PromotionStage.SHADOW:
                return PromotionStage.PAPER, "edge lost in shadow — back to paper"
            return current, "no edge yet — stays in paper"
        # Edge present: advance one rung if the gate for the NEXT rung is satisfied.
        if current in (PromotionStage.RESEARCH, PromotionStage.PAPER):
            if regime_coverage_met:
                return PromotionStage.SHADOW, "edge earned + regime coverage — promoted to shadow"
            return current, "edge earned but regime coverage incomplete — stays in paper"
        if current is PromotionStage.SHADOW:
            if manual and regime_coverage_met:
                return PromotionStage.REDUCED_LIVE, "shadow edge held + human go-live — reduced live"
            return current, "shadow edge held; awaiting human go-live"
        if current is PromotionStage.REDUCED_LIVE:
            if manual:
                return PromotionStage.FULL_LIVE, "reduced-live edge held + human go-live — full live"
            return current, "reduced-live edge held; awaiting human full-live approval"
        return current, "edge held at full live"

    def halt(self, family: str, reason: str) -> None:
        self.ensure_family(family)
        with self._lock:
            self._connection.execute(
                "UPDATE family_promotion SET stage=?, last_reason=?, updated_at=? WHERE family=?",
                (PromotionStage.HALTED.value, f"HALTED: {reason}", self._now().isoformat(), family),
            )
            self._connection.commit()

    def snapshot(self) -> dict:
        """All families' promotion states, for the dashboard promotion board (Rule N)."""
        with self._lock:
            rows = self._connection.execute(
                """SELECT family, stage, edge_earned, deflated_sharpe, trades_evaluated,
                   regime_coverage_met, last_reason, updated_at FROM family_promotion
                   ORDER BY family"""
            ).fetchall()
        families = [
            FamilyPromotionState(
                family=r[0], stage=PromotionStage(r[1]), edge_earned=bool(r[2]),
                deflated_sharpe=r[3], trades_evaluated=r[4], regime_coverage_met=bool(r[5]),
                last_reason=r[6], updated_at=r[7],
            )
            for r in rows
        ]
        counts: dict[str, int] = {}
        for f in families:
            counts[f.stage.value] = counts.get(f.stage.value, 0) + 1
        return {
            "families": [
                {"family": f.family, "stage": f.stage.value, "edge_earned": f.edge_earned,
                 "deflated_sharpe": round(f.deflated_sharpe, 3), "trades": f.trades_evaluated,
                 "regime_coverage": f.regime_coverage_met, "reason": f.last_reason}
                for f in families
            ],
            "stage_counts": counts,
            "live_families": [f.family for f in families if f.stage in _LIVE_STAGES],
        }

    def snapshot_json(self) -> str:
        return json.dumps(self.snapshot())
