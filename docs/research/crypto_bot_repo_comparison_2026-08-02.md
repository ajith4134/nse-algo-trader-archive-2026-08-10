# crypto-bot repo — what it is, and how it compares to nse-algo-trader

**Read:** 2026-08-02 · **Source:** https://github.com/ajith4134/crypto-bot.git (private, user's own)
**Sibling repos:** nse-crypto-bot-final (the "prior attempt"), nse-botonly (= this project, nse-algo-trader).

## 1. What crypto-bot actually is

Despite being called a "completed bot," its own README states: **"Layer 0 is a working library,
not a running system."** It is a **design + research archive**, not a finished bot:

- **114 MB, 1,142 files — mostly source material** (817 Instagram frames, 9 reels, 7 YouTube
  video note sets, 135 markdown design docs). Only **~12 Python modules of actual code**.
- **Only Layer 0 (raw market-data capture) is built** — on branch `layer0-raw-capture`
  (`src/capture/*`: binance.py, hyperliquid.py, raw_writer, sequencing, capture_ledger,
  universe_tracker, frame_codec…), ~14 test files. "45 commits, 256 tests, capture proven
  byte-exact against live Binance." Supervisor + HTTP poller unbuilt; a double-writer lock was
  in flight at snapshot time.
- **Domain: global CRYPTO**, not NSE. Execution venues Binance + Hyperliquid; reference-only
  Kraken/OKX/Coinbase. Instruments: spot + perps + dated futures + options (Deribit). Capital
  path: **under $10k for first 6 months** ("paid validation, not income") → $100k–$1M.

## 2. Its architecture (6 layers, strict build order)

| Layer | Purpose | Key components |
|---|---|---|
| **0 Truth** | no look-ahead leakage, structurally | **Bitemporal store** (event/ingestion/availability_time), **clock-gated access API** (one path for backtest+live), snapshot-on-ingest, provenance stamper, frozen universe snapshots |
| **1 Reality filter** | fees dominate edge 5–10× | **Cost engine gating every signal before acceptance**, capacity model |
| **2 Search integrity** | "this is what killed the prior attempt" | **Trial registry (honest cumulative N)**, holdout custodian (refuses queries), mechanism declaration, validation harness (Deflated Sharpe as in-loop fitness, CPCV, MinBTL, BH-FDR) |
| **3 Live ops** | where real losses occur | Venue health auto-halt, rate-limit budgeter, order-intent WAL, watchdog+firewall kill, staleness detector |
| **4 Portfolio** | | Discounted Thompson allocator, vol-target sizer + fractional-Kelly ceiling, correlation breaker, drawdown ladder |
| **5 Signal integrity** | | Depth-weighted OFI (never L1 imbalance), funding/basis engine, HAR-RV; **not** a 200-indicator zoo |

**Stack (settled, live-verified):** Python 3.12/uv · **NautilusTrader** (one code path
backtest↔live; adapters for both venues) · Parquet+ZSTD/**DuckDB**/Polars · **LightGBM**+Optuna ·
MLflow (aliases) · sops+age secrets · systemd --user · pytest+Hypothesis.

**Strategy thesis:** organize by **family, not frequency**. Carry (funding/basis) first —
latency-immune, viable at cloud scale. Market-making / latency-arb / triangular-arb declared
**structurally closed** at this size+latency. Options are the long-term third leg (variance risk
premium) but sequenced last (needs Greeks gate + IV surface).

**The prior attempt (nse-crypto-bot-final) "failed"** because it developed on **Mackey-Glass
chaotic data** (52%→96.4% accuracy) — deterministic, stationary, non-adversarial, proving the
plumbing works and nothing about markets. Lesson = never develop on a tractable proxy. (This is
exactly our **Rule F: real-data verification**.)

## 3. Same author, same DNA — mapped to our modules

The *cognitive/AI vision is identical* across both projects:

| crypto-bot concept | our nse-algo-trader equivalent |
|---|---|
| Three brains + BULL/BEAR/ARBITER | strategy_engine + directional agents |
| Experiment ledger (immutable, incl. failures) | memory_reflection / experience memory |
| Promotion pipeline + manual go-live button | paper→gated-live path |
| Risk gate nothing bypasses (SEC 15c3-5) | risk_management/pre_trade_risk_gate |
| Dual-LLM quarantine (lethal trifecta) | llm_strategy + news_sentiment |
| Meta-model over the ledger ("learns about itself") | predictive_core / epistemics |
| Episodic/semantic/reflective memory | memory_reflection |
| Self-improving autonomous organism | autopoiesis, will, conscience, sentience, axiology, society, intrinsic_motivation |

The two CLAUDE.md rule sets are **siblings**: crypto-bot Rules 0–7 (verification, model-routing,
youtube, install-freely, live enforcement hooks, research-tool, front-load spec/interview,
self-describing names) overlap heavily with our Rules A–Q. Notable exact matches:
- their **Rule 7 (names state what the thing does)** = our **Rule C**
- their **Rule 3 (never skip an option because it needs installing)** = our **install-freely**
- their **Rule 0 (verification / real output)** = our **Rule F**
- their **Rule 5 (research to files first)** = our **persist-research-to-files**
- their **Rule 1 (sonnet for research agents)** = our **research-agents-use-sonnet**

## 4. Maturity gap (the honest headline)

**Our nse-algo-trader is FAR more built out.** Ours = **289 Python files across 27 modules**
(dashboard, live paper loop, real Zerodha Kite integration, 16-trunk/~197-branch atlas, VPIN,
Black-Scholes IV, replay backtester…). crypto-bot = design docs + **one** data-capture layer.
crypto-bot is "what to build and why, rigorously reasoned"; ours is "a large amount already
built." They are two attempts at the *same* institutional-grade autonomous-trading vision in two
different asset classes.

## 5. What we could usefully steal from crypto-bot

Transferable regardless of asset class (these are validation/data-integrity gaps worth auditing
in our NSE project):

1. **Bitemporal store + single clock-gated data path** shared by backtest and live — prevents
   look-ahead leakage *structurally*, not by discipline. Directly applicable to NSE replay/live.
2. **Search-integrity layer** — Deflated Sharpe as the in-loop fitness (not a post-hoc report),
   an honest cumulative **trial registry** (counts discarded/abandoned runs), holdout custodian,
   MinBTL/PBO/CPCV. This is the antidote to overfitting across our large strategy search.
3. **Cost engine gating signals before acceptance** — for NSE the analog is STT + brokerage +
   GST + stamp duty + exchange txn charges + slippage; gate every signal on round-trip breakeven.
4. **Mechanism declaration + regime-coverage gate** (seen a real drawdown & vol spike) instead of
   elapsed-days promotion.
5. **Options = a second risk vocabulary** (Greeks under the gate, not notional) — relevant to our
   NSE options ladders.
6. The **20-most-forgotten list** (cross-strategy netting, signal expiry, liquidation-distance,
   P&L attribution by cost component, feature-staleness stamps…) as an audit checklist.

Crypto-specific pieces (funding carry, Hyperliquid oracle model, venue-health, sops+age,
NautilusTrader) are less transferable to a single-broker NSE system.
