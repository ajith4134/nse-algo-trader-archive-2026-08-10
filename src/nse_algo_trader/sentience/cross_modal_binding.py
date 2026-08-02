"""Cross-modal binding (Trunk VIII; research/130).

Different faculties observe the SAME situation from different "modalities" — microstructure, memory,
safety, LLM. When several INDEPENDENT modalities corroborate the same proposition (e.g. "elevated
risk"), binding them yields a higher-confidence BOUND percept than any single modality — the binding
that turns separate signals into one perception. Sourcing (research/130 / research/125): anchored on
`scipy.stats.norm` Stouffer-Z evidence combination (pyds/Dempster-Shafer archived; pgmpy/bayespy
overkill). PURE (no I/O).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from scipy.stats import norm

_CLIP = 1e-4  # keep norm.ppf finite at the 0/1 extremes


@dataclass(frozen=True)
class ModalitySignal:
    modality: str          # microstructure / memory / safety / llm
    confidence: float      # 0..1 — this modality's confidence in the proposition
    supports: bool         # does this modality support the proposition?


@dataclass(frozen=True)
class BoundPercept:
    proposition: str
    bound_confidence: float
    corroborating_modalities: tuple[str, ...]
    modality_count: int
    is_bound: bool
    summary: str = ""
    contributing: tuple[ModalitySignal, ...] = field(default_factory=tuple)


def bind_percept(signals: list, proposition: str) -> BoundPercept:
    """Bind the supporting modality signals into one percept. Confidences are combined with
    Stouffer's Z so INDEPENDENT corroboration raises confidence above any single modality; a lone
    modality keeps its own confidence. `is_bound` iff ≥2 distinct modalities support."""
    supporting = [s for s in signals if s.supports]
    distinct = sorted({s.modality for s in supporting})
    if not supporting:
        return BoundPercept(proposition, 0.0, (), 0, False,
                            f"no modality supports '{proposition}'")

    zs = [norm.ppf(min(1 - _CLIP, max(_CLIP, s.confidence))) for s in supporting]
    combined_z = sum(zs) / (len(zs) ** 0.5)   # Stouffer: √n in the denominator
    bound_confidence = float(norm.cdf(combined_z))
    is_bound = len(distinct) >= 2

    summary = (
        f"'{proposition}': {'BOUND' if is_bound else 'single-modality'} confidence "
        f"{bound_confidence:.0%} across {len(distinct)} modalit{'ies' if len(distinct)!=1 else 'y'} "
        f"({', '.join(distinct)})"
    )
    return BoundPercept(
        proposition=proposition, bound_confidence=bound_confidence,
        corroborating_modalities=tuple(distinct), modality_count=len(distinct),
        is_bound=is_bound, summary=summary, contributing=tuple(supporting),
    )
