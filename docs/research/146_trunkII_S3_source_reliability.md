# research/146 — Trunk II SENSES · S3: per-source reliability scoring (the trust keystone)

**Slice:** S3 of the news sense (research/140's build order; leapfrogged to do S4a–c at user request,
now filled in). The user's own keystone idea: **every news source earns a learned reliability score**,
so a low-trust source can't move the gate alone and corroborating independents combine. Trust-weights
everything S1/S2/S4 acquired; feeds the (queued) S7 entry gate.

## Sourcing (Rule I) — REUSE our own machinery, no external OSS
research/140 already specified reusing the VI/XIII trust organs; confirmed the primitives exist:
- **Beta-reputation** — `epistemics/misinformation_resistance._beta_reputation(good,bad)=(good+1)/
  (good+bad+2)` (XIII EPISTEMICS, research/132; subjective-logic/beta, no clean OSS package → bespoke).
  S3 reuses this exact formula, **tier-seeded** (priors below).
- **Stouffer's Z evidence combination** — `sentience/cross_modal_binding` (`combined_z = Σ ppf(conf)/√n`;
  `scipy.stats.norm`, already a dep). S3 reuses this to combine CORROBORATING sources.
- **Misinfo over-trust flag** — XIII `assess_source_credibility` (high influence + low reputation →
  resist). S3 applies the same idea to the SOCIAL tier once S5 lands.
No new dependency; this is assembly of found in-house pieces (building-features-from-ideas).

## Tier priors (the "advisory-until-proven" ladder from research/140)
Beta pseudo-counts seed each source by its tier, so a source starts where its class deserves and
moves as evidence accrues:
| Tier | good0 | bad0 | prior reliability | role |
|---|---|---|---|---|
| EXCHANGE_FILING (NSE/BSE) | 9 | 1 | 0.90 | primary truth — official filings |
| PUBLIC_NEWS (RSS/rendered) | 3 | 2 | 0.60 | modest prior — confirmation |
| BROKER_RESEARCH | 2 | 2 | 0.50 | neutral — earns per track record |
| SOCIAL (X/Telegram) | 1 | 3 | 0.25 | untrusted — advisory-until-proven |

## Reliability from signals available NOW (no market outcome needed)
`reliability = (good0 + fresh_polls + corroborated) / (good0+bad0 + fresh_polls + stale_polls + corroborated + …)`
- **Freshness track** is a REAL outcome-independent signal we already produce: a source delivering
  fresh items → +good; a source going STALE (staleness-rejected — the Moneycontrol-RSS trap) → +bad.
  So a chronically-stale feed is down-weighted with no market data at all.
- **Corroboration** (another source carrying the same claim) → +good (S7-facing; proxy now).

## STEP 1 — Target
`build_reliability_board(observations) -> ranked tuple[SourceReliability]` (PURE) + `combine_source_
confidences([...]) -> float` (Stouffer). A cadence assembles `SourceObservation`s from the store
(per-source item counts + tier) + latest freshness, computes the board, surfaces it.
- **Success test (Rule F):** the real board from the live store ranks NSE filings (EXCHANGE_FILING)
  top, fresh RSS/rendered news modest, and a stale-rejected feed below its fresh peers.

## STEP 2 — Build / wiring
- `news_source_reliability.py` (PURE): tier priors + `SourceObservation` + `source_reliability` +
  `build_reliability_board` + `combine_source_confidences` (Stouffer).
- Store: `source_item_counts()` → (source_id, source_name, tier, count) per source.
- Live service: `_maybe_run_source_reliability` (foreground, cheap — store read + latest freshness) →
  board cached; `news_source_reliability` surface + manifest.
- **PRIMARY consumer = S7** (weight each news item by its source reliability at the gate) — QUEUED
  (Rule K); read-only board until then, so the sense stays 🟡.

## STEP 3 — Verify
- Hermetic (Rule J): crafted observations → assert tier ordering, fresh boosts, stale penalises,
  Stouffer corroboration raises combined confidence above any single source.
- Real-data (Rule F): board from the real store + a real freshness poll → filings top, stale feed down.

## Rule K — queued after S3
- **Outcome-driven α/β accrual** (did the source's claim resolve true — level respected / catalyst
  hit?) → market/resolution-gated, same gate as council/society reputation. The board is prior+freshness
  until then. · Content-corroboration detection (same story across sources) · SOCIAL misinfo-flag (S5) ·
  **S7 entry-gate consumer (PRIMARY)** · S4d (proxy/vision, user-deferred).
