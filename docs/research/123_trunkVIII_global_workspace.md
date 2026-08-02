# VIII — Global Workspace / broadcast bus (Trunk VIII keystone)  ·  research/123

**Trunk VIII SENTIENCE & GLOBAL WORKSPACE — the integrator.** Design doc (Rule D).
First slice built the CORRECTED way: OSS sourcing done BEFORE writing code (real search, not a
from-memory note — the lapse the user flagged; now hook-enforced).

## The idea → concrete target
Global Workspace Theory (Baars; Dehaene's "global neuronal workspace"; Blum & Blum's Conscious
Turing Machine): many specialist processes run in parallel, compete for a **limited-capacity
workspace**, and the winning coalition — once it crosses an **ignition threshold** — is **broadcast**
to the whole system as the dominant global context. This is the integrator that turns the bot's
currently-advisory faculties into one mind.

**Target:** `GlobalWorkspace.run_cycle(contributions) -> WorkspaceBroadcast | None` — collect the
faculties' current signals as uniform contributions, score each by salience, select the winner,
and if salience ≥ the ignition threshold, broadcast it (blinker signal) as the dominant global
context; else no ignition (nothing dominant this cycle).
**Success test:** over the REAL cached faculty verdicts, a CRITICAL safety verdict (constitution /
tripwire / goal-integrity) wins and ignites (safety-first arbitration); with no critical signal, the
highest-conviction advisory (debate/allocator/opponent) wins if it clears the threshold; a subscriber
actually receives the broadcast.

## Parts + REAL sourcing (sourcing-oss-parts pass, agent ae295ec7 — 23 tool-uses, READMEs read)
| Part | Best OSS found | Verdict |
|------|----------------|---------|
| P1 contribution record | `blackboard-core` (MIT, 5★, LLM-supervisor-coupled); `faif/python-patterns` blackboard (teaching snippet) | **build** — a frozen dataclass; no lib fits a lightweight signal record without dragging in LLM orchestration |
| P2 salience scorer | `pyDecision`/`mcdm` (MCDA libs, MIT) — reference-only if it grows to true MCDA | **build** — spec is a 3-factor weighted product (urgency×relevance×confidence) |
| P3 competition/winner | stdlib `heapq`/`sorted`; coalition-game libs are wrong domain | **build** — `max`/`nlargest` over P2 scores |
| P4 ignition threshold | none exists (it's one `if`) | **build** — trivial glue |
| **P5 broadcast bus** | **`blinker` 1.9.0, MIT, Pallets/Flask-proven, actively maintained** | **VENDOR** — matches "one broadcast, many subscribers" exactly; lighter than PyPubSub's topic-tree |
| P6 workspace loop | `ctm-ai` (Apache-2.0, 18★, Conscious Turing Machine — truest GWT match but LLM-modality-coupled + immature); `pyClarion` (67★ but wrong theory); LIDA-py (3★ stub) | **build**, **reference ctm-ai's up-tree→workspace→down-tree structure**; nothing production-usable to vendor wholesale |

**Wholesale-vendor check:** no production-usable GWT/blackboard package exists — the integrator loop
is hand-built over the vendored `blinker` bus. This is the honest OSS-assembly verdict on the record.

## Combination prototype (step 4 — a real gotcha caught)
`blinker.signal('...').connect(receiver)` uses **weak references** by default → a receiver with no
strong ref is GC'd before `send` and never fires (verified: subscriber got `[]`). Fix: connect with
`weak=False` (or hold a strong ref). Verified `weak=False` delivers the broadcast. Documented so the
integration is reproducible.

## Component parts (`sentience/global_workspace.py` + vendored `blinker`)
- **`WorkspaceContribution`** (frozen) — `source`, `kind` (safety/opportunity/risk/info),
  `urgency`, `relevance`, `confidence` (each 0..1), `content` (human string), `is_critical`.
- **`salience_score(c)`** — weighted product `urgency^wu · relevance^wr · confidence^wc`; a critical
  safety contribution is floored to max salience (safety dominates the workspace).
- **`WorkspaceBroadcast`** (frozen) — `winner_source`, `kind`, `content`, `salience`, `ignited`,
  `coalition` (sources within an ε of the winner), `runner_up`.
- **`GlobalWorkspace`** — `run_cycle(contributions)`: score → pick winner (argmax) → ignition gate →
  `signal('global_workspace_broadcast').send(...)`; caches `latest_broadcast`; `subscribe(fn)` wraps
  `connect(weak=False)`.

## Wiring (Rule G/N)
`_maybe_run_global_workspace(now)` collects the service's REAL cached faculty verdicts (constitution,
wireheading/deceptive tripwires, goal-integrity, red-team, ethics/law, debate-risk, allocator,
opponent ledger) into contributions, runs the cycle, caches the broadcast, and appends it to a
broadcast history via a real blinker subscriber (proves the bus, not a variable). Dashboard surface
`global_workspace` shows the current dominant focus + ignition + recent broadcasts. Rule N.

## Verification
- Hermetic (Rule J): critical safety contribution wins + ignites; no-critical → top advisory wins if
  ≥ threshold, else no ignition; a `weak=False` subscriber receives the broadcast.
- Real-data (Rule F): over the real cached verdicts, run a cycle and confirm the broadcast reflects
  the true dominant signal (e.g. the goal-integrity WARNING / interpretability red-flags surface).

## Rule K (queued — honest grading)
This slice builds the INTEGRATOR (collect→compete→ignite→broadcast) + bus + a real subscriber +
surface. The **decision-consumer** (the broadcast BIASING the entry gate — e.g. a dominant safety
signal tightening sizing, a dominant high-conviction opportunity relaxing it, calibration-gated) is
the QUEUED next VIII branch. So: "integrator built + broadcasting; decision-consumer QUEUED."

## Atlas impact
Moves VIII: **global broadcast bus + limited-capacity workspace + salience/priority scorer +
ignition threshold** 🔴→🟢 (4 branches). VIII 0🟢→4🟢. Overall 41→45 / 197 (22.8%).
