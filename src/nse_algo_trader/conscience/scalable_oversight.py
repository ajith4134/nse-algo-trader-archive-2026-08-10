"""Scalable oversight (Trunk VII; research/116) — CONSCIENCE competence-ceiling gate.

As the bot takes more decisions than any overseer can individually check, safety requires selective
escalation: cheap/confident decisions run autonomously; consequential-and-uncertain ones are
escalated to stronger oversight before acting (AI-safety-via-debate / iterated amplification). The
bot already has the oversight MECHANISMS (debate panel, prediction council); this organ is the
meta-policy that decides WHICH decisions need that scrutiny, plus a hard COMPETENCE CEILING — it
will not autonomously authorise a decision that is both high-stakes AND low-confidence (there is no
human in the paper loop to escalate to, so the safe default is: don't act beyond your competence).
PURE (no I/O) — the state gate calls `classify_oversight` at the entry sites.
"""

from __future__ import annotations

from dataclasses import dataclass

# Oversight tiers — self-describing.
OVERSIGHT_AUTONOMOUS = "autonomous"        # confident enough to act unsupervised
OVERSIGHT_PANEL_REVIEW = "panel_review"    # permitted, but flagged for the debate/council panel
OVERSIGHT_HUMAN_REVIEW = "human_review"    # beyond autonomous competence → blocked (defer)


@dataclass(frozen=True)
class OversightPolicy:
    autonomous_confidence: float = 0.62   # win-prob ≥ this ⇒ no escalation needed
    low_confidence_floor: float = 0.55    # win-prob < this ⇒ deeply uncertain


@dataclass(frozen=True)
class OversightDecision:
    tier: str
    permit_autonomous: bool
    reason: str


def classify_oversight(
    win_probability: float, is_high_stakes: bool,
    policy: OversightPolicy = OversightPolicy(),
) -> OversightDecision:
    """Decide the oversight tier for a proposed decision from its confidence and stakes. A
    high-stakes AND low-confidence decision is beyond autonomous competence (HUMAN_REVIEW → blocked);
    moderate confidence permits action but flags it for the panel; confident acts autonomously."""
    if win_probability < policy.low_confidence_floor and is_high_stakes:
        return OversightDecision(
            OVERSIGHT_HUMAN_REVIEW, False,
            f"high-stakes + low-confidence ({win_probability:.0%}) — beyond autonomous competence, "
            "escalated (deferred; no human overseer in the loop)",
        )
    if win_probability < policy.autonomous_confidence:
        return OversightDecision(
            OVERSIGHT_PANEL_REVIEW, True,
            f"moderate confidence ({win_probability:.0%}) — permitted under panel scrutiny "
            "(debate/council)",
        )
    return OversightDecision(
        OVERSIGHT_AUTONOMOUS, True,
        f"confident ({win_probability:.0%}) — autonomous action within competence",
    )


@dataclass(frozen=True)
class OversightSummary:
    autonomous: int
    panel_review: int
    human_review_blocked: int

    @property
    def total(self) -> int:
        return self.autonomous + self.panel_review + self.human_review_blocked

    @property
    def autonomous_share(self) -> float:
        return self.autonomous / self.total if self.total else 0.0

    @property
    def headline(self) -> str:
        if self.total == 0:
            return "no decisions classified yet"
        return (
            f"{self.total} decisions: {self.autonomous} autonomous · {self.panel_review} panel · "
            f"{self.human_review_blocked} blocked (beyond competence)"
        )


def summarize_oversight(
    autonomous: int, panel_review: int, human_review_blocked: int
) -> OversightSummary:
    return OversightSummary(autonomous, panel_review, human_review_blocked)


# ---------------------------------------------------------------------------------------------
# B16: stakes are an AMOUNT OF MONEY AT RISK, not an instrument class.
#
# Every option entry passed `is_high_stakes=True` unconditionally while every cash entry passed
# False. Combined with the memory recalibration pushing option win-probabilities to 0.07-0.36, that
# blocked essentially EVERY option entry — the single most direct cause of "index options = 0" —
# while a cash position of ten times the rupee risk passed unexamined.
#
# A Rs 5,000 defined-risk spread is not higher-stakes than a Rs 50,000 cash position; it is an order
# of magnitude LOWER. The gate itself is correct and is kept: high-stakes AND low-confidence is
# genuinely beyond autonomous competence. Only the stakes MEASURE changes.
# ---------------------------------------------------------------------------------------------

#: A decision risking at least this fraction of account capital is high-stakes, whatever it trades.
HIGH_STAKES_RISK_FRACTION_OF_CAPITAL = 0.01


def is_high_stakes_by_risk_amount(
    risk_amount: float | None,
    account_capital: float | None,
    risk_fraction_threshold: float = HIGH_STAKES_RISK_FRACTION_OF_CAPITAL,
) -> bool:
    """Is this decision high-stakes, measured by money at risk relative to capital?

    Unknown risk or capital returns True (fail-SAFE): if we cannot size the stake, we must not
    assume it is small. That keeps the conservative behaviour exactly where uncertainty is real,
    instead of applying it to a whole instrument class.
    """
    if risk_amount is None or account_capital is None:
        return True
    if account_capital <= 0:
        return True
    return (abs(float(risk_amount)) / float(account_capital)) >= risk_fraction_threshold
