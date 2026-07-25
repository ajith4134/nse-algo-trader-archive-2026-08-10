"""Real NSE corporate-action records (splits/bonuses) + the parser that turns
NSE's free-text `subject` into a price-adjustment factor (research/62 §4a; §11.2).

A split or bonus makes the printed price drop overnight for a purely structural
reason (a 1:5 split divides the price by 5). A replayed price series that spans
such an ex-date would show that drop as a fake crash unless we know the action
and its ratio. This module is the Layer-2 source of that knowledge: it fetches
the real NSE corporate-action calendar (via `nselib`, acquired per Rule I) and
parses each record's `subject` into a `CorporateAction` carrying the multiplier
to apply to prices BEFORE the ex-date to bring them onto the post-action scale.

Only SPLIT and BONUS get a real factor (they cause the big structural gaps);
dividends / rights / other are carried as factor 1.0 (not adjusted for intraday
continuity — a documented limitation, BACKLOG).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Protocol


class CorporateActionType(str, Enum):
    SPLIT = "split"  # face-value sub-division, e.g. Rs 10 → Rs 2
    BONUS = "bonus"  # X free shares per Y held
    OTHER = "other"  # dividend / rights / etc. — no continuity adjustment


@dataclass(frozen=True)
class CorporateAction:
    """One NSE corporate action with the factor to multiply pre-ex-date prices
    by so a series across the ex-date stays continuous."""

    symbol: str
    ex_date: date
    action_type: CorporateActionType
    price_adjustment_factor: float  # e.g. 0.2 for a 1:5 split, 0.5 for a 1:1 bonus


_BONUS_SUBJECT = re.compile(r"bonus\s+(\d+)\s*:\s*(\d+)", re.IGNORECASE)
_SPLIT_SUBJECT = re.compile(
    r"from\s+(?:rs|re)\.?\s*([\d.]+).*?to\s+(?:rs|re)\.?\s*([\d.]+)",
    re.IGNORECASE | re.DOTALL,
)


def parse_corporate_action_subject(
    subject: str,
) -> tuple[CorporateActionType, float]:
    """Turn an NSE `subject` string into (type, price-adjustment factor).

    - "Bonus X:Y" (X free per Y held) → BONUS, factor = Y/(X+Y).
    - "Face Value Split ... From Rs A ... To Rs B" → SPLIT, factor = B/A.
    - anything else → OTHER, factor 1.0 (no continuity adjustment).
    """
    bonus = _BONUS_SUBJECT.search(subject)
    if bonus:
        free, held = int(bonus.group(1)), int(bonus.group(2))
        return CorporateActionType.BONUS, held / (free + held)
    if "split" in subject.lower() or "sub-division" in subject.lower():
        split = _SPLIT_SUBJECT.search(subject)
        if split:
            old_face, new_face = float(split.group(1)), float(split.group(2))
            if old_face > 0:
                return CorporateActionType.SPLIT, new_face / old_face
    return CorporateActionType.OTHER, 1.0


def corporate_action_from_nselib_row(row: dict) -> CorporateAction | None:
    """Build a `CorporateAction` from one `corporate_actions_for_equity` row
    (`symbol`, `exDate` like '24-Jun-2026', `subject`). Returns None if the
    ex-date is unparseable."""
    try:
        ex_date = datetime.strptime(str(row["exDate"]).strip(), "%d-%b-%Y").date()
    except (ValueError, KeyError):
        return None
    action_type, factor = parse_corporate_action_subject(str(row.get("subject", "")))
    return CorporateAction(
        symbol=str(row["symbol"]).strip(),
        ex_date=ex_date,
        action_type=action_type,
        price_adjustment_factor=factor,
    )


class CorporateActionSource(Protocol):
    """DI seam: production uses the nselib source; tests inject a fake."""

    def corporate_actions_by_symbol(
        self, from_date: date, to_date: date
    ) -> dict[str, list[CorporateAction]]: ...


class NseLibCorporateActionSource:
    """Real NSE corporate actions via `nselib` (imported lazily so this module
    loads without the dependency / network)."""

    def corporate_actions_by_symbol(
        self, from_date: date, to_date: date
    ) -> dict[str, list[CorporateAction]]:
        from nselib import capital_market

        frame = capital_market.corporate_actions_for_equity(
            from_date=from_date.strftime("%d-%m-%Y"),
            to_date=to_date.strftime("%d-%m-%Y"),
        )
        actions_by_symbol: dict[str, list[CorporateAction]] = {}
        for record in frame.to_dict("records"):
            action = corporate_action_from_nselib_row(record)
            if action is None or action.action_type is CorporateActionType.OTHER:
                continue
            actions_by_symbol.setdefault(action.symbol, []).append(action)
        return actions_by_symbol
