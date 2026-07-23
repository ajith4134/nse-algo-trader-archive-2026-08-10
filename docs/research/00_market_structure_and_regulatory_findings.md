# 00 — Market Structure & Regulatory Research (pre-Layer-1)

Research that grounded the project scope, `CLAUDE.md` rules, and the Layer 1
(Universe & Instrument Registry) design. Findings, not code — see
`docs/flowcharts/` for how the code that resulted from this actually works.

## Regulatory framework (SEBI, binding constraint on the whole project)

- SEBI circular **"Safer Participation of Retail Investors in Algorithmic
  Trading,"** issued Feb 4, 2025 (SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/132),
  timeline extended Sep 30, 2025, **fully mandatory Apr 1, 2026**.
- Structure: broker = **principal**, this bot = **agent**. All orders route
  through the broker's API — never direct-to-exchange.
- **Algo-ID tagging**: every order must carry an exchange-assigned
  identifier once the execution layer is wired up.
- **White-box vs. black-box**: white-box = transparent, replicable logic,
  personal/family use only, allowed without extra registration as long as
  order rate stays under threshold. Black-box (hidden logic, or logic that
  changes without being re-registered, or distributed to other users)
  requires **SEBI Research Analyst registration**; any logic change forces
  re-registration as a new algo. **This is why any self-modifying/learning
  component in the system must promote changes through a human-reviewed
  gate — an automatically-self-rewriting live strategy risks tipping into
  black-box classification.**
- **10 orders/sec/exchange/client** threshold — below it, no formal
  algo-registration beyond broker empanelment; above it, mandatory
  registration.
- Static whitelisted IP required for API access.
- Confidence: high but not verified against the primary legal PDF
  line-by-line (it didn't render as extractable text) — cross-check the
  actual SEBI circular before treating any specific number as gospel for a
  compliance-critical decision.

## NSE/BSE instrument universe (facts, as of mid-2026)

- **NSE index-options underlyings — the complete list, not a sample:**
  NIFTY 50, NIFTY NEXT 50, FINNIFTY, MIDCPNIFTY, BANKNIFTY. Five, total.
- **SENSEX and BANKEX are BSE products, not NSE** — deferred to a later
  phase, different exchange integration entirely.
- **NSE single-stock options:** ~185-208 stocks, reviewed
  quarterly/semi-annually — list changes, never hardcode it.
- **NSE cash universe:** ~2,084 mainboard-listed companies. Nifty 500
  already represents ~92-96% of free-float market cap and turnover — the
  remaining ~1,500+ names are mostly illiquid tail. "All 2000+ stocks" is a
  liquidity-filtering problem, not just a universe-listing problem.
- Lot sizes change periodically (e.g. Jan 2026 revision: NIFTY 65,
  BANKNIFTY 30, FINNIFTY 60, MIDCPNIFTY 120) — never hardcode; always read
  off the live instrument master.

## Broker API landscape (as of mid-2026)

| Broker | API cost | Per-order brokerage | Rate limit | Notes |
|---|---|---|---|---|
| Zerodha Kite Connect | Personal: free; Connect (data): ₹500/mo | ₹0/₹20/₹20 | not publicly specified | **Chosen broker for phase 1.** Some secondary sources still quote an outdated ₹2,000/mo figure — conflict noted, official support docs say ₹500/mo. |
| Upstox | Free (₹10/order promo until 31 Mar 2026) | ₹0/₹20/₹20 | — | |
| Angel One SmartAPI | Free | ₹20 or % (lower) | ~10 orders/sec | |
| Fyers | Free | ₹0/₹20/₹20 | ~10 orders/sec | Strong historical OHLCV depth |
| Dhan | Free (data ~₹500) | ₹20 or 0.03% (lower) | ~25 orders/sec, WebSocket | Fastest quoted rate limit |

## Full system taxonomy (layers A-L)

Layer roadmap now tracked live in `docs/flowcharts/00_project_overview.md`;
original research taxonomy preserved here for context:

A. Regulatory · B. Universe & Instrument Registry · C. Market Data ·
D. Indicators/Features · E. Strategy/Signal/ML · F. Risk Management ·
G. Execution/OMS · H. Broker Integration · I. Backtesting & Paper Trading ·
J. Session/Square-off · K. Monitoring/Logging · L. Documentation/Process.

Each layer graded ⭐ (user-named) / ✅ (expected) / 🚀 (advanced) /
🌌 (frontier) — full detail was presented in conversation; the load-bearing
subset (base tier) is what got built into the Layer 1-9 roadmap.

## Three tiers (original scope framing)

- **Base:** cash intraday + all 5 NSE index options, one broker
  (Zerodha), rule-based indicators, hard risk limits, EOD square-off,
  manual paper-trade verification, markdown flow-chart notes per feature.
- **Advanced 🚀:** multi-broker abstraction, ML signal ranking, portfolio
  Greeks risk, liquidity-filtered full-universe scanning, automated
  contract-master sync, alerting, walk-forward validation gating.
- **Ultra-advanced 🌌:** RL execution agent, NSE+BSE cross-exchange
  awareness, self-healing session recovery, auto-generated data-lineage
  diagrams, multi-account capital allocation, regime-adaptive strategy
  switching. (Superseded/refined by the adaptive-learning research in
  `01_adaptive_learning_architecture_findings.md` — that file is the
  current source of truth for the learning/memory/self-evolution design.)

## Decisions locked in from this research

- Language: Python.
- Broker (phase 1): Zerodha Kite Connect, kept behind a swappable
  broker-integration boundary.
- Segments in phase 1: NSE cash intraday + NSE options intraday (index +
  single-stock). Futures, commodities, BSE index options: deferred.
- No overnight carry, any segment, ever.
- Starting layer: Universe & Instrument Registry (built — see
  `docs/flowcharts/01_universe_instrument_registry.md`).

## Sources (representative, not exhaustive)

- SEBI circular extension notice: sebi.gov.in/legal/circulars/sep-2025/...
- Broker pricing: support.zerodha.com (official), algotest.in broker
  comparison (secondary, cross-checked).
- NSE/BSE index derivatives: nseindia.com option-chain pages, business-standard.com,
  bigul.co lot-size coverage, niftytrader.in.
- F&O stock counts: dhan.co futures/options stock lists, univest.in,
  ventura securities F&O blog.
- NSE listed-company counts / Nifty 500 coverage: nseindia.com Nifty 500
  index page, Wikipedia NSE/NIFTY 50/NIFTY 500 pages.
