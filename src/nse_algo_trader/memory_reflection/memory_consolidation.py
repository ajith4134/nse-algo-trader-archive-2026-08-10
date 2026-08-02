"""Memory consolidation engine (Trunk XV; research/135) — episodic → semantic transfer.

Complementary-learning-systems consolidation: specific episodic §9 experiences are gradually
consolidated into stable SEMANTIC facts — but only once enough evidence accrues (the sample-size gate
IS the gradual transfer; a thin, unsettled pattern is not yet knowledge). Sourcing (research/135):
references `cognitive-memory-agent`'s cluster→merge→promote pattern but built bespoke over the numeric
calibration board (that library is LLM/embedding-coupled for text — wrong shape). PURE (no I/O).
"""

from __future__ import annotations

from nse_algo_trader.memory_reflection.semantic_memory import SemanticFact, SemanticMemory


def consolidate_to_semantic(
    board: list, min_sample: int = 15, confidence_scale: int = 20
) -> SemanticMemory:
    """Consolidate the episodic calibration board into semantic facts. Only mechanisms with
    `experiment_count ≥ min_sample` are PROMOTED (the gradual episodic→semantic transfer); each
    becomes a `SemanticFact` with a settled-ness `confidence` that rises with sample size. `board` =
    CalibrationBoardRow-like (`.mechanism_name`, `.experiment_count`, `.predicted_win_rate`,
    `.actual_win_rate`)."""
    facts: list[SemanticFact] = []
    for r in board:
        if r.experiment_count < min_sample:
            continue  # not yet enough evidence to consolidate into knowledge
        reliability = max(0.0, 1.0 - abs(r.predicted_win_rate - r.actual_win_rate))
        confidence = r.experiment_count / (r.experiment_count + confidence_scale)
        facts.append(SemanticFact(
            subject=r.mechanism_name, condition="all", hit_rate=r.actual_win_rate,
            reliability=reliability, sample_size=r.experiment_count, confidence=confidence,
            statement=(f"'{r.mechanism_name}' has hit-rate {r.actual_win_rate:.0%} "
                       f"(reliability {reliability:.0%}) over {r.experiment_count} experiences"),
        ))
    facts.sort(key=lambda f: f.confidence, reverse=True)
    return SemanticMemory(facts=tuple(facts))
