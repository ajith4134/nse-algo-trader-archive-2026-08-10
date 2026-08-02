# Dual directional AI agents (BULL vs BEAR, evidence-gathering, self-correcting)

**Seed (user's words):** *"an advanced AI feature that decides which side the trade should be placed —
direction for BUY/CE — and another AI feature for the down side PE/SELL; both gather EVIDENCE on why the
AI should open the trade in the direction they suggest, and it LEARNS as it gets wrong. Ultra-advanced.
Evidence = order-book depth, volume profile, etc., all ML/DL + advanced things. Deep complex
institutional-grade code with complex logic and justified LOC — a real software, not simple code."*
**Date:** 2026-08-02 · **Status:** 🔵 exploring (5 research agents) · IS the directional core of [idea #1](main_ai_brain_all_strategies.md)

---

## 1. The bigger picture (expand-idea)

This is **the LONG/SHORT/FLAT directional-decision core of idea #1's brain** — specified as **two
opposing evidence-engines + an arbiter**:
- **BULL agent** → calibrated **P(up)** + the evidence for going long / buying CE.
- **BEAR agent** → calibrated **P(down)** + the evidence for buying PE / selling.
- **ARBITER (meta-labeling)** → resolves the two into **LONG / SHORT / FLAT** + bet size.

Category one level up = **directional signal generation with abstention + adversarial verification.**
This is the well-known **BULL/BEAR + arbiter** pattern (in your crypto-bot DECISIONS.md + nse-crypto-bot-final).

**Refinement (user, 2026-08-02): each agent is its OWN autonomous BOT** — not a shared function. Each of
BULL/BEAR has **its own complete architecture** (own model stack, own feature/data pipeline, own
calibration layer, own online-learner, own state/memory store, own SHAP evidence log) and **its own data
needs**. They subscribe to the same raw feed but each runs a dedicated, independently-versioned,
independently-trained processing chain — so BULL can be retrained/replaced without touching BEAR. This is
the ultra-advanced, institutional framing (two production bots + an arbiter, ~thousands of LOC each).

**Refinement #2 (user, session-reset 2026-08-02): each bot gets its own EVIDENCE-GATHERING organs beyond
price/microstructure** — **candle/OHLCV data · autonomous ONLINE RESEARCH · and (mainly) per-stock NEWS
data** for every symbol it tracks — and each **decides in BOTH segments** (direction → cash long/short
AND options CE/PE). So a bot's thesis is built from quant (LOB, volume-profile, ML/DL) **+ news/event
sentiment + online research**, all timestamped point-in-time. ⚠️ **This makes each bot the "lethal
trifecta"** (untrusted web/news + credentials + trading) → the news/research organ MUST sit behind a
**Dual-LLM quarantine** (§2b). [→ RESEARCH agent-news, agent-nlp, agent-security]

**The load-bearing reframe (what keeps it institutional, not a toy):**
1. **NOT a chat debate.** Two LLMs arguing = the committee anti-pattern (underperforms budget-matched;
   self-correction without ground truth *degrades*). Each "agent" is a **calibrated probabilistic MODEL**
   (LightGBM/DeepLOB), the arbiter is a **meta-model**, and resolution is **deterministic**. [→ agent-1]
2. **Both agents firing high → FLAT.** A system contradicting itself is not confident. Abstention is a
   first-class action.
3. **"Learns as it gets wrong" = online update from REALIZED P&L** (hard ground truth) + a meta-model over
   the trade ledger — NEVER the model grading itself (that degrades). [→ agent-5]
4. **Evidence = feature attribution (SHAP) + a declared mechanism**, so every decision carries an
   auditable "why", not a black-box vote. [→ agent-4/5]

## 2. Architecture (deep, Rule-P — modules, not a scalar)
```
              ┌─────────── shared EVIDENCE / feature bus ───────────┐
              │ order-book depth: OFI, queue/depth imbalance,        │
              │   microprice, book pressure, Kyle's λ, VPIN [agent-2]│
              │ volume profile: POC, VAH/VAL, HVN/LVN, CVD [agent-3] │
              │ ML/DL: LightGBM + DeepLOB features, regime, technical │
              │ KRONOS candlestick foundation-model forecast (§2c)   │
              │ NEWS/event sentiment (behind Dual-LLM quarantine)    │
              └───────────────┬──────────────────┬──────────────────┘
                              ▼                  ▼
                   ┌────────────────┐   ┌────────────────┐
                   │ BULL model     │   │ BEAR model     │   each: calibrated P + SHAP evidence
                   │ P(up)+evidence │   │ P(down)+evid.  │
                   └───────┬────────┘   └───────┬────────┘
                           └────────┬───────────┘
                                    ▼
                     ┌────────────────────────────────┐
                     │ ARBITER (meta-labeling)         │  → LONG / SHORT / FLAT + size
                     │ both-high→FLAT; calibrated;     │     (act only if E[edge]>cost, idea #2 Wall-1)
                     │ deterministic resolution        │
                     └───────────────┬────────────────┘
                                     ▼  realized P&L
                     ┌────────────────────────────────┐
                     │ ONLINE LEARNER + META-MODEL     │  river drift-detect · champion/challenger ·
                     │ (learns from REALIZED outcomes) │  meta-model over ledger · calibration tracking
                     └────────────────────────────────┘
```
Maps onto existing repo (`predictive_core`, `strategy_engine`, directional agents, `memory_reflection`
ledger) — extend, don't rebuild.

## 2c. Evidence organ — KRONOS candlestick foundation model (user IG post DbO5FVYgd19, 2026-08-02)
The post = **Kronos** (Tsinghua, AAAI-2026, **MIT**, HuggingFace `NeoQuasar/Kronos-small` +
`Kronos-Tokenizer`; 33k★/5.7k forks; BSQ tokenizer coarse+fine subtokens → causal-transformer,
autoregressive). **Feed last 400 candles → predicts next 120 (OHLC + volume).** API:
`pred = KronosPredictor(model, tok, max_context=512); forecast = pred.predict(df=klines[-400:], pred_len=120)`.

**How it plugs into the two bots (this is the point of the post):**
1. **Shared forecast organ, opposite tails.** Run Kronos **Monte-Carlo** (sample the autoregressive
   forecast N times) → a *distribution* over the next 120 candles → derive `P(up)`, expected return,
   expected vol, quantile bands, forecast-uncertainty. **BULL bot reads the up-tail** (P(up)/expected
   up-move) as one evidence feature; **BEAR bot reads the down-tail.** Same model, opposite reads.
2. **Finetune on NSE candles** (both the tokenizer AND predictor adapt — frame 5) on NIFTY / Bank Nifty /
   stock K-lines the project already has → base model was trained on global/crypto, MUST be NSE-finetuned
   (Rule F). One of the concrete first build steps.
3. **It is EVIDENCE, not a signal.** Frame 6's own catch = *"raw signals are not pure alpha; no costs, no
   risk neutralization; research tool, not money printer."* → Kronos output must **beat the linear +
   LightGBM baseline** on NSE data, flow into the meta-labeling arbiter, and clear the **net-EV + risk
   gate** (idea #2 Wall-1). NEVER trade raw Kronos. It's one organ beside LOB, volume-profile, news, ML/DL.
4. **⚠️ SECURITY (crypto-bot's own finding, FEATURES §10):** loading HF weights = **untrusted binary**
   (weights can carry object code — xz-utils-style). **Pin by content hash · prefer safetensors over
   pickle · run inference sandboxed / network-isolated.** Ties to the dual-LLM/security organ (agent-security).
5. **⚠️ Maturity caveat (crypto-bot sourcing):** last push ~Apr-2026 (verify current); `max_context=512`
   is a hard limit (the 400→120 shape is a *constraint*, not tuning). Re-verify version + safetensors
   before vendoring (sourcing-oss-parts). Vendored under MIT — no license issue (Rule E; personal use).

## 2d. ONLINE-RESEARCH organ — browser + scrape + vision-LLM (user ask 2026-08-02, live GitHub data via `gh`)
The bots gather live data/news from pages (Moneycontrol etc.) three ways — **all three, layered**, and
ALL behind the Dual-LLM quarantine (§7-security): the reader is tool-less/credential-less and emits only
**inert structured data**, never text or actions.

| Approach | Best OSS (live ⭐, verified via gh 2026-08-02) | Use |
|---|---|---|
| **1. HTML scrape → clean data** | **crawl4ai** ⭐75.8k Apache-2.0 (ALREADY in project) · firecrawl ⭐159k AGPL (installed as MCP, needs key) | default: fast, LLM-friendly markdown from a page/RSS link |
| **2. Agentic browser (TYPES + navigates like a human)** | **browser-use** ⭐107.6k **MIT** (the standout for "typing + accessing pages") · Skyvern ⭐22.6k AGPL (vision+LLM, unseen sites) · stagehand ⭐23.7k MIT (Playwright+AI) · Playwright (base) | when a page needs login/search/JS clicks (Moneycontrol live quote, screener) |
| **2b. ANTI-DETECTION browser (defeat anti-bot gates)** | **Camoufox** (`daijro/camoufox`) ⭐10.7k **MPL-2.0** — Firefox fork w/ **C++-level fingerprint spoofing**, Playwright-compatible **Python** API (user IG find, verified 2026-08-02) | **THE fix for the 403/anti-bot walls the news agent hit on NSE/BSE/Moneycontrol** + tipster sources (idea #7). Drive browser-use/Playwright THROUGH Camoufox so scrapes look like a real browser. Still behind the Dual-LLM quarantine. |
| **3. SCREENSHOT → local vision-LLM → structured data** | **MiniCPM-V** ⭐26k Apache · **Qwen-VL** ⭐19.7k Apache · moondream ⭐9.9k Apache · GOT-OCR2.0 ⭐8.2k · markitdown ⭐170k (img→md) | robust fallback when scraping is blocked/anti-bot or the number is only rendered as an image — Playwright/browser-use screenshots the panel → **local install** VLM reads it → JSON |

**Recommended stack:** **crawl4ai (have it) for scrape → browser-use (MIT) for agentic type/navigate →
screenshot + a LOCAL vision-LLM (MiniCPM-V / Qwen-VL, install freely) for the anti-bot/image-only cases.**
Prefer regulatory feeds + RSS first (§7-news); use the browser/VLM path only where those don't reach.

**⚠️ Security (non-negotiable, ties to §7-security):** a browser agent reading untrusted pages IS the
lethal trifecta. The scraper/browser-agent/VLM = the **quarantined reader**: no credentials, no trading
tools, network-egress-limited; its ONLY output is typed structured data (price, sentiment, event tag) into
the deterministic gate — a page (or text-in-image) that says "BUY now" can at most perturb a *value*, never
reach the trading model or place an order. License note: firecrawl/Skyvern are AGPL — fine for private
non-distributed use (Rule E), but crawl4ai/browser-use (MIT/Apache) are cleaner if distribution ever matters.

## 2e. The organ's DATA-TARGET CATALOG (user 2026-08-02: "gather ALL news + any other additional data")
The online-research organ is the **universal external-data acquisition layer** — not just news. It's a
**shared subsystem** (feeds the bots idea #4, the brain idea #1, the radar idea #2). Everything it gathers
is timestamped point-in-time, keyed by ISIN/symbol, emitted as **inert structured data behind the Dual-LLM
quarantine**. Full target catalog (each → source → method):

| # | Data target | Source(s) | Method |
|---|---|---|---|
| 1 | **News** (done §7-news) | NSE/BSE announcements · Indian press RSS · GDELT | feed/RSS/scrape |
| 2 | **Corporate actions / event calendar** | NSE/BSE filings · results/dividend/split/bonus/M&A/board-meeting dates | feed + scrape |
| 3 | **Analyst data** | ratings/target-price/upgrades-downgrades · consensus estimates | scrape (Trendlyne/Tickertape) |
| 4 | **Ownership & FLOWS** | **FII/DII daily flows** · **participant-wise OI** (client/pro/FII/DII) · bulk/block deals · promoter pledging · shareholding-pattern change | NSE feed + scrape |
| 5 | **Macro / economic** | RBI policy · CPI/WPI/GDP/IIP · **global cues** (GIFT-Nifty, Dow fut, crude, DXY, US10Y) · **USDINR** | scrape/API |
| 6 | **Sector / peer context** | sector indices · peer moves · sector rotation/news | feed + scrape |
| 7 | **Options-derived** | **India VIX** · PCR · max-pain · OI buildup · IV | market feed + web aggregators |
| 8 | **Sentiment / social** | X/Twitter finance · StockTwits-analog · forums · Google Trends | API/scrape (quarantined, low-trust) |
| 9 | **Fundamental / alt** | quarterly results numbers · ratios/valuation (Screener.in/Tickertape) · **concall transcripts** · credit ratings (CRISIL/ICRA) · SEBI orders | scrape/VLM |
| 10 | **Calendar/context** | holiday · expiry · budget/RBI event dates · muhurat | static + feed |

**Design:** one **acquisition-scheduler** dispatches per-target collectors (feed poller · RSS · crawl4ai ·
browser-use · vision-LLM) → each collector emits **typed structured records** to an append-only,
point-in-time **evidence store** → the bots/brain/radar consume from the store, never from raw pages. Flows
(#4) and macro/global cues (#5) are especially high-value for *direction* (FII/DII + global cues drive the
NSE open) — prioritize those beyond raw news. Low-trust sources (#8 social) get heavier corroboration + the
FDR/net-EV gate before they ever size a trade.

**Connector-mining source (user IG find, verified 2026-08-02):** **Fincept Terminal**
(`Fincept-Corporation/FinceptTerminal`) ⭐29.4k — an open-source "Bloomberg alternative" advertising
**100+ data sources** + AI research + institutional workflows. **Mine its data-source connectors** (esp.
any Indian/NSE feeds) as ready adapters for this catalog (sourcing-oss-parts, owed), and use its
terminal UX as a dashboard reference. Evaluate — don't adopt the whole app; we build our own.

**⚠️ Owed (Rule K):** exact per-source API/RSS endpoints, rate limits, and free-vs-paid for targets 2–9
were NOT freshly verified (WebSearch exhausted this session) — a source-verification research pass is
queued for when budget resets (BACKLOG). Reuse what the project already has (news_sentiment,
participant_positioning/VPIN, universe_registry) — don't rebuild.

## 3. The honest walls (carry these or it's a toy)
- **Direction is HARD** — intraday direction ≈ near-random; label noise; the prior build measured a
  "40.3% anti-signal" on real data. → mandatory **linear + LightGBM baseline gate** every model must beat.
- **Order-flow is ~contemporaneous, not predictive** — OFI ~65% *concurrent* R² but only **~3%
  predictive** (idea #2). Evidence ≠ forecast. [→ agent-2]
- **NN's are overconfident** → **calibration (Platt/isotonic/temperature) before sizing** is mandatory.
- **Self-correction degrades** without ground truth → learn only from realized P&L + hard evaluator.
- **Volume-profile levels are largely descriptive/self-fulfilling** → gate through validation. [→ agent-3]

## 4. Depth / Rule-P justification (why thousands of LOC are real, not padding)
Cohesive modules, each load-bearing: (a) evidence feature-bus (LOB + volume-profile + technical, streaming
incremental) · (b) BULL model + (c) BEAR model (LightGBM + optional DeepLOB, triple-barrier labels, purged
CV) · (d) calibration layer · (e) meta-labeling arbiter · (f) online-learner + drift detection + champion/
challenger · (g) SHAP evidence store + mechanism declaration · (h) full tests (unit + property + adversarial
+ real-data). Heavyweight libs integrated: **LightGBM · PyTorch (DeepLOB) · river · SHAP · scikit-learn
calibration · statsmodels · mlfinlab meta-labeling** (verify — public repo may be stubbed).

## 5. Base → Advanced → Ultra
- **Base ✅:** BULL + BEAR = two calibrated **LightGBM** classifiers on LOB+volume-profile+technical
  features; meta-labeling arbiter → LONG/SHORT/FLAT; online update from realized P&L; SHAP evidence.
- **Advanced 🚀:** add **DeepLOB** (CNN+LSTM on raw book) as a second evidence source gated by the
  baseline; drift-adaptive online learning; meta-model over the ledger; full mechanism-declaration trail.
- **Ultra 🌌:** regime-conditional agents, adversarial self-testing (each agent tries to refute the
  other's evidence), calibrated ensemble disagreement as its own FLAT signal, continual learning with
  replay + champion/challenger auto-promotion.

## 6. Open questions (to finalize)
1. First model class — LightGBM-only baseline first (recommend), or LightGBM + DeepLOB from the start?
2. Segment for the first directional core — NIFTY options direction, or cash?
3. Decision cadence — per-tick, per-minute-bar, or on radar-signal (idea #2) trigger?
4. How much DL — is DeepLOB in scope now, or after the GBT baseline proves out?

## 7. Research findings
**Fresh research RE-RUNNING after session reset (2026-08-02) — folding in as agents complete.** Prior
preliminary block (below) stands; fresh findings appended per-topic.

### 7-lob. Order-book depth + volume-profile evidence (fresh agent) ✅
**Confirms the wall — these are CONTEXT features, not standalone alpha:**
- **OFI** (Cont-Kukanov-Stoikov): strong *contemporaneous* (R²≈40% but that's look-ahead); **properly
  lagged forecast: in/out-of-sample R² ~3.4%/3.05%, hit-ratio 53%, Sharpe 0.12** → cannot trade alone.
- **Microprice** (Stoikov): one of the FEW with genuine short-horizon *predictive* value (where mid
  settles) — worth including. **VPIN**: flash-crash "early warning" **rebutted** (Andersen-Bondarenko:
  peaked AFTER, co-moves with volatility). **Kyle's λ**: contemporaneous liquidity/impact, use to size
  slippage not forecast. **L1 imbalance: most spoofable** — use multi-level book pressure.
- **Volume profile (POC/VAH/VAL/HVN/LVN/CVD/footprint):** **ZERO peer-reviewed predictive studies** —
  Steidlmayer practitioner heuristics, **plausibly self-fulfilling** → use as regime/level CONTEXT, not
  signal. VWAP evidenced for *execution*, not direction.
- **⚠️ NSE data:** Kite = **5-level depth only** (`price/quantity/orders` ×5); full **tick-by-tick (TBT)
  order-by-order feed is co-lo/leased-line only, NOT retail** → OFI/VPIN/Lee-Ready are **approximations**
  on 5-level snapshots + trade prints. Document as lower-fidelity proxies.
- **OSS:** `mlfinlab`/`pymlfinance` (microstructure — Kyle/Amihud/Hasbrouck λ, VPIN, tick-rule) ·
  `sstoikov/microprice` · `py-market-profile`/`volprofile` (POC/VA) · CVD/HVN hand-rolled in pandas/Polars.
- **→ design:** microstructure + volume-profile are WEAK/CONTEXT features in the multi-factor bot, never
  primary alpha; realistic OFI-class ceiling ~3% R². (Reinforces: Kronos/news/regime must carry the load,
  all gated.)

### 7-news. Per-stock NSE news acquisition (fresh agent) ✅
- **Tier 1 — regulatory ground truth:** NSE/BSE **corporate-announcement** JSON feeds (results, board
  meetings, ratings, block/insider deals) — anti-bot gated (cookie + **3 req/s**), so use a maintained
  wrapper (`NseIndiaApi`/`nsepython`/`bsedata`). **Keyed by symbol → no NLP disambiguation** — highest
  signal.
- **Tier 2 — Indian press RSS:** Moneycontrol/ET/BS/Livemint/CNBC-TV18 via **feedparser** → full text via
  **crawl4ai (already in project)** / **trafilatura**.
- **Tier 3 — aggregators:** **GDELT DOC 2.0** (free, no key, tone-scored, since 2017) + **Marketaux**
  (entity/exchange tagging — test). ⚠️ Finnhub/AlphaVantage/Polygon = **US-centric, unreliable for NSE**.
- **Entity→ticker:** key on **ISIN** (stable across renames), alias table, require corroboration or discard
  (mis-attribution worse than a miss).
- **⚠️ Point-in-time (critical):** timestamp by exchange **DISSEMINATION** time (not "filed"); **append-only
  immutable log** (symbol, source, publish_ts, content-hash); record `publish_ts` AND `bot_observed_ts` →
  use `bot_observed_ts` as the backtest floor (kills look-ahead); normalize IST.

### 7-nlp. News→signal NLP (fresh agent) ✅
- **Models:** **finbert-tone** (yiyanghkust) / **ProsusAI/finbert** (best out-of-box); **FinGPT** (LoRA,
  finetune ~$17 on one GPU); general models FAIL on finance (negation, "beat/miss estimates", hedged
  guidance). Indian: English press FinBERT-ok; vernacular needs **IndicBERT/MuRIL**; NSE filings = XBRL,
  more extractable than prose.
- **Event extraction > sentiment:** NER+entity-link → event-type classify (earnings/M&A/rating/order/mgmt/
  regulatory/dividend, each a directional prior) → **numeric surprise (actual vs consensus)** — hard
  numbers dominate soft tone. Signal = per-article score → **novelty-discount (dedup)** → **time-decay
  (hours–days half-life)** → news-volume weight → aggregate.
- **🔴 Honest alpha:** real only in the **first minutes** + **small/illiquid** names; decays fast,
  arbitraged in liquid large-caps by HFT. **Derwent/Twitter-mood** (87.6% claim → fund closed ~2yr → didn't
  replicate) = the cautionary tale.
- **🔴 LLM LOOK-AHEAD contamination** (Glasserman-Lin): an LLM knows post-cutoff outcomes + "distraction
  effect" → **for historical backtests use FinBERT (non-generative) or restrict to post-training-cutoff
  dates or anonymize entities**; LLMs only for LIVE inference.

### 7-security. Dual-LLM quarantine — MANDATORY for the news/research organ (fresh agent) ✅
- **Lethal trifecta confirmed** (Willison): read-untrusted + credentials + act = existential; **the order
  stream IS the actuator** (no separate exfil channel needed). Real incidents (Claude web_fetch nested-URL
  exfil, EchoLeak, GitLab Duo, AgentForce). Training guardrails insufficient ("99% is a failing grade").
- **Dual-LLM design:** **privileged model** (tools/credentials) NEVER sees raw untrusted text; a
  **quarantined reader** (tool-less, credential-less, treated as adversary-controlled) emits **ONLY typed
  structured data** — sentiment∈[-1,1], event enum, confidence, source-count — **never free text**. So a
  "BUY 10000 now" injected in an article can at most perturb a *score/enum*, never reach the trading model
  as instructions. Patterns: Map-Reduce sub-agents per article; **CaMeL** (control/data-flow separation,
  provable on 77% AgentDojo); deterministic runtime policy engine (allow/block/confirm).
- **PoisonedRAG:** **5 malicious docs → ~90% attack success**; paraphrase/perplexity/dedup insufficient →
  **source allowlist + ≥2-independent-source corroboration + structured-only boundary + the gate**.
- **🔒 THE INVARIANT:** *no path from web/news content to a capital action that skips the deterministic
  non-LLM gate* (purged-CV + **DSR** + **net-EV**). **Data-driven, not text-driven** — a poisoned page can
  only bias one feature value into a model whose influence the validation gate has already bounded; it
  cannot conjure an unvalidated trade. This is idea #2's Wall-1/Wall-2 doubling as the security backstop.

### 7-mldl. ML/DL + arbiter + online-learning core (fresh agent) ✅
- **Model spectrum:** mandatory **linear/logistic baseline** (statsmodels) → **LightGBM/XGBoost** (tabular
  default — Grinsztajn 2022: trees beat NN on medium tabular data) → **DeepLOB** (CNN+LSTM, IEEE-TSP 2019)
  / **TransLOB** (transformer) on raw LOB. **Hard gate: every model must beat linear AND GBT on the same
  features** before it ships (FI-2010 benchmark protocol).
- **Calibration MANDATORY** (Guo 2017: modern NN's systematically overconfident): Platt / isotonic /
  **temperature** scaling via `sklearn CalibratedClassifierCV`; validate with **Brier score + reliability
  diagrams**; calibrate **each bot's** P before it sizes.
- **Meta-labeling arbiter** (López de Prado): primary = direction (tuned high-recall), secondary = P(call
  correct) → **doubles as bet-size**; both-high → **FLAT**, both-low → FLAT; **deterministic** resolution
  (auditable). ⚠️ **mlfinlab CONFIRMED STUBBED** — public repo is a bug-tracker only, real code paywalled,
  docs removed → **reimplement triple-barrier + meta-label + purged/embargoed CV from the AFML book** (short
  pseudocode). Use `fracdiff` etc. for the pieces.
- **Learns-as-it-gets-wrong:** **river** (ADWIN / DDM drift detectors) fed each prediction's realized
  correctness → drift flag triggers retrain / window-reset / champion-challenger; **warm_start GBT** for
  incremental; **meta-model over the trade ledger** (learns which bot/signal works in which regime).
  ⚠️ **self-correction degrades** (Huang ICLR-2024) → learn ONLY from **realized P&L + a hard evaluator**
  (FunSearch pattern: generate → deterministic test → keep winners), NEVER self-grade.
- **Evidence:** **SHAP** per decision = the mechanism-declaration trail. OSS: LightGBM · XGBoost · PyTorch
  (DeepLOB) · river · SHAP · sklearn-calibration · statsmodels.

---
**PRIOR preliminary block (kept):**

- **Arbiter / meta-labeling (from idea #1 + crypto-bot):** primary predicts DIRECTION, secondary
  (meta-label) predicts whether ACTING is profitable + size (López de Prado). **Both-high → FLAT.** NOT a
  chat committee — committees fail 41–86% budget-matched (Berkeley MAST); resolution deterministic.
- **Order-flow evidence (from idea #2):** OFI ~**65% concurrent R² but ~3% predictive** — evidence ≠
  forecast; L1 imbalance spoofable → use depth-weighted, treat as context not oracle.
- **Direction is HARD (from idea #1 + nse-crypto-bot-final):** intraday ≈ near-random; the prior build
  measured a **40.3% anti-signal** on real data → mandatory linear + LightGBM baseline gate.
- **Calibration + learning discipline (from idea #1/#5-brain):** NN's overconfident (Guo 2017) →
  calibrate before sizing; **self-correction WITHOUT ground truth degrades** → learn only from realized
  P&L + hard evaluator (FunSearch pattern); meta-model over the ledger; discounted bandit forgets stale.
- **Stack (from idea #1):** LightGBM primary · DeepLOB (PyTorch) as gated 2nd source · river (online +
  drift) · SHAP (evidence) · scikit-learn calibration · statsmodels · mlfinlab meta-labeling (⚠️ public
  repo may be stubbed — verify).

_Owed by the fresh pass: exact LOB feature list for NSE 5-level depth, volume-profile compute + OSS,
DeepLOB repo/benchmarks, drift-detector choice, per-decision SHAP/mechanism-declaration design._

## 8. Finalized decision (synthesis — ALL research complete 2026-08-02)

**Two autonomous BOTS (BULL, BEAR), each own-architecture + own-data, deciding in BOTH segments (cash
long/short + options CE/PE), resolved by a deterministic arbiter, learning only from realized P&L.**

**Each bot's stack (institutional, Rule P — the LOC is real function, not padding):**
1. **Evidence organs** (its own data pipeline): microstructure (LOB/OFI/microprice/volume-profile — WEAK
   *context* features, ~3% predictive ceiling) · **Kronos** candlestick foundation-model forecast (§2c,
   NSE-finetuned) · **news/event NLP** (FinBERT-tone + event-surprise, §7-nlp) · **online-research** organ
   (crawl4ai → browser-use → local vision-LLM, §2d) — the last two **behind the Dual-LLM quarantine**.
2. **Model:** calibrated **LightGBM** base (must beat linear+GBT baseline) → **DeepLOB** gated later;
   triple-barrier labels + **purged CV reimplemented from AFML** (mlfinlab is stubbed); **calibration
   mandatory** (temperature/isotonic) before sizing.
3. **Arbiter (meta-labeling, deterministic):** BULL P(up) + BEAR P(down) → **LONG / SHORT / FLAT** + size;
   **both-high → FLAT**, both-low → FLAT.
4. **Learns-as-it-gets-wrong:** river (ADWIN/DDM drift) on **realized P&L** + warm-start GBT + meta-model
   over the ledger + champion/challenger — **never self-grades** (self-correction degrades).
5. **Evidence trail:** SHAP per decision + declared mechanism.

**🔒 THE governing invariant:** *no path from web/news/model output to a capital action that skips the
deterministic gate* (purged-CV + **DSR** + **net-EV**, idea #2 Walls-1/2). Data-driven, not text-driven —
this is simultaneously the overfitting control AND the prompt-injection security backstop.

**🔴 Honest bar (surface always):** intraday direction ≈ near-random (prior build: 40.3% anti-signal);
news alpha decays in minutes + is arbitraged in liquid names; OFI ~3% predictive; NN's overconfident.
→ the bots earn trust only by beating baselines + clearing the gate on REAL NSE data (Rule F).

**Concrete OSS to integrate:** Kronos (MIT, safetensors, sandboxed) · LightGBM/XGBoost · PyTorch (DeepLOB)
· river · SHAP · sklearn-calibration · statsmodels · FinBERT-tone/FinGPT · crawl4ai/browser-use/MiniCPM-V ·
GDELT/feedparser/trafilatura/NseIndiaApi · reimplement AFML (triple-barrier/meta-label/purged-CV).

**Status:** researched-complete. This is idea #1's directional core built as two production bots. Finalize
= confirm §6 picks (first model class · segment · cadence · autonomy). Tracked in docs/BACKLOG (B45→ready).
