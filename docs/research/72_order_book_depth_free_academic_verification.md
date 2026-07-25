# Research/72 — Historical NSE Order-Book DEPTH: Free/Academic/Public Verification

**Rule I acquisition research (Rule D: saved to file).** Skill used: `deep-research`
(4-angle parallel sweep + source triangulation + credibility grading). Targeted
re-verification of a specific hypothesis: *"no vendor sells historical Indian
order-book depth — the only path is to record it forward."* Companion to
`54_nse_microstructure_data_sourcing.md` (2026-07-24, first pass, reached this same
conclusion), `59_deep_history_price_and_universe_sourcing.md` (pricing detail),
`70_slice4_p4b_live_depth_recorder_design.md` (the record-forward feature this
finding justified building), and the sibling same-day pass
`71_free_academic_nse_tick_data_sourcing.md` (asks the adjacent tick/trade
question — this file is DEPTH-specific and does not repeat 71's tick findings
except where directly load-bearing).

**As-of date: 2026-07-25.** Four independent angles run in parallel: academic/
WRDS/LOBSTER, Kaggle/GitHub/HuggingFace/Zenodo, quant-forum practitioner
consensus, NSE-official + broker free-tier re-check. Sources WebFetched and read
directly unless marked snippet-only.

---

## 0. Bottom line

**The hypothesis is directionally CORRECT but one clause is imprecise.** It is
false that *no one* sells historical NSE order-book depth — NSE's own data-vending
arm does, and two narrow academic channels grant it. It is true that **no free,
individually-accessible route to real historical NSE order-book depth exists
anywhere** — official, academic, or open-data. Every legitimate route that has
real depth history charges five-to-six-figure INR/USD annual fees, gates it to
institutions/FPIs/campus populations, or both. For a personal, non-institutional
project, **"record it forward yourself" remains the only genuinely free path** —
not because the data doesn't exist, but because every channel that has it is
priced or gated out of reach. This does not change `54`'s or `70`'s conclusions;
it closes out the "did we miss a free/academic door" question with a documented,
independently re-triangulated **no**.

---

## 1. Ranked list of every concrete depth source found (paid + free + gated)

| # | Source | Depth granularity | Coverage | Access | Cost | Grade |
|---|---|---|---|---|---|---|
| 1 | **Record your own live broker depth** — Kite (5-level), Dhan (20/200-level), Fyers (50-level), Upstox (30-level) | True live order-book snapshots | Forward-only, from the day you start | Own account, own disk | **Free** | A — only genuinely free + open route; already built as `70` |
| 2 | **NSE Data & Analytics "Historical Order & Trade Data"** (`dotexdata.nseindia.com`) | Continuous per-order events (add/modify/cancel, jiffy timestamps) — near-continuous LOB reconstruction | CM/F&O since ~Dec 2007; delivered via SFTP/AWS S3, 90-day lag (orders), 30-day (trades) | Licence + undertaking form, individual-entity eligibility unconfirmed | ₹12,50,000/yr commercial; **₹6,25,000/yr "Student/Researcher" (50% off)**, CM or F&O each (per `59`, confirmed again this pass) | A (official) — real, but not free, and honest eligibility for the discount is doubtful for a trading (not research) project |
| 3 | **NSE Data & Analytics "Historical Trade Data" (legacy)** | Discrete LOB **snapshots** (order-level, a handful of times/day) + full trades log | CM since 1995, F&O since 2003 | Same portal/licence | ₹1,10,000/yr | A (official) — cheaper, but coarser (snapshots not continuous) and still paid |
| 4 | **NSE's free 6-month tick-by-tick order+trade trial** | True tick order+trade data, up to 6 months | New/prospective clients only | Onboarding incentive | Free — **but restricted to Foreign Portfolio Investors (FPIs)**, not retail/individuals | B (real per NSE's own Data Usage & Sharing Policy; population-gated, unusable here) |
| 5 | **NSE-NYU Stern Initiative on Indian Capital Markets** (`stern.nyu.edu`) — **NEW finding, not in `54`/`59`/`71`** | "Historical tick by tick (TBT) trade and order level data" provided to approved projects "at a subsidized rate" | Full order-level, all-Nifty-50-class coverage demonstrated in funded output (Gupta, Raman & Yadav, ~2006 data, 14 trader-classification codes) | Competitive: ~6 international proposals/year funded, $7,500 grant, requires an institutional PI + genuine (non-trading) research question | Subsidized, not free; 2022 call-for-proposals routes data access back through NSE's standard commercial policy — terms appear to have tightened since the 2012-19 era | A (real, triangulated: program page + funded paper) — legitimate, but institutional/competitive, and (like #2's discount) not honestly usable by a personal trading-bot project |
| 6 | **IIM Ahmedabad Vikram Sarabhai Library** — NSE order-book licence, 2019-2020 | Genuine order-book data + tick-by-tick CM (1999+)/F&O (2000+) | Campus DVD/download delivery | IIMA students/faculty/staff only | Free to campus community; **no external/alumni/paid tier** | A legitimacy / C accessibility — real academic depth data exists, but is closed-campus (detailed in `71` §2.1; cross-referenced, not re-derived here) |
| 7 | **SEBI Dec-2024 "Policy for Sharing Data for Research/Analysis" + NSE Oct-2024 Data Usage Policy** | N/A for depth — **tick-by-tick order/trade data is explicitly the restricted "second basket"**; only aggregate OHLC/volumes are in the free researcher "first basket" | SEBI-accredited institutions only, 2 GB/researcher/year | Data Seeking Request Form | Free (aggregate only) | B — real, current, legitimate program; explicitly does NOT solve the depth question (detailed in `71` §2.1) |
| 8 | **LOBSTER** (`lobsterdata.com`) | Full message-level reconstructed order book | **NASDAQ only** — reconstructed from NASDAQ Historical TotalView-ITCH; no non-US coverage found anywhere in its own docs | Free academic (NASDAQ-issued waiver) | Free, but **zero India/NSE coverage** — confirms the "LOBSTER is US-only" premise | A/B — confirms no depth-equivalent exists, doesn't solve it |
| 9 | **No Indian LOBSTER-equivalent found** | — | — | — | — | Confirmed absence, two independent search passes (this pass + `71`) |
| 10 | **WRDS (Wharton)** | None — WRDS's own TAQ/ISSM tick products are US-only; no Refinitiv/LSEG Tick History module on WRDS itself | — | — | — | B (absence-of-evidence, triangulated across this pass + `71`) — dead end |
| 11 | **LSEG/Refinitiv Tick History** (accessed via a subscribing university's own library, bypassing WRDS, e.g. Yale) | Claims NSE eq+deriv coverage to ~1994-96; whether historical *depth* (vs. quotes/trades) is retained is **unconfirmed** | Institutional library subscription | Enterprise, non-WRDS route | Enterprise $$$, not free | B — real product, access path exists only via an affiliated university, not for an individual |
| 12 | **Kaggle / GitHub / HuggingFace / Zenodo** | **Nothing genuine** — every "NSE tick/depth" listing found on all four platforms is 1-min/5-min/daily OHLC mislabeled, or an unrelated dataset (e.g. HuggingFace's "NIFTY" is an LLM acronym collision) | — | Free download | Free | C — confirms no free open depth dataset exists; two independent exhaustive passes (this pass + `71`) converge on zero |
| 13 | **`lebedov/nseindia_lob`** (GitHub) | Order-level LOB **reconstruction code**, not a dataset — requires you to already own NSE's paid order-level files (#2/#3 above) as input | — | Free, open-source, but Python 2, unmaintained since ~2013/2020 | Free (tool only) | B (legitimate tool, not a data source) |
| 14 | **GDFL / TrueData "market depth" products** | Marketed as depth vendors, but **actual historical retention is ~2-7 days of live capture, not a real historical archive**; a TradingQnA thread shows a retail user's request for 3 years of depth went unanswered, and another commenter explicitly doubts full order-book history is retail-available at all | Live-only in practice | Free trial (time-boxed), paid ongoing | ₹1,439-3,199/mo (live feed, not historical depth) | A/B (legitimate vendors) but functionally do not sell historical depth |
| 15 | **All checked brokers' historical APIs** (Kite, Upstox, Angel One SmartAPI, ICICI Breeze, Dhan, Fyers, Groww, 5paisa) | **Zero historical depth anywhere** — depth exposed only via live websocket ("full"/quote mode); historical endpoints cap at 1-minute candles (ICICI Breeze's 1-second is price/OI, not depth) | — | — | — | A — re-confirmed as of 2026-07-25 across all seven brokers, no change from `54` |

---

## 2. Practitioner/community cross-check (new corroboration)

Zerodha's own **TradingQnA** forum (`tradingqna.com/t/historical-market-depth-data/17573`,
read directly) has Zerodha founder Nithin Kamath himself pointing a 2017 asker
toward "exchange-approved data vendors" (GDFL, TrueData) for historical depth — a
2019 follow-up asking whether the OP ever actually got it, or at what price, went
**unanswered**. A parallel Reddit thread (`r/IndianStockMarket`, "Full market depth
orderbook data vendor??") has a commenter explicitly questioning whether "full
market depth orderbook" is available to retail at all. Combined with GDFL/TrueData's
own documented ~2-7-day retention (row 14 above), the retail-practitioner community's
lived experience matches this pass's official-source finding: **no one has actually
obtained a real historical NSE depth archive through a retail-priced channel.**
Separately, a Zerodha co-founder's own forum comment confirms the SEBI-mandated
"free" TBT feed is colocation-only and cannot be streamed to any client — easily
confused with "free tick/depth data" but not retail-accessible in any form
(`tradingqna.com/t/free-tick-by-tick-data/36336`, cited in `71`).

---

## 3. What refines vs. confirms prior research

- **Confirms unchanged**: `54`'s Tier-2 conclusion ("no vendor sells historical
  NSE depth" as a *practical/retail* statement) and `70`'s justification for
  building the record-forward recorder. `59`'s pricing table for NSE Data &
  Analytics (₹1.1L-31.3L/yr) is independently re-derived here from the same
  primary tariff PDF, which triangulates it.
- **Refines**: the literal claim "no vendor sells it" is technically false — NSE
  itself is the vendor, selling continuous per-order event data (not just
  discrete snapshots) since ~Dec 2007. The correct, precise framing (already
  present in `59`, restated here for this pass's specific question) is: *it is
  sold, officially, but priced/gated such that it is not a realistic acquisition
  for a personal project* — five-to-six-figure INR/yr, honest eligibility for
  the discount tier doubtful, 30-90 day delivery lag.
- **New**: the NSE-NYU Stern Initiative academic grant channel (row 5) was not
  previously documented anywhere in this project's research. It is included for
  completeness/transparency but assessed as **not a viable path** for this
  project — same honest-eligibility problem as the Student/Researcher discount
  (this is a personal trading system, not a university research proposal), plus
  it is competitive (~6 slots/year, global applicant pool) and requires an
  institutional PI this project does not have. **No action recommended.**

---

## 4. Blunt verdict (direct answer to the question asked)

**Is historical NSE order-book depth obtainable free, or at all?**

- **At all, for money**: **Yes.** NSE's own Data & Analytics arm sells continuous
  historical order-level data (from which the book at any point is reconstructible)
  since Dec 2007, plus a coarser discrete-snapshot product back to 1995/2003. Two
  academic channels (IIMA campus licence, NSE-NYU Stern grants) also grant real
  order-book-level access to vetted populations. So "no vendor sells it" is false
  as a literal, unqualified statement.
- **Free, for an individual/personal project**: **No — confirmed, not refuted,
  after two independent full research passes** (this one + the sibling `71`) and
  four parallel search angles in this pass alone (academic/WRDS/LOBSTER,
  Kaggle/GitHub/HuggingFace/Zenodo, quant-forum practitioners, NSE/broker
  official re-check). No Kaggle, GitHub, HuggingFace, or Zenodo dataset is
  genuine. No broker — free tier or paid — exposes historical depth; all are
  live-websocket-only. LOBSTER has zero India coverage and no Indian equivalent
  exists. WRDS has nothing. Every academic-free channel found (SEBI's Dec-2024
  policy, NSE's FPI trial, IIMA's campus licence, the NSE-NYU Stern grants)
  either explicitly excludes tick/order data from its free tier or gates it to a
  population (accredited institution, FPI, campus member, competitive grantee)
  a personal retail project does not belong to.
- **Practical conclusion for this project, unchanged from `54`/`70`**:
  **record it forward yourself** (already built, `70`) is the only free,
  self-service path to a depth history. If deeper/older fidelity is ever
  required, the only legitimate paid escalation is licensing NSE's own
  "Historical Order & Trade Data" product (`59`'s pricing) — there is no cheaper
  or free legitimate substitute anywhere.

---

## 5. What this pass did NOT cover
- Direct outreach to NSE (`marketdata@nse.co.in`) or the NSE-NYU Stern program to
  ask whether a personal/non-institutional applicant could ever qualify — not
  attempted (assessed as very unlikely to succeed given the honest-eligibility
  problem already flagged for the Student/Researcher discount in `59`/BACKLOG).
  Same open item as `59`'s G4/G5 — not duplicated here as a new backlog entry.
  IIM Ahmedabad "how attainable is guest/affiliate access" — not evaluated,
  covered as out-of-scope in `71` §4 already.
- Full primary-source read of Refinitiv/LSEG Tick History's exact NSE depth-field
  schema (whether it retains depth or only trades/quotes) — access itself is
  enterprise/university-gated regardless, so not pursued further.
- Whether the lebedov/nseindia_lob reconstruction code could be revived/ported to
  Python 3 to process NSE's paid order-level files, if that product is ever
  licensed — a build-time question, not a sourcing one; deferred to whenever `59`'s
  G4/G5 licensing decision is actually made.

*Stopping condition: 4 parallel angles (academic/WRDS/LOBSTER, Kaggle/GitHub/
HuggingFace/Zenodo, quant-forum practitioners, NSE/broker official re-check),
each independently triangulated against this project's existing `54`/`59`/`71`
research and against each other — a full pass surfaced one genuinely new lead
(NSE-NYU Stern) and otherwise converged on confirmations only, no new free
route.*
