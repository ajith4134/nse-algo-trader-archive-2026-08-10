# Research/76 — Free point-in-time NSE index-membership / survivorship-free universe

**Deep-research pass (2026-07-25), legitimacy-filtered.** One of five parallel
sweeps on "free ways to get the paid data" (see the consolidated `research/77`).

## Bottom line
No free, official, ready-made "point-in-time constituents" DB exists for NSE
indices (no CRSP/S&P equivalent that's free). The reliable free route is
**reconstruction from NSE's free daily bhavcopy + Masters (1994/95+, with a
"Deleted" flag)** — exactly what a July-2026 academic paper validated (85–90%
historical accuracy) and exactly what this project already does
(`point_in_time_universe_resolver`, §53 slice 2). Curated event lists exist but
are stale or partial.

## Ranked free sources
1. **NSE bhavcopy + Masters (reconstruction)** — `nsearchives.nseindia.com`; each
   day lists every security that traded (survivorship-free by construction); Masters
   "Deleted" flag marks later delistings. Free, no auth. Tools: `jugaad-data`,
   `nser`. NSE's own methodology PDF: `archives.nseindia.com/content/press/Data_details_CM.pdf`.
   **This is the primary path (already built here).**
2. **Academic validation** — Ranse 2026, *Survivorship Bias in Emerging-Market
   Small-Cap Indices* (arXiv 2603.19380 / SSRN 5833162): reconstructs NIFTY Smallcap
   250 point-in-time from bhavcopy; survivor-only backtests overstate returns 4.94pp
   / Sharpe 0.097. Method public; output file not confirmed released.
3. **NSE `IndexInclExcl.xls`** (`archives.nseindia.com/content/indices/IndexInclExcl.xls`)
   — official add/exclude events across ~35 indices, but **stale since Sep-2020**.
4. **niftyindices.com monthly reports** — constituent/market-cap PDFs from ~Apr-2013;
   free but manual PDF diffing, no bulk CSV.
5. **Wikipedia NIFTY 50 "Index changes"** — dated add/remove table 2005–2025, CC-BY-SA,
   scriptable; cross-check only (Grade B/C).
6. **IIMA Fama-French/Momentum India library** (`faculty.iima.ac.in/iffm/...`) —
   free factor/portfolio returns 1993–2025; NOT constituent membership.
7. **CMIE Prowess** — the functional Indian CRSP analog; **paid** (institutional
   library only), flagged as the gold-standard fallback, not free.
8. **F&O-eligibility-by-date** — **no free consolidated list**; reconstruct from the
   F&O-segment bhavcopy (a symbol with FUT/OPT trading on a date = eligible then) +
   NSE circulars for rule-change dates. (This is the defensible free method.)
9. **niftyhistory.in** — claims free survivorship-free constituent CSVs since
   inception; **UNVERIFIED** (403 to bots); do not rely on without a human check.

## Verdict & recommendation
Free survivorship-free NSE universe = **reconstruct from bhavcopy** (done), sanity-
checked against Wikipedia (2005+) and `IndexInclExcl.xls` (1998–2020). F&O universe
= reconstruct from F&O bhavcopy presence. No free ready-made membership DB; Prowess
is the paid gold standard. Pre-2004 NIFTY-50 add/remove has no free structured source.

## Not covered / open
Manual browser check of niftyhistory.in; exhaustive per-circular F&O-eligibility
enumeration; BSE-side equivalents. Web-search budget was exhausted late in the pass.
