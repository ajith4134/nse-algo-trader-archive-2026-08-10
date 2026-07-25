# Project: NSE Autonomous Algo Trading Bot

## What this is
An autonomous, intraday-only trading system for Indian markets. Positions are
always squared off before market close — no overnight carry, ever, in any
segment.

**Phase 1 scope (active now):** NSE cash equity intraday + NSE options
intraday (index options: NIFTY, NIFTYNXT50, FINNIFTY, MIDCPNIFTY, BANKNIFTY;
plus NSE single-stock options, ~210 stock-option underlyings (215 total option underlyings incl. 5 indices), reviewed quarterly).

**Deferred to a later phase (do not build yet):** NSE/BSE futures, commodity
derivatives, BSE index options (SENSEX, BANKEX).

**Stack decisions already made:** Python (broker SDK + ML ecosystem fit).
Broker (execution): Zerodha Kite Connect (chosen for phase 1; broker-
integration layer must stay swappable — do not hardcode Kite specifics
outside the broker integration layer). Data sourcing (Layer 2): **not
Kite-only** — Upstox, Angel One, ICICI Direct, and Groww APIs are also
planned as interchangeable data sources (decided `docs/PLAN.md` §8a.12);
the data-ingestion layer must treat every broker's data API as swappable
the same way the execution layer treats brokers as swappable.

## Regulatory constraints (binding, not optional)
- Runs under SEBI's Feb 2025 "Safer Participation of Retail Investors in
  Algorithmic Trading" framework (fully mandatory as of Apr 1, 2026).
- Broker is "principal," this bot is "agent" — all orders route through the
  broker's API, never direct-to-exchange.
- This is a **white-box** algo (personal use only, not distributed to other
  users). Must stay under 10 orders/sec/exchange/client, or it crosses into
  mandatory-registration territory.
- Every order must carry the exchange-assigned Algo-ID once wired up in the
  execution layer.
- If this bot is ever offered to other people, that changes the regulatory
  category entirely (SEBI Research Analyst registration) — flag loudly before
  building anything that shares strategies/signals with another account.

## Rule A — Layer-by-layer build, verify before advancing
Build one feature/layer at a time, in dependency order (see
`docs/flowcharts/00_project_overview.md` for the layer roadmap). After
building a feature:
1. Verify it (tests + a manual check against real/sample data).
2. Explicitly confirm — out loud, in conversation — that nothing more is
   needed on this feature.
3. Only then move to the next layer. Do not start the next layer's code
   while the current one is still open.

## Rule B — Living flow-chart notes (update after every feature)
After every feature is completed, update the running notes in
`docs/flowcharts/`, written like cumulative class notes:
- A data-flow diagram from the very start of the pipeline through the new
  feature (not just the new feature in isolation).
- For the new feature specifically: every function name, every import, the
  exact type/shape of data it exports, and the full list of files that
  belong to it.
- Never delete old notes — they accumulate. One file per layer/feature,
  cross-linked from `00_project_overview.md`.

## Rule C — Self-describing names
Every file, module, function, class, and variable name must reveal its role
by name alone — if you only read the name, you should know what it does.
No generic `utils.py` / `helper()` / `data` / `manager` unless qualified with
what it actually does. Applies to edits of existing code too, not just new
code.

## Rule D — Research, planning, and important discussions get saved to files, every time, without fail
Any non-trivial research pass, planning/architecture discussion, or decision
made in conversation must be written to a file under `docs/research/` (or
`docs/flowcharts/` if it's about an already-built feature's data flow)
before the turn is considered done — never left to live only in chat
history. This includes: research findings and sources, candidate plans and
their ranking/recommendation, and the reasoning behind any non-obvious
decision. Update the relevant index file (`docs/flowcharts/00_project_overview.md`
or a new `docs/research/` index) to point to it so it's discoverable later.

## Rule E — License is not a filter when researching borrowable code
This project is for individual/personal use only and will not be
distributed, sold, hosted as a service, or open-sourced. When researching
or recommending existing open-source projects/code to borrow features
from, evaluate on technical merit only — never exclude or downrank a
project because of its license (GPL/AGPL/no-license-asserted/proprietary).
Copyleft source-disclosure obligations trigger on distribution or
offering a network service to others, not on private personal use. If
this project's status ever changes (offered to others, hosted, distributed
— which already changes the regulatory category per the constraints
below), revisit every borrowed piece's license at that point, not before.

## Rule F — Real-data verification gate (every feature, every branch)
No feature, layer, or branch — including all 16 trunks and ~200 AI
branches (research/32-36) — is considered done until it has been
verified against the **real data it will operate on in production**, not
fake/synthetic data.
- Synthetic fixtures may scaffold deterministic unit tests, but they
  NEVER substitute for the real-data verification pass, which is the
  actual sign-off. (Prefer fixtures that are trimmed *real* samples over
  invented ones.)
- "Real data" = the actual source the feature consumes in production:
  live/replayed NSE market data, real Kite API responses, the real NSE
  official reports, and — for AI/learning/paper features — the real
  paper/replay/live stream they learn from. A feature is tested on the
  same data it will run on.
- If the real data is not reachable yet (e.g. live ticks need an open
  market session), that is recorded as an explicit blocker against the
  feature — never a reason to sign off on fake data instead.
- This pairs with Rule A's "verify before advancing": Rule A requires
  tests + a manual check; Rule F fixes that the manual check must be
  against production-real data, for everything, including AI branches.

## Rule G — No orphaned features/files (wired-into-the-loop verification)
Every new feature, file, function, or module must be connected to the
project's execution flow — directly or indirectly — so nothing is built
that no path ever reaches. Checked on every code add, and it is
IMPORTANT (a feature that isn't wired in is not "done").
- On every add, trace the wiring: from the new code, follow who imports/
  calls it, up to either (a) a runnable entry point (a CLI, cron job,
  the paper/live loop, the dashboard) or (b) a layer that another layer
  consumes. "Indirectly in the loop" is fine — Layer N's output feeding
  Layer N+1 counts.
- If nothing currently consumes it, it is allowed ONLY when a **named,
  queued future consumer** is documented (which layer/slice will wire it
  in, and roughly when). Record that pointer in the layer's flowchart
  note. Tests-only-caller with no named future consumer = an orphan:
  either wire it, or don't build it yet.
- Deleting/replacing code: check for and remove now-orphaned callers and
  dead files it leaves behind — no stranded fragments.
- Research/planning docs under `docs/` are reference, not code, and are
  exempt from this rule (they are indexed via the overview instead).
- Pairs with Rule A (build in dependency order) and Rule F (verify on
  real data): a feature is done when it is wired into the loop AND
  verified on the real data it operates on.

## Rule H — Keep the living System Map current (read it first, update it always)
`docs/SYSTEM_MAP.md` is the single source of truth for how the project is
built and how data flows — feature-by-feature, file-by-file, with the real
data-flow edges (generated from the code's AST import graph, not memory).
- **Read it FIRST** — before opening source files — to understand where we
  stand. It exists so you (and any fresh agent on any server) can grasp the
  whole system without grepping the tree.
- **Update it on EVERY new/renamed/deleted file or feature, and whenever the
  data flow between features changes** — in the SAME change. Follow the
  "§0 · HOW TO MAINTAIN" protocol inside it: re-run the extractor to get the
  true graph, update the system diagram (§1), the feature's registry block
  (§2), any runtime flow (§3), and append to the maintenance ledger (§4).
- **Two required confirmations to the user, every time code files are added
  or changed** (a `PostToolUse` hook also reminds you, so you never need to be
  told): (1) BEFORE/at the start, having read `docs/SYSTEM_MAP.md`, post the
  message **"📖 Read the flow chart"**; (2) AFTER updating the map, post
  **"🗺️ Updated the flow chart"**. Send both literally so the user can see the
  map was consulted and kept current.
- Never hand-guess the graph — always regenerate the ground truth from the
  code so the map stays TRUE to what is on the server.
- This complements Rule B (per-layer flowchart notes): Rule B is the deep
  per-feature narrative; Rule H is the one consolidated cross-feature map.

## Rule I — Never compromise a feature down to what's on hand; go acquire what it needs
If a feature needs data — or ANYTHING (a dataset, a live/historical source, a
tool, a library, an API, a capability, a reference) — that the project does
not yet have, **do NOT scope the feature down, stub it, or settle for only
what is already present.** Instead:
1. Name exactly what the feature needs (the missing data/tool/source and why).
2. **Search online** for where to legitimately obtain it (official APIs, data
   providers, OSS projects/datasets, docs) — use the `deep-research` /
   `sourcing-oss-parts` skills.
3. **Acquire and integrate it** if legitimately available (respecting Rule E —
   license is not a filter for personal use — and the regulatory/no-secrets
   constraints; never bypass auth/law/market-manipulation lines).
4. If it genuinely cannot be obtained yet, record that as an explicit blocker
   against the feature (like Rule F's real-data blocker) — never silently
   deliver a degraded version as if it were complete.
- Applies to EVERYTHING, not just data. "The project only has X" is never a
  reason to build a lesser feature — find and bring in what the full feature
  requires.
- Pairs with Rule F (verify on the REAL data it needs — so first go get that
  data), Rule E (license-blind sourcing), the full-universe rule (never a
  sample), and the sourcing/building-from-ideas skills.

## Rule J — Hermetic simulation-harness verification when real data is unavailable
When a feature's REAL production data is not reachable yet (market closed, no
live session, a source not ingested), do NOT leave it unverified. Build a
hermetic simulation/injection harness (established practice: hermetic tests +
dependency-injection test seams + in-memory fakes + contract tests — see
`docs/research/45`):
1. **Inject the exact data SHAPE** the feature consumes — trimmed REAL samples
   preferred over invented (Rule F) — through the SAME swappable interface the
   real source uses (a faithful in-memory fake / replay source, not an ad-hoc
   mock). Verify EVERY function: input contracts, internal file→file data flow,
   output contracts/shapes, and error paths.
2. **Hermetic isolation (non-negotiable):** the fake/injected source sits behind
   the DI seam, so PRODUCTION selects the real adapter and the fake is NEVER
   wired into the live path — the injected test data is structurally unable to
   reach real behavior (verify: the fake appears only under `tests/`, never in
   `src/`; prod instantiates the real adapter). A fake that could leak into the
   live path is a bug to fix BEFORE adding the feature.
3. **This verifies FUNCTIONAL correctness ONLY.** It does NOT satisfy Rule F's
   real-data sign-off, which stays an explicit OPEN BLOCKER against the feature
   until performed on the actual production data. Never present a sim-verified
   feature as fully done — label it "functionally verified (sim); real-data pass
   pending (blocker)."
- Pairs with Rule F (sim never substitutes for the real-data gate), Rule G (the
  harness exercises the real interface/wiring, not a parallel toy), Rule A
  (verify before advancing), Rule I (if even the data shape is unknown, go
  acquire a real sample first).

## Rule K — No silent skips: every deferral is tracked, surfaced, and cleared
The user must NEVER have to point out something I promised and skipped. Any time
I defer work — the moment I write or say "queued", "next", "named future
consumer", "deferred", "TODO", "open blocker", "later slice", "follow-up", or
otherwise promise something not done in this change — I MUST, in the same turn:
1. **Record it** as a tracked task (TaskCreate) AND append it to
   `docs/BACKLOG.md` under the owning feature, with: what it is, why deferred,
   and what "done" looks like. Nothing deferred lives only in prose.
2. **Grade the parent honestly.** A feature is **not "fully done" if its intended
   PRIMARY consumer is still queued.** Display-only wiring (e.g. a dashboard
   panel) does NOT fulfill a "feed into decisions / the loop" promise — that is
   "functionally built, purpose-consumer QUEUED", not done. Say which one it is
   at sign-off, out loud (pairs with Rule A sign-off and Rule G no-orphans).
3. **Clear before diverging.** Before starting a NEW, unrelated feature, FIRST
   read `docs/BACKLOG.md`; if the feature I just finished has unfulfilled queued
   items, either (a) do them next, or (b) explicitly list them to the user and
   get a decision to defer — never silently jump to unrelated work leaving
   promises dangling.
4. **Surface every sign-off.** End each slice by listing the still-open backlog
   items for that feature, so the user sees the outstanding queue without asking.
- Backlog items are closed in `docs/BACKLOG.md` (struck through / moved to a Done
  section) only when actually delivered + verified, or when the user explicitly
  drops them. This is the standing to-do memory across turns/sessions — treat it
  as authoritative, and reconcile it with the live task list each session start.
- Pairs with Rule A (sign off before advancing), Rule G (no orphans / named
  consumer), Rule F/J (open real-data blockers are backlog items too), Rule H
  (the map records structure; the backlog records promised-but-undone work).

## Rule L — Three segments EQUAL by default; priority order only as the tie-break under a constraint
By default treat the three segments as **EQUAL priority** — cover the FULL universe
of all three equally, never over-focusing on any one (and never a cash-only path
while options lag). The segments:
- NSE **index options** (NIFTY, BANKNIFTY, FINNIFTY, MIDCPNIFTY, NIFTYNXT50)
- NSE **stock options** (~210 underlyings)
- NSE **cash equity intraday**

**Only when you genuinely cannot serve all three equally** — a rate-limit / time /
compute / budget constraint, or a deliberate single-segment focus — apply this
tie-break order to decide what gets priority and what is dropped LAST/first:
1. index options → 2. stock options → 3. cash (cash yields first).
So: equal breadth normally; index-options-first only when something must give.
This sits on top of the full-universe rule — within each covered segment always the
FULL universe (all 5 index-option underlyings with near-expiry ATM/ITM/OTM ladders,
all ~210 stock-option underlyings with ladders, all ~2,000 cash names), never a sample.

## Rule M — Plan Altitude: never tunnel on one topic; keep the WHOLE plan (and the live map) in view
Going deep on one feature for many slices must never let the rest of the plan
fall out of view. `docs/MASTER_PROGRESS.md` holds the ENTIRE plan at a glance
(Layers 1–11, §53 tiers, ADVANCED slices, multi-broker, dashboard, blockers,
paused items) — an index over PLAN/SYSTEM_MAP/BACKLOG.
- **Session start:** read `MASTER_PROGRESS.md` (with `BACKLOG.md`) and say where we
  are in the WHOLE plan before doing anything.
- **Every sign-off:** after the per-feature open items (Rule K), add a one-line
  **whole-plan altitude check** — where the finished slice sits in `MASTER_PROGRESS`
  and the top 2–3 remaining big-rocks across the ENTIRE plan. **Re-pick the next work
  from `MASTER_PROGRESS` by whole-plan priority, not by whatever is locally adjacent.**
- **Anti-tunnel trigger:** after ~3 consecutive slices in one feature-area (or before
  starting a new area), force the zoom-out above and re-confirm this is still the
  highest-value area.
- **Keep it TRUE TO THE SERVER, always:** update `MASTER_PROGRESS.md` AND
  `SYSTEM_MAP.md` in the SAME change as any new/changed feature (pairs with Rule H).
  The dashboard `/map` page renders `SYSTEM_MAP.md`, so the diagram the user sees must
  always match what is actually running — never let the map drift behind the code.

## Rule N — Every feature is VISIBLE on the dashboard (built ≠ done until displayed)
Wiring a feature into the loop is not enough; if the user can't SEE it, it's not done.
- A user-visible feature is **not "done" until it registers a dashboard SURFACE**
  (title, status, headline metrics / rows) via the feature-surface registry
  (`docs/research/91`) AND appears in the dashboard feature-coverage manifest.
  This is the mirror of Rule K: display-only never satisfied "wired into decisions";
  now wired-but-invisible never satisfies "shipped" either.
- A **coverage audit/test** fails when a manifest feature has no surface, and the
  dashboard shows a **feature-coverage panel** listing every feature's live status —
  so "is the dashboard up to date with all features?" is answerable at a glance.
- Pairs with Rule G (no orphans), Rule H/M (keep the map current), Rule K (done-criteria).

## Non-negotiables carried through every layer
- Intraday only. Every position auto-squares-off before close. No exceptions
  per-segment, ever, unless a future phase explicitly revisits this.
- Never commit API keys/secrets — `.env` is gitignored; broker credentials
  are loaded from environment/secret store only.
