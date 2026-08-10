# RULES.md — the FULL, authoritative rule text (Rules A–P)

> This is the complete elaboration of every rule. `CLAUDE.md` holds a SLIM index
> (each rule in 2–4 lines + how it is enforced); this file is the full text it points to.
> Rationale for the slim/hook split: docs/research/160. Nothing here was cut from the
> original CLAUDE.md — it is preserved verbatim below.

---

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

## Rule A — Engine-by-engine build, verify before advancing
Build one feature/layer at a time, in dependency order (see
`docs/flowcharts/00_project_overview.md` for the layer roadmap). **The unit of
work is a COMPLETE ENGINE-GRADE feature (Rule P), not a thin advisory slice** —
scope and build the whole engine (data pipeline · algorithm/model core · state
store · decision integration · full tests) as one cohesive deliverable,
assembling and verifying it layer-by-layer on real data until it works
end-to-end and changes a real decision. "One at a time" governs ENGINES; it must
NOT be used to justify shipping a scalar-diagnostic fragment as a finished
feature. After building an engine:
1. Verify it — the full Rule-P checklist + the Rule-F real-data pass with outputs
   inspected by eye (not just "tests pass").
2. Explicitly confirm — out loud — that the engine is decision-grade and complete
   (only a documented live-data-accrual blocker may remain, Rule K).
3. Only then move to the next engine. Do not start the next while the current is open.

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

### Rule H.1 — The §1 DIAGRAM must stay true to the code (the rendered flow-chart, not just the ledger)
The `/map` page renders the §1 Mermaid diagram; it is what the user actually
*sees*. Updating only the §4 ledger while the §1 diagram drifts is a Rule-H
violation (this happened: whole trunks/features were missing from the rendered
chart). So on EVERY change that adds/renames/removes a feature package, module,
or a cross-feature data-flow edge, you MUST reconcile the §1 diagram against the
`§0` extractor output IN THE SAME CHANGE, verifying ALL of:
1. **Node completeness** — every feature package printed by the extractor has a
   node in the diagram (no missing features; the extractor's package count ==
   the diagram's feature-node count). Persisted stores the feature owns
   (`*.sqlite3`/`*.json`) appear as cylinders.
2. **Edge fidelity** — every *material* cross-feature edge the extractor reports
   is drawn (data-flow direction), with a truthful label; no invented edges.
   Any edges deliberately omitted for readability (e.g. composition-root imports)
   are called out in the honesty note, not silently dropped.
3. **Label truth** — each node's label reflects the feature's REAL current role
   and, for the concept-tree trunks (VII CONSCIENCE, VIII SENTIENCE, …), the
   ACTUAL built branches — not a stale subset. If a trunk completes, the node
   says so and lists its branches.
4. **Counts** — the header's "N modules across M feature packages" equals the
   extractor's totals; the spine prose's import counts match the extractor.
5. **Validate** — after editing, confirm the Mermaid parses (every edge endpoint
   is a defined node; no dangling refs; nothing unconnected) before signing off.
Treat the diagram as a first-class deliverable: detailed, accurate, and true to
what is on the server — a fresh agent or the user must be able to trust it
literally. (Pairs with Rule N: the diagram is the user-visible map, so
"built ≠ done until the rendered chart shows it truthfully.")

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

## Rule O — Production-grade code quality (never simplified; surface every rejection; build deep, not thin)
Every feature must be PRODUCTION-GRADE — the full, correct implementation, not a reduced/stubbed/
toy subset chosen to save effort. When a slice looks small, that must be because the algorithm is
genuinely small, NOT because functionality was cut. Concretely:
1. **Surface OSS rejections for double-check.** Whenever a `sourcing-oss-parts`/web-search pass rejects
   a library/tool, SURFACE it at sign-off (what, why, alternative chosen) so the user can double-check
   and override; offer to vendor the rejected option. Never a silent reject. When reimplementing
   bespoke instead of a rejected library, the bespoke version must be COMPLETE for the use case (the
   same primitives, not a lite subset) — e.g. real MCDM scalarization + normalization, not a naive
   scale-broken weighted-sum.
   **O.1a — REJECTION-EVIDENCE TIERS (2026-07-27).** A rejection is an irreversible, invisible decision,
   so it carries the HIGHEST evidence bar, not the lowest. Triage candidates on mechanical facts
   (`scripts/probe_oss_candidates.py`: installability on this aarch64 box · maintenance recency ·
   release cadence · archived/yanked · test-suite coverage of the needed capability · correctness-issue
   count · API signatures), never on README prose.
   · **Tier-1** facts alone may disqualify ONLY for objective, mechanically-checkable reasons: won't
     install here · archived upstream · release yanked · wrong language · demonstrably wrong I/O shape
     (verified by signature) · unmaintained past a stated date threshold.
   · **Tier-2** — any rejection on CORRECTNESS, DEPTH or QUALITY grounds requires at least one of:
     (a) reading the file that implements the piece, (b) installing and running it on real input,
     (c) citing a specific issue/changelog entry. A README impression is never sufficient.
   When surfacing rejections at sign-off, LABEL the tier of evidence behind each one. Tier-2 claims
   backed only by tier-1 evidence mean the sourcing pass is not finished.
2. **Real-data verification is the true correctness gate — unit tests are not enough.** Numeric/decision
   code is not done until its REAL outputs are inspected by eye on real data (Rule F), not merely "it
   ran without error." (Every serious bug in this project — scale-swamped weighted-sum, number-truncation
   6580→658, profit-in-crore mistaken for a price target, cross-attribution — passed hermetic tests and
   was caught only on real data.)
3. **Never swallow errors silently.** Best-effort code (loop cadences, background threads) may keep the
   loop alive, but it must COUNT/LOG/SURFACE its failures (an error counter per feature), so a silently-
   dead feature is visibly distinguishable from a healthy one. `except: pass` with no signal is banned.
4. **Numeric & boundary robustness is mandatory:** guard degenerate inputs (empty/singleton series,
   div-by-zero, None/NaN); NORMALIZE before combining different-scale quantities; use stable formulas.
5. **Financial-domain correctness checklist on every trading-path change:** no look-ahead/leakage;
   timezone-explicit datetimes (IST↔UTC); money precision/rounding; explicit sign & unit conventions
   (returns as fraction vs %, loss magnitudes positive); position/lot/tick correctness.
6. **Test the failure and adversarial paths + invariants**, not just the happy path (noise-rejection,
   fallback-on-failure, "decomposition sums to total", monotonicity). Green ≠ correct.
7. **Depth over breadth-theater.** The atlas has ~197 branches; do NOT satisfy a branch with a thin
   read-only diagnostic when the branch calls for a real decision-grade organ. If the deep version is
   market-gated/data-gated (real ML model, live earning harness, microstructure fill), build the fullest
   version buildable now AND record the depth gap explicitly (Rule K) — never present a diagnostic-grade
   stand-in as the finished ultra-advanced branch. Prefer fewer, DEEPER slices over many shallow ones.
- Pairs with Rule F (real-data gate), Rule I (acquire what depth needs), Rule K (record depth gaps),
  and the memory `feedback_surface_rejections_and_production_grade`.

## Rule P — ENGINE-GRADE DEPTH: build real engines, not skeletons (the core quality bar)
**Every feature is a real ENGINE — a load-bearing subsystem with a genuine algorithm/model/solver,
carried state, a real input pipeline, and a decision-grade output — NOT a ~60-150-line scalar computed
from a SQLite table and dressed in engine vocabulary.** The SOTA benchmark (`docs/research/155`) is the
bar: SOAR ships each faculty as a tested kernel subsystem (semantic memory 8,798 LOC, episodic 6,705);
Qlib ships 24 trained ML models + a CVXPY optimizer + a point-in-time DB; NautilusTrader ships an L1/L2/L3
order book with queue-position + nanosecond latency; even the *weakest* real projects (OpenCog PLN,
MicroPsi) are hundreds–thousands of lines of runnable math/logic with test suites. A one-function
scalar-diagnostic faculty "is not a thinner version of what they do — it is a different category of
artifact: a labeling/dashboard layer over data that already exists, with no engine underneath." This
project's ambition (a 16-trunk / ~197-branch ultra-advanced autonomous-AI organism) demands the engine,
not the label. This rule OVERRIDES any tendency (in Rule A slicing, or default minimalism) to ship thin.

### P.1 — The ENGINE-GRADE checklist (a feature is NOT done until ALL hold)
1. **A real algorithm / model / solver / simulation** — an optimization actually solved, a model actually
   trained (with train/validate/walk-forward + a generalization claim), a formal inference procedure, or
   a real simulation. NOT a closed-form summary statistic over rows that already encode the answer.
2. **Carried STATE** — the engine persists and evolves state across decisions (learned parameters, model
   weights, a fitted distribution, an order book, a knowledge store) — not a stateless scalar recomputed
   each call.
3. **A real input pipeline from raw sources** — ingests raw data (ticks/bars/filings/features) and
   transforms it through a real pipeline; it does not merely read an outcome column someone else produced.
4. **Decision-grade output that CHANGES behavior** — the output actually alters a real decision (size,
   entry, exit, allocation, veto). "Advisory / read-only / identity-until-a-market-gated-earning" is NOT
   done — build the FULL acting path + its earning/calibration mechanism; the ONLY permissible open
   blocker is the final live-data accrual (Rule F/J), and it must be recorded (Rule K).
5. **Depth-justified size** — the engine is as large as the real algorithm honestly requires, decomposed
   into cohesive modules (data adapter · core algorithm/model · state/model store · decision integration ·
   verification). Typically MANY files and hundreds–thousands of lines. **LOC is a SYMPTOM of doing the
   real thing, never a target — do NOT pad; every line must earn its place implementing real function.**
6. **Comprehensive tests** — unit + property/invariant + failure/adversarial + the Rule-F real-data pass
   with outputs inspected by eye. Errors surfaced, never swallowed (Rule O.3).
7. **Correct vocabulary** — call it "engine/model/optimizer/reasoner" ONLY when there is a real solver/
   inference procedure + carried state; otherwise call it "monitor/diagnostic" and treat it as such.

### P.2 — Build the WHOLE engine at once (the unit of work is the engine, not a thin slice)
Do NOT ship a feature as a sequence of thin advisory fragments. **Scope and build the COMPLETE engine as
one cohesive deliverable** — its data pipeline, algorithm/model core, state store, decision integration,
and full test suite — assembling + verifying it layer-by-layer on real data until it works end-to-end and
changes a real decision. This is heavier per feature and that is the point: fewer, DEEPER features that
are actually decision-grade, over many shallow ones (Rule O.7). Use the `building-engine-grade-features`
skill for the method. For a large engine, orchestrating the build (parallel sub-component construction +
adversarial verification via a Workflow) is encouraged when available.

### P.3 — Use REAL, powerful libraries for real depth (reverse the lightweight bias)
When a heavyweight library provides genuine depth (CVXPY, LightGBM/XGBoost, PyTorch, statsmodels, river,
PyMC, arch, cvxportfolio, scikit-learn, pymoo, Riskfolio-Lib, …), INTEGRATE it — do not reimplement a
lite bespoke subset to "stay lightweight" (installs are pre-approved,
`feedback_install_freely_no_asking`). Bespoke is justified ONLY when it is genuinely DEEPER or a better
fit than the library — and then it must be full-depth, not a toy. Every rejection is surfaced for the
user's double-check (Rule O.1); default toward the more powerful real engine.

- Pairs with Rule O (production-grade), Rule A (verify before advancing — now per ENGINE), Rule I
  (acquire the real algorithms/data/libraries an engine needs), Rule F/J (real-data is the gate),
  Rule K (record the one permissible live-accrual blocker). Reconciled into Rule A below.

## Rule Q — Thin data NEVER shrinks a feature; build the FULLEST function and let it self-activate
**User directive, 2026-07-27.** When a feature's full function would need more closed trades / more
history / more samples than currently exist, you **build the full function anyway**. Sparse data is a
reason to *gate activation*, never a reason to reduce invention, scope, or ambition.

**Banned (all of these are the SAME mistake):**
- Designing a smaller feature "because we only have N trades" (e.g. dropping a hierarchical/Bayesian
  layer, a per-regime split, a survival model, a multi-objective term, a learned component) and
  substituting a scalar/heuristic.
- Deferring parts of the algorithm to "a later slice, once data accrues" — that is Rule-P thinness
  wearing a schedule.
- Choosing an algorithm class *because* it survives small N, when a richer one is the right answer.

**Required instead — build FULL, gate ACTIVATION:**
1. Implement the complete algorithm/model/solver exactly as it would be built with abundant data.
2. Add an explicit **maturity ladder** inside the engine: a declared minimum-sample requirement per
   component, an honest `status` (`gathering` → `earned`/`active`), and a **safe identity behavior**
   while immature (multiplier `1.0`, no veto, advisory) — the same `is_earned` convention the existing
   gates use.
3. Make maturity **automatic**: as trades/samples accrue, each component crosses its own threshold and
   *switches itself on* with no code change and no new slice. Nothing waits on a human to "come back".
4. Use principled small-N handling INSIDE the full algorithm — priors, shrinkage/partial pooling,
   hierarchical borrowing, regularization, uncertainty widening, abstention — rather than a simpler
   algorithm. Uncertainty is modelled, not avoided.
5. Surface the ladder: the dashboard shows each component's maturity (`have N / need M`) so the user can
   see exactly what is armed and what is still gathering.
6. Log the accrual gap as a Rule-K open blocker ("acting path built + gated; live accrual pending") —
   which is the ONE permissible deferral shape, and only for *activation*, never for *function*.

- Pairs with Rule P (engine-grade depth — this closes the "small N" escape hatch), Rule I (never
  compromise to what's on hand), Rule F/J (real-data pass; accrual gap logged), Rule K (the blocker is
  tracked), Rule N (maturity visible on the dashboard).

## Rule R — Status surfaces are MEASURED from the real server/code state, never hand-authored

**The rule.** Any surface that reports what the system HAS (feature-status catalogue, build-status wall,
AI-atlas coverage, progress boards, `/map`) must be GENERATED from the actual server — never a hand-typed
status that can drift from the code. The generator reads the real ground truth:
- the code's **AST / import graph** (which modules exist, what imports/consumes what — same extractor as
  Rule H),
- the **wiring graph** (is the feature reached from a runnable entry point, or an orphan? — Rule G),
- **live runtime probes** (does it actually run; last-measured signal; error/degraded state),
- the **feature-surface registry + coverage manifest** (Rule N).

**What every row must carry.** A real source file (or "no code") + a machine-derived status
(`built` / `partial` / `not-built` / `blocked` / `orphan`) + the measured signal it was derived from + a
**generation timestamp**. Model the crypto reference wall: *"Generated by <generator> · never
hand-edited · Measured <ts>."*

**Honesty gates.**
- A status that cannot be measured is shown as `UNKNOWN` / `NOT-INSTRUMENTED` — **never** defaulted to
  healthy, built, or done (same discipline as autopoiesis telemetry: UNAVAILABLE ≠ healthy).
- Nothing shows "done/built" that the code does not actually implement + wire. If the tracker prose and
  the code disagree, the CODE wins and the surface reflects the code (and the stale prose is flagged).
- Regenerate on every relevant change; a stale board is a bug.

**The plan side is the one authored part.** The catalogue of what was ever *planned / discussed / idea /
forgotten-skip* is legitimately authored (it is intent, not state) — but its **BUILD-STATUS column is
always machine-derived** and reconciled against the server. Plan = authored; status = measured. Never let
an authored plan row silently assert a build state.

**Pairs with** Rule H (the map is generated from the AST, read-first/update-always), Rule N (every
feature visible on the dashboard), Rule G (orphan detection is a measurable status), Rule K (blocked/
deferred is a real, surfaced status). Origin: user directive 2026-08-03 ("true to what is on the server
state"), modelled on the crypto Feature-Catalogue + Status-Wall (generated, never hand-edited).

## Non-negotiables carried through every layer
- Intraday only. Every position auto-squares-off before close. No exceptions
  per-segment, ever, unless a future phase explicitly revisits this.
- Never commit API keys/secrets — `.env` is gitignored; broker credentials
  are loaded from environment/secret store only.
