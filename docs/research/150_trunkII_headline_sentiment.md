# research/150 — Trunk II SENSES · headline sentiment (the polarity half + directional gate)

**Slice:** the SENTIMENT half of sentiment/news (D4, research/140). We have news EVENT risk (S7) but
no POLARITY — adverse vs favourable. This adds a headline sentiment score and makes the S7 news-event
gate DIRECTIONAL: an adverse-sentiment event on a symbol is riskier than a neutral one.

## Sourcing (Rule I) — D4 decided VADER + FinBERT; build behind a DI seam
research/138 verdict: **FinBERT (ProsusAI/finbert)** is the accurate primary (91–93% F1 on Indian
headlines) but a **~1.75 GB CPU-torch** install; **VADER** is light but weak on finance (a pre-filter).
Decision here: a `HeadlineSentimentScorer` **DI seam** so scorers are swappable, with a working
**finance-lexicon-boosted VADER** as the installed default (verified now), and **FinBERT as the drop-in
upgrade behind the same seam** (no rewiring; its 1.75 GB footprint is a user-gated install — flagged,
not silently pulled). VADER real-tested: base VADER scored "Buy … target" 0.00 (misses the bullish cue)
→ the finance lexicon boost fixes exactly this class.

## STEP 1 — Target
`HeadlineSentimentScorer.score(text) -> HeadlineSentiment(score∈[-1,1], label)`; the finance-VADER
impl seeds VADER's lexicon with market terms (miss/cut/downgrade/tumble negative; beat/upgrade/buy/
surge/target positive). Feeds: (a) a `news_sentiment` surface (most adverse/favourable headlines);
(b) the S7 gate — adverse sentiment AMPLIFIES a symbol's event risk (directional), favourable dampens.
- **Success test (Rule F):** real headlines score with correct sign — "Q1 miss, guidance cut" strongly
  negative, "Buy … target of Rs N" positive, "shares fall 2%" negative; the gate risk on an
  adverse-news symbol exceeds a neutral-news symbol of equal recency/reliability.

## STEP 2 — Build / wiring
- `headline_sentiment.py`: `HeadlineSentiment` dataclass + `HeadlineSentimentScorer` seam +
  `FinanceVaderSentimentScorer` (lexicon-boosted; lazy-imports vaderSentiment). `label_for(score)`.
- S7 `news_entry_gate`: `build_news_event_risk_by_symbol(..., sentiment_scorer=None)` — when provided,
  an item's risk contribution is scaled by an adverse-sentiment factor (neutral = ×1, strongly adverse
  = ×1.5, favourable = ×0.7), so the gate leans on BAD news. Still reliability-floored + advisory-until-
  earned (safety unchanged).
- Service: build the scorer once; pass to the gate builder; `news_sentiment` dashboard surface (score
  distribution + the most-adverse recent headlines) + manifest. Dep `vaderSentiment`.

## STEP 3 — Verify
- Hermetic (Rule J): finance headlines → correct sign/label; a fake scorer drives the directional
  gate factor; neutral vs adverse symbol risk ordering.
- Real-data (Rule F): score the real stored headlines → correct polarity; adverse-news symbol risk >
  neutral-news symbol.

## Rule K — after this
FinBERT scorer behind the seam (1.75 GB — user-gated install) as the accuracy upgrade · LLM-pool
materiality escalation (FinBERT-triage → LLM confirm, research/138) · sentiment column persisted in the
store · per-sector/market-mood aggregate.
