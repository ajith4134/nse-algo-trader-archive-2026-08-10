"""Semantic memory (Trunk XV; research/135) — the consolidated general-knowledge store.

Distinct from EPISODIC memory (raw §9 outcomes, already built) and the temporal knowledge graph:
semantic memory holds the stable, generalisable FACTS the consolidation engine distils from many
episodes ("mechanism X has hit-rate Y with reliability Z over N experiences"). Queryable general
knowledge, the neocortical end of complementary-learning-systems consolidation. PURE (no I/O).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SemanticFact:
    subject: str          # the mechanism the fact is about
    condition: str        # the context it holds under ("all" or a market regime)
    hit_rate: float
    reliability: float    # 1 − |predicted − actual| calibration accuracy
    sample_size: int
    confidence: float     # rises with sample size (how settled the fact is)
    statement: str        # human-readable knowledge


@dataclass(frozen=True)
class SemanticMemory:
    facts: tuple[SemanticFact, ...] = field(default_factory=tuple)  # confidence-desc

    @property
    def fact_count(self) -> int:
        return len(self.facts)

    def query(self, subject: str) -> tuple[SemanticFact, ...]:
        """The consolidated facts about a subject (mechanism)."""
        return tuple(f for f in self.facts if f.subject == subject)

    @property
    def summary(self) -> str:
        if not self.facts:
            return "no consolidated knowledge yet (episodic experiences not yet stable enough)"
        top = self.facts[0]
        return (f"{self.fact_count} consolidated fact(s); strongest: {top.statement} "
                f"(confidence {top.confidence:.0%})")
