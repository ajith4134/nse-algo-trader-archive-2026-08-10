"""Hermetic test for Trunk XV memory consolidation + semantic memory (research/135): well-supported
episodic mechanisms are consolidated into semantic facts (gated by sample size = gradual transfer);
thin ones are not; confidence rises with sample size; query works. Pure, no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass

from nse_algo_trader.memory_reflection.memory_consolidation import consolidate_to_semantic


@dataclass
class _Row:
    mechanism_name: str
    experiment_count: int
    predicted_win_rate: float
    actual_win_rate: float


def test_high_sample_mechanism_is_consolidated():
    board = [_Row("orb_long", 40, 0.68, 0.70)]
    mem = consolidate_to_semantic(board, min_sample=15)
    assert mem.fact_count == 1
    f = mem.facts[0]
    assert f.subject == "orb_long" and abs(f.hit_rate - 0.70) < 1e-9
    assert abs(f.reliability - (1 - abs(0.68 - 0.70))) < 1e-9
    assert "hit-rate 70%" in f.statement


def test_thin_mechanism_is_not_consolidated():
    board = [_Row("thin", 5, 0.9, 0.9)]  # below min_sample → not yet knowledge
    mem = consolidate_to_semantic(board, min_sample=15)
    assert mem.fact_count == 0 and "not yet stable" in mem.summary


def test_confidence_rises_with_sample_size():
    small = consolidate_to_semantic([_Row("a", 20, 0.5, 0.5)]).facts[0]
    large = consolidate_to_semantic([_Row("a", 200, 0.5, 0.5)]).facts[0]
    assert large.confidence > small.confidence


def test_facts_sorted_by_confidence_and_query():
    board = [_Row("a", 20, 0.5, 0.5), _Row("b", 200, 0.5, 0.5)]
    mem = consolidate_to_semantic(board, min_sample=15)
    assert mem.facts[0].subject == "b"  # more samples → higher confidence → first
    assert mem.query("a")[0].subject == "a" and mem.query("zzz") == ()


def test_empty_board():
    mem = consolidate_to_semantic([], min_sample=15)
    assert mem.fact_count == 0
