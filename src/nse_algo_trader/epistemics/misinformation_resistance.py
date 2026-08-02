"""Deception / misinformation resistance (Trunk XIII; research/132) — the epistemic immune system.

Treat each mechanism as an information SOURCE of beliefs; a source whose confident predictions are
systematically WRONG is misinformation. This organ scores a beta-reputation per source (credible vs
not, from calibrated-vs-confidently-wrong outcomes) and flags sources that are OVER-TRUSTED relative
to their credibility (high influence, low reputation) — the ones to resist. Sourcing (research/132):
subjective-logic / beta-reputation is the right algorithm but no clean package; built the beta
formula (α=good+1, β=bad+1), reference TrueSkill/SLEncodings. PURE (no I/O); reads the calibration board.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SourceCredibility:
    source: str                # the mechanism-as-information-source
    reputation: float          # beta-reputation in [0,1] — credibility of its confident beliefs
    influence: float           # share of decisions it drives
    experiment_count: int
    is_over_trusted: bool      # high influence, low reputation → resist


@dataclass(frozen=True)
class MisinfoReport:
    sources: tuple[SourceCredibility, ...] = field(default_factory=tuple)  # influence-desc
    flagged: tuple[str, ...] = field(default_factory=tuple)                # over-trusted-unreliable
    mean_reputation: float = 1.0
    summary: str = ""

    @property
    def is_clean(self) -> bool:
        return not self.flagged


def _beta_reputation(good: float, bad: float) -> float:
    """Beta-reputation: (good+1)/(good+bad+2) — a source with more confidently-correct than
    confidently-wrong evidence is credible; the +1/+2 prior keeps a thin source near 0.5."""
    return (good + 1.0) / (good + bad + 2.0)


def assess_source_credibility(
    board: list,
    over_trust_gap: float = 0.15,
    min_influence: float = 0.10,
) -> MisinfoReport:
    """Score each mechanism-source's beta-reputation from its calibration (credible = evidence the
    confident belief was borne out; not = confidently-wrong mass) and flag over-trusted sources.
    `board` = CalibrationBoardRow-like objects (`.mechanism_name`, `.experiment_count`,
    `.predicted_win_rate`, `.actual_win_rate`)."""
    total_n = sum(r.experiment_count for r in board)
    if total_n == 0:
        return MisinfoReport(summary="no sources to assess")

    sources: list[SourceCredibility] = []
    for r in board:
        n = r.experiment_count
        # confidently-wrong mass = how much the confident prediction over-stated the true outcome.
        overstatement = max(0.0, r.predicted_win_rate - r.actual_win_rate)
        good = r.actual_win_rate * n
        bad = overstatement * n
        reputation = _beta_reputation(good, bad)
        influence = n / total_n
        over_trusted = influence >= min_influence and (influence - reputation) >= over_trust_gap
        sources.append(SourceCredibility(
            source=r.mechanism_name, reputation=reputation, influence=influence,
            experiment_count=n, is_over_trusted=over_trusted,
        ))
    sources.sort(key=lambda s: s.influence, reverse=True)
    flagged = tuple(s.source for s in sources if s.is_over_trusted)
    mean_rep = sum(s.reputation * s.influence for s in sources)  # influence-weighted mean reputation
    summary = (
        f"{len(sources)} sources · influence-weighted reputation {mean_rep:.0%}"
        + (f" · RESIST (over-trusted, low-credibility): {', '.join(flagged[:3])}" if flagged
           else " · no over-trusted misinformation sources")
    )
    return MisinfoReport(
        sources=tuple(sources), flagged=flagged, mean_reputation=mean_rep, summary=summary,
    )
