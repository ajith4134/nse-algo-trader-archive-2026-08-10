# Paid Commercial Vendors for Indian Corporate-Actions Master Data

Part of a 7-part vendor/sourcing research report for a personal NSE algo-trading project.
Scope: paid vendors selling/exposing a clean historical corporate-actions master (splits, bonus,
dividends, rights, mergers) for NSE/BSE-listed equities, ideally ~20 years of history.

Research date: 2026-07-24. Method: primary-source WebFetch of vendor sites/docs where reachable;
DuckDuckGo HTML/Lite used for discovery after the session's WebSearch quota was exhausted; Bing
returned unrelated/garbage results for these queries and was abandoned. All claims below are cited
inline; every vendor's own pricing/product page was attempted first, with secondary sources used
only where the vendor's own site did not disclose the data (blocked, 404, or contact-only).

---

## 1. Ace Equity / Ace Equity Nxt (Accord Fintech)

**Products found:** Two distinct Accord Fintech offerings surfaced:
- **ACE Equity Nxt** (www.aceequitynxt.com) — the research-terminal / financial-database product
  (successor to the older "Ace Equity"/Ace Analyser branding at aceanalyser.com, which redirects to
  a bare login page with no public content).
- **ACE Datafeed** (www.accordfintech.com/market-data-feed) — the raw data-feed/API product, separate
  from the terminal product.

**Coverage:**
- ACE Equity Nxt: company profile, board members, balance sheet, P&L, cash flow, segment finance,
  ratios, stock prices, quarterly results, capital structure and shareholding information, 14
  industry-specific formats, Excel plug-in. The product page and features page do **not** name a
  dedicated corporate-actions module (splits/bonus/dividends/rights/mergers) explicitly — only
  "capital structure and shareholding" is called out. [A — aceequitynxt.com/features, fetched
  directly]
- ACE Datafeed: explicitly lists "Corporate Action – BSE EOD" as a feed category, alongside
  intraday/EOD equity, derivatives, commodities, 5-yr financials + 8-quarter results, MF NAVs, IPO
  data. Event-type breakdown (which of splits/bonus/dividend/rights/merger) is not itemized on the
  page. [A — accordfintech.com/market-data-feed, fetched directly]

**History depth:** Not stated for corporate actions specifically. Company financials advertised as
5 years + 8 quarters (ACE Datafeed); Ace Equity Nxt does not state a depth number anywhere on its
public pages.

**Format:** ACE Equity Nxt = web-based terminal + Excel plug-in (not an API for external systems).
ACE Datafeed = "financial information feed through FTP and API," real-time and EOD. [A]

**Pricing:**
- **ACE Equity Nxt: Rs. 125,000 (~USD 3,500) "onwards" per year, taxes extra** — this is the one
  concrete self-serve-visible price found across all 9 vendors. [A — aceequitynxt.com/subscribe-now,
  fetched directly]
- ACE Datafeed: no pricing published; page routes to "Request a Callback," phone (+91-22-67834000),
  and email (info@accordfintech.com). [A]
- A CFA Society India "member offer" PDF for Accord Fintech products exists
  (cfasocietyindia.org/wp-content/uploads/2021/06/Accord-offer-document.pdf) suggesting discounted
  institutional/professional-body pricing exists, but the PDF's text layer was not extractable via
  WebFetch, so exact discount figures could not be verified. [C — found but unreadable, flagged not
  used as evidence]

**Procurement path:** ACE Equity Nxt has a self-serve "Subscribe Now" page with the price shown
up front — closest thing to self-serve in this whole vendor set, though at ~$3,500/yr it is still a
professional-grade purchase, not an impulse buy. ACE Datafeed is sales-contact-only.

**Credibility grade:** A (vendor's own product/pricing pages, opened directly).

**Verdict for personal use:** Realistically **out of reach for casual individual use** at $3,500/yr
minimum, and even so the corporate-actions granularity (event-type breakdown, machine-readable
export) is not demonstrated on the public site — would need a sales conversation to confirm whether
it produces a clean per-event corporate-actions table suitable for backtesting adjustments.

---

## 2. Capitaline (Capital Market Publishers / Capitaline databases)

**Products found:** Capitaline Plus, Capitaline databases (capitaline.com), plus a spun-off
Capitaline Transfer Pricing Online product (transferpricer.com) — not relevant to corporate actions.

**Coverage:** The main site states coverage of "45,000/35,000+ Indian listed and unlisted companies"
across 300+ industries, with company profiles, director info, and financials (P&L, balance sheet,
cash flow, consolidated, segment, forex, R&D) spanning "more than 10-year financials." **No page
reachable explicitly itemized corporate-actions coverage (splits/bonus/dividends/rights/mergers)** —
this was searched for specifically (root site, /products.aspx guess [404], /cfa/index.aspx, and a
Datarade profile) and never surfaced. [A for the pages that did load — capitaline.com root and
capitaline.com/cfa/index.aspx, fetched directly; absence of corporate-actions detail is a genuine
gap in vendor's public disclosure, not a search failure, since Capitaline's product line is broad
enough that CA data plausibly exists inside "Capitaline Plus"/"Capitaline Database" but isn't
documented publicly]

**History depth:** "More than 10-year financials" stated for financials; no CA-specific depth
figure found anywhere.

**Format:** Web-based/cloud database ("no software installation" required per the site). No
mention of API access on any page reached.

**Pricing:** **No pricing published anywhere.** Confirmed absent on: capitaline.com root,
capitaline.com/cfa/index.aspx, and the Datarade third-party profile, which states outright:
"Capitaline has not published pricing information for their data services" and that the profile is
unclaimed/auto-generated by Datarade rather than vendor-maintained. [A — capitaline.com, fetched
directly; B — datarade.ai/data-providers/capitaline/profile, third-party but explicit about the
absence]. Two academic-library PDFs referencing a "Capitaline Plus (Offline)" product and an RVIM
college subscription document were found (library.iima.ac.in, rvim.edu.in) but their PDF text
layers were not extractable via WebFetch, so no pricing could be confirmed from them.

**Procurement path:** "New User Register" self-serve account creation is available, but this
appears to be account setup, not purchase — actual commercial terms require Contact Us / Reach Us.
Sales-mediated.

**Credibility grade:** A for what was found (vendor's own site); the corporate-actions-specific
claim is a **confirmed gap**, not a guess.

**Verdict:** Cannot be assessed as fit-for-purpose for a corporate-actions master without a sales
call — the vendor's public materials never confirm CA coverage exists as a distinct, exportable
dataset. Pricing entirely opaque. Likely institutional-tier (academic libraries and market
publishers are its visible customer base), not a self-serve individual product.

---

## 3. CMOTS / Accord Fintech (data-feed side)

Note: CMOTS (cmots.com) and Accord Fintech's ACE Datafeed are related/overlapping — CMOTS Internet
Technologies Pvt. Ltd. appears to be Accord Fintech's data-feed distribution arm; both were
investigated as the prompt requested.

**Coverage:** CMOTS's own site (cmots.com) rendered essentially no crawlable content via WebFetch
(page loaded as a bare "CMOTS" string with no body content — likely a JS-rendered SPA). A
third-party API aggregator/reseller, FintegrationFS (fintegrationfs.com/fintechapis/cmots-market-data-feed),
describes the "CMOTS Market Data API" as covering "stock quotes, indices, forex rates, commodity
prices, market news, and historical data," with REST endpoints and SDKs — but **explicitly does not
mention corporate actions (splits/bonus/dividends/rights/mergers) anywhere in its description**. [B
— fintegrationfs.com, third-party reseller/consultant, not CMOTS itself; explicitly disclaims being
the data provider: "credentials and approvals managed by the respective providers"]

**History depth:** Not stated.

**Format:** REST API / SDKs per the reseller page; unverified against CMOTS's own documentation
since cmots.com did not yield readable content.

**Pricing:** Not published anywhere found; FintegrationFS page routes to "request a demo."

**Procurement path:** Sales/demo-request only; not self-serve.

**Credibility grade:** B (best available was a third-party API reseller describing the product;
CMOTS's own site was not readable via automated fetch — this is a genuine access limitation, flagged
rather than papered over).

**Verdict:** Cannot confirm corporate-actions coverage exists in the CMOTS API product at all based
on available evidence. Would need direct vendor contact (or authenticated portal access) to verify.
Not shown to be individual/affordable — positioned at "stock broking firms, banks, portfolio
managers, mutual funds" per Accord Fintech's own customer description.

---

## 4. Bloomberg (Bloomberg Terminal / Bloomberg Data License)

**Coverage:** Bloomberg's own product pages (bloomberg.com/professional/...) returned HTTP 403
Forbidden on every path attempted (product overview, how-to-buy, pricing-support pages) — the site
actively blocks automated fetching. Corporate-actions coverage was not verifiable from Bloomberg's
own site as a result. It is well-established industry knowledge (and consistent with the Terminal's
"all asset classes, all markets" positioning) that Bloomberg carries comprehensive global
corporate-actions data including India/NSE/BSE, but this specific claim could not be confirmed from
a primary Bloomberg source in this session — flagged as unverified-from-primary rather than assumed.

**Pricing:** Bloomberg does not publish list pricing. Secondary/aggregator sources converge on a
consistent figure:
- **costbench.com: $31,980/year for a single terminal seat, $28,320/year/seat for multi-terminal (2+),
  $18,000–$22,000/year for negotiated enterprise deals** — sourced by costbench from "15 verified
  sources" and a "median contract of $31,980 from Vendr buyer database (n=15 purchases)," last
  verified May 2026. [B — costbench.com, secondary aggregator citing real transaction data, not
  Bloomberg's own site]
- A LinkedIn post independently cites **~₹20 lakh (~$24,000) per year for one terminal in India**,
  roughly consistent with the costbench figures once currency/regional variance is allowed for. [C —
  LinkedIn post, unverified individual claim, directionally consistent with B-grade source]
- Multiple other secondary sources (Investopedia, The Pricer, StocksToTrade) corroborate the
  $24,000–$32,000/year/seat range without contradicting it.

**Procurement path:** Enterprise sales only; no self-serve signup exists. Confirmed by the 403 block
on all self-service/pricing pages and universal secondary-source agreement that Bloomberg requires a
sales relationship.

**Credibility grade:** B (triangulated across 3+ independent secondary sources for pricing; primary
Bloomberg site inaccessible to verify coverage specifics).

**Verdict: Confirmed enterprise-only, ~$24,000–$32,000/year per seat.** Entirely outside the reach
of an individual personal trader. Not a realistic option for this project.

---

## 5. Refinitiv / LSEG Data & Analytics (formerly Thomson Reuters Eikon, now LSEG Workspace)

**Coverage:** LSEG's own corporate-actions product page (lseg.com/en/data-analytics/financial-data/corporate-actions-data)
was reachable and describes "DataScope for corporate actions," covering "ISO, non-ISO events and
extensive historical corporate actions data," delivered via "SWIFT ISO 15022 and Proprietary
formats" across "a variety of packages and delivery platforms," aimed at "pre-trade or post-trade
activities." [A — lseg.com, fetched directly] The page does not enumerate India specifically nor
itemize splits/bonus/dividends/rights/mergers individually, though "extensive historical corporate
actions data" implies broad multi-market coverage consistent with LSEG's global institutional
positioning. Eikon has been retired/is being transitioned to "LSEG Workspace"
(lseg.com/en/data-analytics/products/workspace), confirmed on LSEG's own site. [A]

**History depth:** "Extensive historical" — no specific year figure published.

**Pricing:** **No pricing published anywhere on LSEG's own site.** The Workspace product page
confirms a sales-driven procurement model: "Request product details" forms, "Speak to a specialist,"
multiple regional sales phone numbers including an India number (+91 22 6180 7525), and a "Try or
buy online" link whose actual checkout flow was not explorable via WebFetch. [A — lseg.com, fetched
directly, pricing absence confirmed rather than assumed]

**Procurement path:** Enterprise sales contact; India-specific sales line exists, confirming an
active India commercial presence, but no self-serve tier found.

**Credibility grade:** A (LSEG's own product pages, opened and read directly, for both coverage
description and confirmed absence of public pricing).

**Verdict: Confirmed enterprise-only.** Industry-standard knowledge (and general market pricing for
Eikon/Workspace historically in the $12,000–$22,000+/year/seat range per multiple secondary industry
comparisons such as the WallStreetPrep Bloomberg-vs-Eikon-vs-CapIQ comparison found in search
results) places it in the same tier as Bloomberg — **not realistic for an individual personal
trader.**

---

## 6. Trendlyne

**Access note:** trendlyne.com blocked WebFetch entirely — every path attempted (root, `/data/`,
`/plans/`, `/subscription/plans/`, `/features/trendlyne-data-api/`) returned **HTTP 405 Method Not
Allowed**, consistent with active bot-protection on the whole domain rather than a missing page.
Findings below are therefore from secondary sources (DuckDuckGo-discovered) rather than primary
Trendlyne pages, and are graded accordingly.

**Coverage:** A third-party review site (findmymoat.com/tools/trendlyne) states Trendlyne tracks
"corporate actions and event calendars for India and U.S. markets, including **dividends, splits,
M&A, board meetings, and alerts**." Rights issues are not explicitly named but plausibly covered
under a broader corporate-actions umbrella given the other categories listed. [B — findmymoat.com,
third-party review, not opened from Trendlyne itself]

**Pricing (per the same review):**
| Tier | Price |
|---|---|
| Free | — (basic tier) |
| GuruQ (annual) | ₹2,190/year |
| StratQ (annual) | ₹5,900/year |
| Pro (Global, annual) | ₹8,900/year |
| Pro Plus (Global, annual) | ₹11,900/year |

The review notes "India-only, global, SmartOptions, Excel Connect, alert frequency, backtest limits,
and download limits vary materially by tier," and that "Excel Connect and Google Sheets add-ins" are
available on eligible plans for spreadsheet-based programmatic pull, though **no direct developer/REST
API was confirmed**. [B]

**API access:** A reverse-engineered, unofficial Trendlyne API wrapper exists on GitHub
(github.com/katmakhan/TradeX — `Modules/Trendlyne/trendlyne_apis.py`), but the only endpoint found
in that file was an options-chain "most active contract" endpoint — **no corporate-actions endpoint
was present in the code inspected**. [C — unofficial reverse-engineered wrapper, single file
inspected, not comprehensive]

**Format:** Web platform + Excel/Google Sheets add-ins on paid tiers; no confirmed official REST API
for corporate actions specifically.

**Procurement path:** Self-serve online signup with published INR pricing (per the secondary
source) — this is the **most affordable, most self-serve-friendly option investigated for corporate
actions among all 9 vendors**, if the review's figures are accurate.

**Credibility grade:** B overall (secondary source, but a detailed, specific, internally consistent
pricing table rather than a vague claim) — **flagged for direct verification against trendlyne.com
by the user**, since the primary site could not be opened in this session.

**Verdict:** **Most promising affordable lead of the 9 vendors** — sub-₹12,000/year for a "Pro Plus"
tier with corporate-actions/dividend/split/M&A coverage, IF the review's figures hold up and the
Excel Connect export is granular enough to build a clean corporate-actions master. This needs manual
verification (e.g., a real browser, not automated fetch, since the site blocks bot traffic) before
being relied upon — treat as a strong lead, not a confirmed fact, given the primary-source access
gap.

---

## 7. Screener.in

**Coverage:** Screener.in is confirmed (via its own changelog/docs page, screener.in/docs/, fetched
directly) to have a **"Corporate Actions" tab** in its UI: "The Corporate Actions tab now includes
details of preferential issues undertaken by companies" — confirming at least preferential-issue
tracking exists, implying the tab likely also covers the more common events (dividends, splits,
bonus) though this specific enumeration wasn't itemized on the changelog. [A — screener.in/docs/,
fetched directly]

**Pricing (confirmed from screener.in/premium/, fetched directly):**
- **Hobby Investor (Free): ₹0/year**
- **Active Investor (Premium): ₹4,999/year, inclusive of GST**
The premium tier's only relevant extra found is a "Download Results" (CSV export) feature not in
the free tier. [A]

**API access:** **No official API exists.** Confirmed absent from screener.in/docs/ (changelog
mentions only UI/CSV features, no REST/webhook docs) and from the premium pricing page. Multiple
**unofficial/community-built wrappers** exist on GitHub (Kraken-coder/screener-api-unofficial,
sahiljani/screener-unofficial-api) and on marketplaces (Apify's "Screener.in API," parse.bot). One
of these (sahiljani/screener-unofficial-api) was opened directly: it exposes financials, ratios,
shareholding, and comparison data, but **explicitly does not expose corporate actions data** — its
documented endpoints cover analysis/profit-loss/balance-sheet/cash-flow/ratios/shareholding tabs
only, not the Corporate Actions tab. [A for the GitHub repo itself, fetched directly; C for
reliability as a data source since it's an unofficial scraper wrapper, "not affiliated with,
endorsed by, or supported by Screener.in," subject to breaking on any UI change and arguably against
site terms of service for programmatic/commercial use]

**History depth:** Not stated for corporate actions; general financials advertised as "10 years."

**Format:** Web-only officially (CSV export on Premium). Unofficial scraping-based API wrappers
exist for financials but not confirmed for corporate actions specifically.

**Procurement path:** Fully self-serve, instant online signup, cheapest paid tier of all 9 vendors
(₹4,999/year ≈ $60/year).

**Credibility grade:** A for pricing and official feature description (screener.in's own pages,
fetched directly); C for any API-based access path (unofficial, ToS-risk, and doesn't cover
corporate actions in the one wrapper actually inspected).

**Verdict:** Cheapest, most accessible self-serve option, but **not fit-for-purpose as a
corporate-actions API source** — it has a corporate-actions view in its web UI but no official
export/API for it, and the unofficial API options found don't expose that tab. Would require manual
CSV download or fragile scraping of an unofficial-API-unsupported page, which conflicts with the
project's Rule F (real-data verification) reliability needs for something as adjustment-critical as
corporate actions.

---

## 8. Tickertape

**Coverage:** Tickertape's homepage (fetched directly) surfaces corporate-action items through a
"Corp Action" filter in its news feed, with an example entry: "ARE&M Cash Dividend - Ex Date Jul 27,
2026 - Final • Dividend/Share: ₹5.20" — confirming dividend tracking exists in the product, but the
homepage content does not clarify whether splits, bonus issues, rights offerings, or mergers are
included under the same "Corp Action" umbrella. [A — tickertape.in, fetched directly]

**Pricing (tickertape.in/pricing, fetched directly):**
- 1 month: ₹399/month
- 3 months: ₹899 total (~₹300/month)
- 12 months: ₹2,999/year (~₹250/month), marked "Best Value," with a stated 20% discount vs. monthly

**API access:** **None found.** The pricing page contains no mention of API access or corporate
actions data at all — its listed features are portfolio tracking, screening, forecasts, alerts, and
data export (unspecified scope). [A — tickertape.in/pricing, fetched directly, confirming absence]

**Format:** Web/app only; no developer documentation found anywhere on the site.

**Procurement path:** Fully self-serve, cheapest recurring tier among the retail-terminal-style
products (₹2,999/year ≈ $35/year).

**Credibility grade:** A (vendor's own site, fetched directly, for both the dividend-tracking
feature and the confirmed absence of API/corporate-actions detail on the pricing page).

**Verdict:** Affordable and self-serve, but **no API and no confirmed comprehensive corporate-actions
export** — only dividend data was concretely observed; splits/bonus/rights/mergers coverage is
unconfirmed. Not usable as a programmatic corporate-actions-master data source without manual
extraction, which does not meet the project's need for a clean, automatable historical master.

---

## 9. Simply Wall St

**Coverage:** Simply Wall St (simplywall.st, fetched directly) confirms **India/NIFTY coverage**
exists ("Popular Markets" lists "India: NIFTY"), sourced from **"Institutional Quality Data from S&P
Global Market Intelligence"** across "120,000 global stocks" in 90 markets with "over 10 years of
historical data." [A — simplywall.st, fetched directly] However, **no API offering and no explicit
corporate-actions product/feature (splits, bonus, dividends, rights, mergers) is mentioned anywhere**
on the homepage or the dedicated pricing page (simplywall.st/plans, fetched directly), which lists
only Free / Premium / Unlimited tiers differentiated by portfolio count and report volume, with **no
prices displayed on the page itself** (pricing appears to require account/region selection to
reveal). [A]

**Pricing:** Not disclosed on the public plans page in this session — tiers exist (Free, Premium,
Unlimited) but no ₹/$ figures were shown.

**API access:** None found; no developer documentation surfaced anywhere on the site.

**Procurement path:** Self-serve signup implied ("No credit card required" for free tier), but exact
commercial terms require deeper account-flow navigation not accessible via a single fetch.

**Credibility grade:** A (vendor's own site, fetched directly) for coverage and absence-of-API/CA
findings; pricing figures themselves remain unconfirmed (not a guess — genuinely not shown on the
page).

**Verdict:** Confirmed India equity coverage via S&P Global Market Intelligence sourcing, but
**no corporate-actions-specific product or API was found** — this is a retail investment-research
tool (like Tickertape/Trendlyne), not a corporate-actions data vendor. Not fit-for-purpose for this
project's need.

---

## Cross-vendor summary table

| Vendor | CA coverage confirmed? | History depth stated? | Format | Price found | Procurement | Grade |
|---|---|---|---|---|---|---|
| Ace Equity Nxt | Partial (feed side yes, terminal side no explicit CA module) | No | Web terminal / FTP+API (feed) | **₹125,000 (~$3,500)/yr onwards** | Self-serve price shown, sales for feed | A |
| Capitaline | Not confirmed — genuine gap | No | Web DB, no API found | **None published** | Register + Contact Us | A (gap confirmed) |
| CMOTS / Accord (feed) | Not confirmed (reseller desc. omits CA) | No | REST API (via reseller) | None published | Demo request | B |
| Bloomberg | Assumed (industry-standard) but unverified from primary due to 403 block | No | Terminal / Data License | **~$24,000–$32,000/yr/seat** (triangulated, 3+ secondary sources) | Enterprise sales only | B |
| Refinitiv/LSEG | Yes, generically ("extensive historical CA data") | No | SWIFT ISO 15022 / proprietary feeds | **None published** | Enterprise sales only, India line exists | A |
| Trendlyne | Yes (dividends, splits, M&A, board meetings) per secondary source | No | Web + Excel/Sheets add-in; no confirmed official API | **₹2,190–₹11,900/yr** (secondary source, unverified from primary — site blocked fetch) | Self-serve (per secondary source) | B |
| Screener.in | Yes (UI tab, preferential issues confirmed) but no API for it | "10 years" (general financials) | Web + CSV export; no official API; unofficial wrappers don't cover CA | **₹0 / ₹4,999/yr** | Fully self-serve | A (pricing/coverage) / C (API path) |
| Tickertape | Partial (dividends only confirmed) | No | Web/app, no API | **₹2,999–₹4,788/yr** | Fully self-serve | A |
| Simply Wall St | Not confirmed — no CA product found | "10+ years" (general) | Web/app, no API | Not disclosed on public page | Self-serve implied | A |

---

## Bottom line / recommendation ordering for an individual personal trader

1. **Realistically enterprise-only, rule out:** Bloomberg (~$24k–$32k/yr/seat) and Refinitiv/LSEG
   (no public price but same institutional tier, confirmed sales-only procurement) — both confirmed
   via primary or triangulated secondary sources to be well outside individual-trader budgets.
2. **Ambiguous middle tier, needs a sales call to know true cost/fit:** Ace Equity Nxt (~$3,500/yr
   confirmed, but CA-module granularity unconfirmed), Capitaline (pricing entirely opaque, CA
   coverage unconfirmed), CMOTS/Accord data-feed (pricing opaque, CA coverage unconfirmed from the
   one reachable description).
3. **Affordable retail tools that touch corporate actions but lack an API for it:** Screener.in
   (₹4,999/yr, has a CA tab, no official API), Tickertape (₹2,999/yr, dividends only, no API),
   Simply Wall St (India coverage confirmed, no CA product/API found).
4. **Most promising affordable lead, but unverified from primary source:** **Trendlyne** —
   secondary-source pricing (₹2,190–₹11,900/yr) with an explicitly stated corporate-actions/dividend/
   split/M&A feature set and Excel/Sheets export on paid tiers. **This is the vendor most worth a
   manual (human-browser) follow-up visit** to trendlyne.com/subscription/plans/, since the site's
   bot-protection blocked all automated verification in this session — the secondary evidence is
   good (a specific, internally consistent, multi-tier price table) but has not been triangulated
   against the vendor's own site.

**None of the 9 vendors was confirmed, from a primary source, to sell a clean, API-accessible,
20-year, per-event-typed (split vs. bonus vs. dividend vs. rights vs. merger) corporate-actions
master at an individual-affordable price.** The closest fits are Trendlyne (needs primary
verification) and Ace Equity Nxt (~$3,500/yr, needs a sales call to confirm CA granularity) —
everything else either lacks a confirmed CA product, lacks an API, or is enterprise-only.

---

## What was NOT covered / explicit gaps

- Bloomberg's and LSEG's own India-specific corporate-actions documentation could not be opened
  (403 block on Bloomberg; LSEG's page didn't itemize India specifically) — flagged, not guessed.
- Trendlyne's entire domain blocked automated fetching (405 on every path) — all Trendlyne findings
  rest on one secondary review site and one GitHub code inspection, not the vendor's own pages.
  **Recommend manual verification.**
- CMOTS's own site (cmots.com) did not render usable content via WebFetch (likely a JS SPA) —
  findings rest on a third-party reseller description only.
- Two PDF documents (a Capitaline academic-library brochure and a CFA Society India Accord Fintech
  member-offer document) were located but their text layers could not be extracted via WebFetch —
  they may contain pricing detail not captured here.
- No vendor's public materials were found that explicitly state "20 years of corporate-actions
  history" — the request's ~20-year depth target was not confirmed as met by any of the 9 vendors
  from public-facing pages; this would need direct sales-team confirmation for any vendor under
  serious consideration.
- Per the deep-research protocol's adjacency step: one additional category of vendor surfaced
  incidentally during Datarade searches — global corporate-actions specialists like **Exchange Data
  International (EDI)** and **Cbonds** appear in Datarade's provider list for the "Corporate Actions
  Data" category, but were not in the requested vendor list and were not investigated in depth here;
  flagging as a possible lead for a follow-up pass if the 9 named vendors prove insufficient.
