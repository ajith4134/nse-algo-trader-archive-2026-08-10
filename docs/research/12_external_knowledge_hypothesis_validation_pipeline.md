# 12 — External Knowledge → Validated Hypothesis Pipeline

You asked for an AI feature that reads books, articles, blogs, and
community discussion about NSE trading strategies, turns it into memory,
and maps it into knowledge the system can use — but the critical design
question is: how does the system avoid just *believing* a blog post?
`research/10` shows several widely-repeated NSE claims (circuit "magnet
effect," GIFT Nifty accuracy %, pre-open predicting the day) are folklore,
not fact — this is exactly why nothing extracted from external text can
be trusted directly. This file researches real prior art for that specific
problem and proposes a pipeline.

**Status: research only. Nothing implemented.**

## The core finding: this pipeline already exists commercially — just not for informal sources

**Quantpedia** (quantpedia.com, operating since 2011) is the closest real
production analog. Its documented process: ingest academic papers →
extract the trading rule in plain language, performance, and risk
characteristics → catalog in a structured schema → **independently
re-implement and backtest out-of-sample in QuantConnect** before
publishing it as reliable, explicitly checking whether out-of-sample
performance matches what the source paper claimed. That's
**informal-claim → structured-rule → independent-empirical-validation →
gated-publication** — exactly the target architecture, running at scale
for over a decade. It's built for academic papers, not blogs/forums, but
the architecture transfers directly.

**Michael Harris / Price Action Lab** (practitioner, book *Fooled by
Technical Analysis*, 2015) systematically tests popular technical-analysis
folk claims for statistical significance and data-mining bias, and finds
most such "edges" decay within 1-5 days — useful precedent for treating
any validated rule as perishable, not permanent.

## Real hybrid text+data systems (partial matches)

**RD-Agent(Q)** (Microsoft Research, NeurIPS 2025, open-source) genuinely
reads research papers/financial reports *and* mines data-driven patterns,
implements hypotheses as code, and backtests on real markets — but its
validation is performance-metric-based (IC, ARR), not explicitly gated by
Deflated Sharpe Ratio/CPCV significance testing the way this project
already plans (`research/01`, `04`). It answers "yes" to text-sourced
hypotheses, "partial" on statistical rigor.

**AlphaAgent** (KDD 2025, peer-reviewed) builds anti-overfitting checks
directly into LLM-driven hypothesis generation (originality checks,
hypothesis-factor alignment scoring, complexity limits) — functionally
similar to what DSR/CPCV do, enforced earlier in the pipeline.

**A 2025 preprint** on interpretable hypothesis-driven trading explicitly
targets LLM-generated natural-language hypotheses with walk-forward
validation, citing Campbell Harvey's recommendation that data-mined
factors need a t-stat above 3.0, not the traditional 2.0 — a directly
reusable, harder bar for hypotheses sourced from an effectively unbounded
text corpus.

## A genuinely new risk this research surfaced: LLM pretrained-knowledge leakage

A finding worth flagging on its own: if an LLM is asked to *judge* whether
a historical trading claim worked, it may already know market history from
its own pretraining — a lookahead-bias vector distinct from classic
backtest overfitting. **The fix is architectural**: the LLM must only
*extract structure* from text (condition, predicted effect, instrument,
timeframe, direction) — it must never render the truth verdict itself.
All statistical judgment happens in a deterministic backtest engine
against real NSE data, completely separate from the LLM.

## What community/forum mining looks like today

Peer-reviewed work exists on mining Reddit (r/WallStreetBets) for
collective-intelligence signal, and on meme-stock narrative diffusion. **No
dedicated project was found mining India-specific forums** (r/IndianStreetBets,
TradingView India ideas) at scale for recurring claims — a real, current
gap, not an oversight in this research.

## Provenance/confidence tracking — a gap in every memory framework already researched

Checked directly against official docs of the three memory frameworks from
`research/05`: **none ship a built-in "validation status" field.** Graphiti
has strong source-provenance (every fact traces to a source "episode") and
bi-temporal validity windows, but no protected confidence field — you'd
add one via a custom entity type. Cognee tracks some evidence
directionality per relationship in case studies, not as a general schema
field. Mem0 has source/timestamp attribution but no validation-status
enum. This is confirmed to be an active, named unsolved problem in current
2026 agent-memory research (multiple preprints exist specifically about
provenance-grounded agent memory), not something this project is failing
to find — it genuinely doesn't exist off-the-shelf yet.

## Proposed pipeline for this project

1. **Strict role separation.** The LLM's only job is extraction: source
   text → a structured hypothesis object (`condition`, `predicted_effect`,
   `instrument/market`, `timeframe`, `direction`). It never judges whether
   the claim is true. All truth-judgment happens in the existing
   deterministic DSR/CPCV pipeline against real NSE data. This directly
   closes the pretrained-knowledge-leakage risk above.
2. **A custom `TradingHypothesis` schema**, bolted onto whichever memory
   substrate Layer 10 uses (`research/06`, `research/09`): `source_url`,
   `source_type` (book/article/blog/forum/paper), `extraction_date`,
   `raw_claim_text`, `structured_rule`, `validation_status` (`untested` →
   `in_validation` → `confirmed` / `rejected` / `decayed`), `dsr_stat`,
   `cpcv_pass_rate`, `last_validated`, `next_revalidation_due`. None of
   the researched memory frameworks ship this natively — it has to be
   added deliberately, consistent with `research/06`'s "explainable memory
   must be built in from day one" finding.
3. **Honest trial-count accounting.** Because the corpus of blogs/forums
   is effectively unbounded, *every* extracted claim — accepted or
   rejected — must count toward the Deflated Sharpe Ratio's
   number-of-trials correction, not just the ones that reach backtest.
   Apply a harder bar (Harvey's t-stat > 3.0) to text-mined hypotheses
   than to internally-derived factors, since the search space is wider
   and less principled.
4. **Dedup before backtesting.** Embed each extracted rule and check
   similarity against the existing hypothesis registry first — "upper
   circuit stocks show momentum" reworded fifty ways across fifty blogs
   should collapse to one trial, both for compute cost and for not
   silently corrupting the trial-count accounting in point 3.
5. **Decay/re-validation loop, not one-shot validation.** Schedule
   periodic re-tests of `confirmed` hypotheses on rolling NSE windows
   (Harris's finding that most such edges live 1-5 days is the reason
   why); auto-downgrade to `decayed` on a failed re-test so the playbook
   self-corrects instead of accumulating stale confirmations.
6. **Start with `research/10`'s five claims as the seed backlog** — they
   are already extracted and partially graded; running them through this
   exact pipeline (once built) is the natural first real test of the
   pipeline itself, not just a claims list waiting on someone else's
   pipeline.

## What this means for the plan

This is a concrete refinement of `research/06` feature #1 (autonomous
web-research agent) and feature #2 (win/loss pattern mining) — previously
described in general terms, now with an actual mechanism: extraction is
LLM-driven and untrusted, validation is deterministic and mandatory, and
provenance/decay tracking is a schema decision that has to be made before
Layer 10 starts, not retrofitted. Slots into Layer 10 (Memory &
Reflection), category F of the AI atlas (`research/09`).
