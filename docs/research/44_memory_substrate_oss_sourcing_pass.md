# 44 — Memory Substrate: OSS Sourcing Pass (retroactive, sourcing-oss-parts skill)

Retroactive `sourcing-oss-parts` pass on the Layer-10 `SqliteExperienceMemory`
(built in slices 1–3), to check whether a mature OSS agent-memory / episodic-
experience library should have been vendored instead of hand-built. Complements
research/43 (which chose the STORAGE substrate). License-blind per Rule E.

## The piece's shape (what we're matching against)
IN: a graded §9 prediction + its closed trade — **already-structured typed
records** (strategy, mechanism, regime, instrument-kind, predicted-vs-actual
outcome, win-prob, Brier, realized return), not free text. OUT: calibration-by-
regime, prior-outcomes (entry-time pre-mortem), reflection-diff, per-mechanism
calibration board, assumption tripwires, antibody veto set. Constraints:
Python, embeddable/offline single-node, minimal deps, swappable interface.
**This is structured-record analytics with forecast-calibration queries — NOT
RAG-over-chat semantic memory.**

## Candidates found (search by function: agent-memory · trade-journal · calibration)
| Candidate | What it is | Fit | Verdict |
|---|---|---|---|
| **Cognee / Mem0 / Zep / Letta / Graphiti / LangMem** | LLM agent memory over TEXT/facts (vector store · temporal KG · editable context) | Wrong shape — extract facts from unstructured text for RAG; heavy/LLM-oriented. Cognee's embedded default stack uses **KùzuDB (deprecated)**. | **Reject** (mismatch; confirms research/43) |
| **structjour** (MikePia) | SQLite-backed daily trade-review **app** (GUI) | Not a library/protocol; no calibration/reflection engine | **Reject** — but confirms SQLite is standard for trade journals |
| erma0x/trading_journal, mransbro | CSV / Flask trade-log apps | Apps, not components | Reject |
| **python-prediction-scorer** (yhoiseth) | Proper scoring rules for predictions — **Brier, Logarithmic, Practical, Quadratic**. MIT, 100% test coverage, dependency-free, Python 3.8+, active (63 commits) | **Scoring-only** (no store/cohort/reflection) — but a clean, tested implementation of MORE proper scoring rules than our Brier-only grading | **Borrow (queued)** — vendor the extra scoring-rule formulas |
| **briertools** | Brier decomposition (calibration/discrimination), reliability | Enrichment for the reflection board's reliability view | Note — borrow later |
| **sklearn.calibration.calibration_curve** | Reliability-diagram reference (mature) | Reference for a reliability-curve panel | Note — reference |

## Verdict
**Keep `SqliteExperienceMemory` as built.** A genuine 3-angle sweep confirms no
OSS library does the WHOLE feature: the agent-memory frameworks are text/RAG-
shaped (and drag in heavy or deprecated deps), the trade-journal projects are
apps not components, and the calibration libraries are scoring-only. The two
halves (a structured episodic store + a forecast-calibration/reflection engine)
do not come pre-integrated for structured trade experiences — hand-building the
thin SQLite store behind the swappable `ExperienceMemory` protocol was the right
call (and the protocol still lets us swap to a graph KG later — research/43).

## The borrow I missed (actionable — Rule G named consumer)
**`python-prediction-scorer` (MIT).** Our §9 grading
(`prediction_lab/prediction_outcome_grading.py`) computes **Brier only**. Its
four proper scoring rules (add **Logarithmic** + **Quadratic**) give a richer,
less-degenerate calibration signal for the reflection board + assumption
tripwires (Brier saturates; the log score punishes confident-wrong harder —
exactly the "predicted 85% / actual 0%" case). **Queued borrow:** vendor-and-
adapt those two formulas into a `proper_scoring_rules.py` (provenance: yhoiseth/
python-prediction-scorer, MIT), wire into grading + the reflection board.
`briertools` (Brier decomposition) + `sklearn.calibration` are secondary
references for a future reliability-curve panel.

## Provenance note
Nothing vendored in THIS pass (substrate confirmed as-is). The queued borrow
above must carry a provenance comment (source repo + MIT + what was changed)
when implemented, per the sourcing-oss-parts skill.
