# research/142 — Trunk II SENSES · S2: structured support/resistance level extraction

**Slice:** S2 of the news/sentiment sense (follows S1 feed base, research/140). Turns the raw
headlines S1 already stores into **structured index price-level records** — the user's #1 ask:
"NIFTY/BankNifty support & resistance levels quoted in news."

**Status:** design → build. Deterministic, stdlib-only, real-data-verifiable NOW (market closed;
news + the 220 stored S1 headlines are the production input this slice consumes).

## 1. What it produces
For each stored `RawNewsItem` (title + summary) that references an index underlying, extract the
price levels it quotes and classify each:

```
ExtractedLevelSet{
    content_hash, source_id, source_name, title,
    underlying: "NIFTY" | "BANKNIFTY" | "FINNIFTY" | "MIDCPNIFTY" | "NIFTYNXT50",
    levels: tuple[ExtractedLevel{ value: float, kind: SUPPORT|RESISTANCE|PIVOT, confidence, evidence }],
    published_at,
}
```
Example, from a real stored headline — "Nifty closes below key 23,800 level on Gulf war ripples":
`{underlying: NIFTY, levels: [{value: 23800, kind: PIVOT, confidence: 0.7, evidence: "key 23,800 level"}]}`.

## 2. Sourcing pass (Rule I / sourcing-oss-parts) — verdict: BUILD BESPOKE (stdlib `re`)
Two WebSearch queries run (2026-07-26); repos/libs evaluated + vendor-or-reject recorded:
- **`trendln`, `boysugi20/python-stock-support-resistance`, scipy/k-means pivot detectors** — REJECTED:
  every OSS "support/resistance" library operates on a **historical price series** (pivot/prominence/
  clustering over OHLC), not on **news text**. Wrong input modality entirely.
- **Finance-NER (spaCy Matcher/EntityRuler, `number-spacy`, `word2number`, Prodigy finance NER)** —
  REJECTED for S2: these are general NLP building blocks that would need a trained model or heavy
  deps (spaCy + model ≈ 500 MB) to tag "price levels", and financial index levels are always
  **digit-structured** ("24,800", "51200"), never spelled out — so `word2number` buys nothing and
  spaCy's Matcher is just a heavier regex here. Kept as a candidate for S3+ ticker/entity linking
  (stock-name gazetteer), not needed for S2's index levels.
- **Verdict:** no OSS component does "extract analyst-quoted index S/R levels from Indian financial
  headlines" — it is bespoke. Build with stdlib `re` + a small index gazetteer + a plausibility band.
  Zero new dependencies. (Sources logged in BACKLOG under the S2 entry.)

## 3. Extraction method (bespoke, deterministic)
1. **Index gazetteer** — aliases → canonical underlying: `nifty`/`nifty 50`→NIFTY,
   `bank nifty`/`banknifty`/`nifty bank`→BANKNIFTY, `fin nifty`/`finnifty`→FINNIFTY,
   `midcap nifty`/`midcpnifty`→MIDCPNIFTY, `nifty next 50`/`niftynxt50`→NIFTYNXT50. (Sensex is
   detected for context but NOT emitted — it's a BSE index, out of Phase-1 scope per CLAUDE.md;
   recorded so we don't silently treat it as tradeable.)
2. **Number pattern** — Indian-format `\d{1,3}(?:,\d{3})*(?:\.\d+)?`, then a **plausibility band
   [5,000 – 100,000]**. This is drift-free (covers NIFTY ~24k and BANKNIFTY ~51k for years) and
   rejects the noise the real corpus is full of: years (2024/2026), counts ("5 factors", "6th
   session"), point-moves ("2,000 points" — a move, not a level → also filtered by requiring a
   level keyword, not a "points" keyword), prices ("$95"), "363 pts".
3. **Keyword-adjacency classification** — a number counts as a level ONLY when a level-context
   keyword sits within a small char window:
   - SUPPORT: support, supports, hold(s), holds above, floor, base, cushion, demand zone, buy zone
   - RESISTANCE: resistance, resist, hurdle, cap, ceiling, supply zone, target, upside
   - PIVOT (side unclear but a real level reference): level, key, psychological, mark, breaks/broke,
     closes/closed below|above, slips below, drags below, reclaims, crosses
   Nearest keyword wins; no keyword nearby ⇒ the number is NOT a level (precision guard).
4. **Confidence** — 0.8 explicit SUPPORT/RESISTANCE keyword adjacent to the number; 0.7 PIVOT
   keyword; scaled down if the underlying token is far from the number. Per-level; set confidence =
   max over its levels.

## 4. Wiring (Rule G / H / N)
- New module `news_level_extraction.py` (pure, no I/O) + `news_level_types.py` in `news_sentiment/`.
- Store: new `news_levels` table in `NewsSqliteStore` (content_hash, underlying, kind, value,
  confidence, evidence), `save_extracted_levels` / `load_recent_levels` / `level_count`.
- Runner `news_level_extraction_runner.py`: load recent stored items → extract → save levels.
- Live service: `_maybe_run_news_level_extraction` cadence (after ingestion) + `news_levels`
  dashboard surface (top levels per underlying) + manifest entry.
- **Named future consumer (Rule K, QUEUED):** S7 entry-gate consumer — NIFTY/BANKNIFTY S/R levels
  become option strike/stop context (size-down / defer near a fresh resistance). Read-only until S7.

## 5. Verification
- **Hermetic (Rule J):** unit tests over crafted headlines through the pure extractor — support,
  resistance, pivot, noise-rejection (years/counts/points/prices), multi-underlying, band edges.
- **Real-data (Rule F):** run over the 220 real S1-stored headlines; expect genuine levels from
  items like "Nifty closes below key 23,800 level" and "drags Nifty below 24,000", and expect
  noise ("2,000 points", "$95", "363 pts", "5 factors") to be rejected. Reported honestly.
