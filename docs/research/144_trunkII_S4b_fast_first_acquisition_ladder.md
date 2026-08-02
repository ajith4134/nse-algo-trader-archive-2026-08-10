# research/144 — Trunk II SENSES · S4b: fast-first news acquisition ladder (near-live capture)

**Slice:** S4b of S4-advanced (research/143). Turns news acquisition into a **method-selection ladder**
that captures fresh headlines FAST and cheaply, and surfaces the "new headlines this poll" delta —
the "line-by-line live updates" the user asked for.

## The empirical finding that drove the design (Rule F spike, 2026-07-26)
A `curl_cffi` static fetch (Chrome-impersonated TLS) of the Moneycontrol markets page returned **HTTP
200, 602 KB, in 0.3 s**, and the S4a pure extractor pulled the **same 22 headlines** the 40 s Chromium
render produced. → **The headlines are in the static HTML.** So we do NOT need a 40 s browser render
for these pages; a sub-second fetch works, which makes a SHORT-cadence (near-live) poll feasible.

## Sourcing (research/143 Agent B + C — already done; this reuses those verdicts)
- **`curl_cffi` (lexiforest/curl_cffi) → USE.** Agent C's #1 ban-resistance tool: impersonates a real
  Chrome TLS/JA3 fingerprint (defeats the layer that instantly flags `requests`/`httpx`). Installed +
  real-tested (0.3 s fetch, 200). Also the fetcher S4c (NSE/BSE) will reuse.
- **changedetection.io → considered, NOT adopted as a sidecar here.** Agent B loved it, but Agent C
  explicitly sanctioned "lift its `difflib`-based diff pattern directly into the pipeline instead of
  running the service." Our **store already dedups by `content_hash`**, so `save_news_items()`'s
  `items_new` IS the "only new lines" delta — in-process, no separate Docker service / RSS-polling
  failure domain, hermetically testable. changedetection.io stays a backlog option if we ever need its
  3 s visual-diff on a page whose headlines are NOT in static HTML and change intra-item.

## STEP 1 — Target
`LadderNewsAcquisitionSource.poll(now)` → per site, get headlines by the CHEAPEST method that works:
1. **fast** — `curl_cffi` static fetch (~0.3 s) → extract; if it yields headlines, done.
2. **render** — fall back to S4a's Crawl4AI Chromium (~40 s) only when fast yields nothing (JS-only page).
Returns the same `FeedPollResult` shape → flows through the existing `NewsIngestionRunner` → store.
The store-dedup delta (`items_new`) = NEW headlines since last poll = the live-update signal.
- **Success test (Rule F):** on the real box, the ladder captures Moneycontrol headlines via the FAST
  method in <1 s/site, stores them, and a second poll reports the correct new-vs-seen delta.

## STEP 2 — Parts (mostly already built)
- fast fetch (NEW) — `curl_cffi` behind a DI seam · render fallback (REUSE S4a `render_page_html`) ·
  headline extractor (REUSE S4a `extract_headlines_from_html`) · site registry (REUSE
  `RENDER_TARGET_SITES`) · dedup-store delta (REUSE `NewsSqliteStore`) · ingestion runner (REUSE).
- Only genuinely new code: `fast_news_fetch.py` (curl_cffi seam) + `news_acquisition_ladder.py` (the
  ladder) + the cadence/surface. This is the building-features-from-ideas "thin glue over found pieces".

## STEP 3 — Build / wiring
- `fast_news_fetch.py`: `fast_fetch_html(url)` — `curl_cffi` impersonate chrome, timeout, returns "" on
  failure (behind DI seam; only prod imports curl_cffi — Rule J).
- `news_acquisition_ladder.py`: `LadderNewsAcquisitionSource(sites, fast_fetch, render_fetch)` — fast→
  render per site, records the winning method; never raises per site.
- Live service: **evolve** the S4a cadence — `_maybe_run_rendered_news_ingestion`/`news_rendered`
  surface become `_maybe_run_news_acquisition`/`news_acquisition` running the LADDER (background thread,
  ~5 min cadence; fast-first so usually <1 s, thread covers the rare Chromium fallback). Surface shows
  new-this-poll delta + per-method mix. Old render-only cadence/surface retired (folded into the ladder
  — S4a's `render_page_html` lives on as the fallback rung; no orphan, Rule G). `RenderedNewsPageSource`
  class removed (superseded); its pure functions + registry stay.
- Dep: `curl_cffi` added to pyproject.

## STEP 4 — Verify
- Hermetic (Rule J): fake fast/render seams → assert ladder prefers fast, falls back to render when
  fast is empty, tracks method, and one bad site never breaks the poll.
- Real-data (Rule F): run the ladder over the real Moneycontrol pages → fast method wins <1 s/site,
  headlines stored; re-poll → correct new-vs-seen delta.

## Rule K — queued after S4b
S4c curl_cffi + NSE/BSE announcements (reuses the fast fetcher) · S4d vision + residential proxy (403
sites) · more render targets · S3 source reliability · S7 entry-gate consumer (PRIMARY — sense 🟡).
changedetection.io sidecar kept as an option for intra-item live-diff pages if ever needed.
