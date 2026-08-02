# Project: NSE Autonomous Algo Trading Bot

> **This file is the SLIM rule index.** Each rule below is stated in full-force but compact form,
> tagged with **how it is enforced**: `[HOOK]` = a deterministic Claude Code hook blocks the turn
> until satisfied · `[JUDGMENT]` = self-enforced prose + a skill. The complete elaboration of every
> rule (examples, pairings, rationale) lives in **`docs/RULES.md`**. Why slim + hooks:
> `docs/research/159` (bloat decays adherence; verifiable gates beat prose) + `docs/research/160`.
> The rules themselves are UNCHANGED — only relocated for reliability.

## What this is
An autonomous, **intraday-only** trading system for Indian markets. Positions are always squared off
before market close — no overnight carry, ever, in any segment.

**Phase 1 scope (active now):** NSE cash equity intraday + NSE options intraday. Index options:
NIFTY, NIFTYNXT50, FINNIFTY, MIDCPNIFTY, BANKNIFTY; plus NSE single-stock options (~210 stock-option
underlyings; 215 total option underlyings incl. the 5 indices; reviewed quarterly).

**Deferred to a later phase (do not build yet):** NSE/BSE futures, commodity derivatives, BSE index
options (SENSEX, BANKEX).

**Stack decisions already made:** Python (broker SDK + ML fit). Execution broker: Zerodha Kite Connect
(phase 1; the broker-integration layer must stay swappable — no Kite specifics outside it). Data
sourcing (Layer 2) is **not Kite-only** — Upstox, Angel One, ICICI Direct, Groww APIs are also planned
as interchangeable data sources (`docs/PLAN.md` §8a.12); the data-ingestion layer treats every broker's
data API as swappable, the same way execution treats brokers as swappable.

## Regulatory constraints (binding — never abbreviate or trade away)
- Runs under SEBI's Feb 2025 "Safer Participation of Retail Investors in Algorithmic Trading" framework
  (fully mandatory as of Apr 1, 2026).
- Broker is "principal," this bot is "agent" — all orders route through the broker's API, never
  direct-to-exchange.
- This is a **white-box** algo (personal use only, not distributed). Must stay under
  **10 orders/sec/exchange/client**, or it crosses into mandatory-registration territory.
- Every order must carry the exchange-assigned **Algo-ID** once wired up in the execution layer.
- If this bot is ever offered to other people, that changes the regulatory category entirely (SEBI
  Research Analyst registration) — **flag loudly** before building anything that shares strategies/
  signals with another account.

## The rules (full text in `docs/RULES.md`)

- **A — Engine-by-engine build, verify before advancing.** `[JUDGMENT + HOOK]` The unit of work is a
  COMPLETE engine-grade feature (Rule P), not a thin advisory slice. After each engine: run the full
  Rule-P checklist + the Rule-F real-data pass (outputs inspected by eye), confirm out loud it is
  decision-grade & complete (only a logged live-data blocker may remain), THEN advance. *Stop hooks
  block on unmet map/quality gates.*

- **B — Living flow-chart notes.** `[JUDGMENT]` After every feature, update `docs/flowcharts/` like
  cumulative class notes: full pipeline diagram through the new feature; every function/import/exported
  shape + its file list. Never delete old notes.

- **C — Self-describing names.** `[JUDGMENT]` Every file/module/function/class/var name reveals its role
  by name alone. No bare `utils.py`/`helper()`/`data`/`manager`. Applies to edits too.

- **D — Save research/planning to files, every time.** `[JUDGMENT + reminder HOOK]` Any non-trivial
  research, planning, or non-obvious decision is written under `docs/research/` (or `docs/flowcharts/`
  for built-feature data flow) before the turn ends, and indexed. *PostToolUse reminds that a research
  design doc must record a REAL sourcing search, not a from-memory note.*

- **E — License is not a filter when sourcing.** `[JUDGMENT/policy]` Personal-use, never distributed —
  evaluate OSS on technical merit only, never downrank on license. Revisit only if the project's status
  changes (offered to others / hosted / distributed).

- **F — Real-data verification gate.** `[JUDGMENT]` No feature/branch is done until verified against the
  REAL production data it consumes (live/replayed NSE data, real Kite responses, real reports, the real
  paper/replay/live stream). Synthetic fixtures scaffold unit tests but NEVER substitute. Unreachable
  real data (market closed) = an explicit logged blocker, never a reason to sign off on fake data.

- **G — No orphaned features/files.** `[JUDGMENT]` Every new file/function/module is wired into the
  execution flow (up to a runnable entry point or a consuming layer). If nothing consumes it yet, it is
  allowed ONLY with a named, queued future consumer documented in the flowchart note. Remove dead
  callers/files on delete.

- **H — Keep `docs/SYSTEM_MAP.md` current; read it first.** `[HOOK]` It is the single source of truth
  for structure + data flow (from the code's AST import graph, not memory). READ it before opening
  source. UPDATE it (regenerate ground truth → §1 diagram, §2 registry, §3 flow, §4 ledger) in the SAME
  change as any new/renamed/deleted file or changed data-flow. Post **"📖 Read the flow chart"** at the
  start and **"🗺️ Updated the flow chart"** after updating. *Stop hook blocks if src changed but the map
  didn't; PostToolUse reminds (throttled).*

- **H.1 — The §1 DIAGRAM must stay true to the code.** `[HOOK]` The `/map` page renders §1 — on every
  feature/module/edge change reconcile the diagram against the extractor: node completeness, edge
  fidelity, label truth, counts, and validate the Mermaid parses. *Stop hook runs
  `scripts/check_system_map_diagram_fidelity.py` and blocks on drift.*

- **I — Never compromise a feature down to what's on hand; acquire what it needs.** `[JUDGMENT]` If a
  feature needs data/tool/source/library/capability the project lacks: name it, search online for a
  legitimate source, acquire + integrate it (Rule E license-blind; never bypass auth/law/market-
  manipulation lines). If genuinely unobtainable, log an explicit blocker — never silently ship a
  degraded version.

- **J — Hermetic simulation-harness verification when real data is unavailable.** `[JUDGMENT]` Inject
  the exact real data SHAPE (trimmed real samples preferred) through the SAME swappable interface,
  behind a DI seam that PRODUCTION never selects (the fake lives only under `tests/`). Verifies
  FUNCTIONAL correctness only — the Rule-F real-data pass stays an OPEN BLOCKER. Label such features
  "functionally verified (sim); real-data pass pending."

- **K — No silent skips: every deferral is tracked, surfaced, cleared.** `[JUDGMENT + nudge HOOK]` The
  moment anything is deferred (queued/next/named-consumer/TODO/open-blocker/later/follow-up): record it
  as a TaskCreate task AND in `docs/BACKLOG.md` under its feature (what, why, done-looks-like). A feature
  whose PRIMARY consumer is still queued is NOT done (display-only ≠ wired-into-decisions). Before
  starting NEW unrelated work, read `docs/BACKLOG.md` and clear/surface the prior feature's queued
  items. List open backlog items at every sign-off.

- **L — Three segments EQUAL by default; priority order only as a constrained tie-break.** `[JUDGMENT/
  policy]` Cover the FULL universe of index options / stock options / cash equity equally (never a
  cash-only path while options lag). Only under a genuine constraint apply the tie-break: index options
  → stock options → cash (cash yields first). Within any covered segment, always the FULL universe (all
  5 index underlyings with ATM/ITM/OTM ladders, all ~210 stock-option underlyings, all ~2,000 cash
  names), never a sample.

- **M — Plan altitude: never tunnel; keep the whole plan + live map in view.** `[JUDGMENT]` Read
  `docs/MASTER_PROGRESS.md` (with `BACKLOG.md`) at session start and say where we are in the WHOLE plan.
  At every sign-off add a one-line whole-plan altitude check + re-pick next work by whole-plan priority,
  not local adjacency. After ~3 consecutive slices in one area, force a zoom-out. Keep MASTER_PROGRESS +
  SYSTEM_MAP true to the server in the same change.

- **N — Every feature is VISIBLE on the dashboard.** `[HOOK]` A user-visible feature is not done until
  it registers a dashboard SURFACE (title/status/metrics via the feature-surface registry) AND appears
  in the coverage manifest; a coverage audit fails on a manifest feature with no surface. *Stop hook
  blocks if dashboard code changed but the live page wasn't re-verified
  (`/tmp/claude_dashboard_page_verified`).*

- **O — Production-grade code quality (never simplified).** `[JUDGMENT + static-half HOOK]` Full correct
  implementation, not a reduced/toy subset. (1) SURFACE every OSS rejection at sign-off for double-check;
  bespoke replacements must be COMPLETE, not lite. **(1a) Rejection-evidence tiers:** triage OSS on
  mechanical facts (`scripts/probe_oss_candidates.py`), never README prose. Tier-1 facts (won't install
  here · archived · yanked · wrong I/O shape by signature · stale past a stated threshold) may disqualify
  alone; any rejection on correctness/depth/quality needs tier-2 evidence — you read the implementing
  source, ran it on real input, or cite a specific issue. Label the tier per rejection at sign-off. (2) Real-data-by-eye is the true correctness gate —
  every serious bug here passed unit tests and was caught only on real data. (3) Never swallow errors
  silently — count/log/surface failures (`except: pass` banned). (4) Numeric/boundary robustness:
  guard degenerate inputs, normalize before combining scales, stable formulas. (5) Financial checklist:
  no look-ahead/leakage, IST↔UTC explicit, money precision, sign/unit conventions, lot/tick correctness.
  (6) Test failure + adversarial paths + invariants. (7) Depth over breadth-theater. *Quality-gate Stop
  hook enforces the static half (ruff+mypy clean) deterministically.*

- **P — ENGINE-GRADE DEPTH: build real engines, not skeletons.** `[JUDGMENT + tests HOOK]` Every feature
  is a real ENGINE — genuine algorithm/model/solver/simulation + carried STATE + a raw-input pipeline +
  decision-grade output that CHANGES behavior — NOT a ~60-150-line scalar over a SQLite table dressed in
  engine vocabulary (SOTA bar: `docs/research/155`). Build the WHOLE engine at once (data pipeline · core
  · state store · decision integration · full tests), not thin advisory fragments. Integrate REAL
  powerful libraries (CVXPY, LightGBM, PyTorch, statsmodels, …) — installs are pre-approved; don't
  reimplement lite. LOC is a symptom of real function, never a target — never pad. Use the
  `building-engine-grade-features` skill. *Quality-gate Stop hook enforces tests/lint clean.*

- **Q — Thin data NEVER shrinks a feature; build the FULLEST function, gate only ACTIVATION.** `[JUDGMENT]`
  When a feature's full function needs more closed trades/history/samples than exist today, build the
  COMPLETE algorithm anyway. Never design a smaller feature, drop a modelling layer, pick a weaker
  algorithm class, or defer parts to "a later slice" because N is small. Instead: (1) full algorithm as
  if data were abundant; (2) an explicit MATURITY LADDER inside the engine — per-component minimum-sample
  thresholds, honest `gathering`→`earned` status, safe identity behavior while immature; (3) maturity is
  AUTOMATIC — components arm themselves as trades accrue, no code change, no new slice; (4) handle small N
  *inside* the full algorithm (priors, shrinkage, hierarchical pooling, regularization, widened
  uncertainty, abstention), never by simplifying it; (5) show `have N / need M` per component on the
  dashboard; (6) log the accrual gap as the one permissible Rule-K blocker — activation deferred, function
  never. Closes Rule P's "small N" escape hatch.

## Non-negotiables carried through every layer
- **Intraday only.** Every position auto-squares-off before close. No exceptions per-segment, ever,
  unless a future phase explicitly revisits this.
- **Never commit API keys/secrets.** `.env` is gitignored; broker/Telegram credentials load from
  environment / secret store only — never in code or committed docs.
