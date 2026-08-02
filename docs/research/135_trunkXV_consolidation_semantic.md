# XV — consolidation engine + semantic memory  ·  research/135

**Trunk XV MEMORY & KNOWLEDGE BASE.** Design doc (Rule D). Sourcing: real WebSearch (July 2026) —
findings below.

## Sourcing (real search)
Query: "python library memory consolidation episodic to semantic cognitive architecture extract
patterns". Closest prior art:
- **`apattichis/cognitive-memory-agent`** (github.com/apattichis/cognitive-memory-agent) — an LLM-
  chatbot cognitive architecture with 4 memory systems + a periodic consolidation process:
  **cluster (by embedding cosine similarity) → merge (an LLM synthesises each cluster into one
  memory) → promote (extract recurring patterns to procedural rules)**. The RIGHT conceptual shape
  (cluster→merge→promote), but **LLM/embedding/RAG-coupled for conversational TEXT** — wrong shape for
  our numeric trading experiences (calibration board / regime cohorts). **Verdict: reference the
  pattern, BUILD bespoke** over the numeric memory (group by mechanism×regime, promote stable
  high-sample patterns to semantic facts — no embeddings/LLM needed).
- Academic: episodic-semantic consolidation papers (arxiv 2605.17625, 2602.07261) — theory, no code.
[Sources: github.com/apattichis/cognitive-memory-agent · arxiv.org/abs/2605.17625]

## The ideas (complementary learning systems — hippocampal → neocortical)
- **Consolidation engine** — episodic experiences (specific graded §9 outcomes) are gradually
  consolidated into SEMANTIC facts (stable, generalisable knowledge) — but only once enough evidence
  accrues (the sample-size gate = the gradual transfer). "In many trending sessions, ORB-long hit
  70%" becomes a semantic fact, distinct from any single episode.
- **Semantic memory** — the queryable store of those consolidated facts (general knowledge), distinct
  from the episodic store (raw events, already 🟢) and the temporal graph (already 🟢).

## Targets
- `consolidate_to_semantic(board, min_sample, min_confidence) -> SemanticMemory` — promote each
  well-supported mechanism (n ≥ min_sample) to a `SemanticFact`. Success test: a high-sample
  mechanism becomes a fact with the right hit-rate/reliability; a thin one is NOT promoted (gradual
  transfer).
- `SemanticMemory.query(subject)` returns the consolidated facts about a subject.

## Component parts (`memory_reflection/` — the memory trunk's home)
- `memory_reflection/semantic_memory.py` — `SemanticFact`(subject, condition, hit_rate, reliability,
  sample_size, confidence, statement) + `SemanticMemory`(facts, query, summary).
- `memory_reflection/memory_consolidation.py` — `consolidate_to_semantic` (episodic board → semantic
  facts, gated by sample size = the consolidation transfer).

## Wiring (Rule G/N)
Daily `_maybe_run_memory_consolidation` consolidates the real calibration board into the semantic
store, caches it. Dashboard surface `semantic_memory` (fact count + top facts). READ-ONLY (the
consumer — querying semantic facts to inform decisions — is queued, Rule K; retrieval already exists
for episodic).

## Verification
- Hermetic (Rule J): high-sample mechanism → promoted fact with correct fields; thin mechanism → not
  promoted; `query` returns the right facts; confidence rises with sample size.
- Real-data (Rule F): over the real §10 memory, consolidate the real board into semantic facts and
  print the knowledge base.

## Atlas impact
consolidation engine + semantic memory 🔴→🟢. XV MEMORY 4🟢→6🟢 (5🔴 left). Overall built 58→60/197 (30.5%).
