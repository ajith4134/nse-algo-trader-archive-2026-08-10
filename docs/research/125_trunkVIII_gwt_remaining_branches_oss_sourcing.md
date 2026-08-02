# VIII — Remaining GWT/cognitive-architecture branches: OSS prior-art sourcing pass · research/125

Sourcing-oss-parts pass (Rule D) for the 9 GWT branches still open on top of the built integrator
(`sentience/global_workspace.py`, research/123: contribution record → salience score → single-winner
competition + epsilon-coalition → ignition threshold → `blinker` broadcast). Each branch is thin glue
over OUR OWN in-process faculty signals (no external data) — real web/GitHub/PyPI search run for all
9 parts (4 parallel sourcing agents, model sonnet, ~97 tool-uses total, READMEs read before verdicts).
No code written this pass. License recorded as info only (Rule E — personal use, not a filter).

## Summary table

| # | Part | Best real candidate(s) | Verdict |
|---|------|------------------------|---------|
| 1 | Selective attention | `asmo`/asmo_python (BSD-3, PhD-thesis attention architecture) — dead since 2016 | **build** — reference ASMO's thesis model only |
| 2 | State-dependent attention | `empyrical` (Apache-2.0, drawdown/vol metrics); homeostatic/allostatic-RL literature | **build** — empyrical feeds the state metric, no attention-modulator lib exists |
| 3 | Self-model | `metacognition-skill` (unlicensed, 12★, Experience→Perception→Self-Model loop) | **build** — reference the pattern; nothing maintained/general exists |
| 4 | Attention schema | none installable (AST papers, incl. 2025 ASAC, ship zero code) | **build** — pure reference to Graziano/Wilterson theory, no code prior art at all |
| 5 | Coalition formation | AIOps alert-correlation pattern (temporal+attribute+threshold); `river` streaming clustering (wrong weight class) | **build** — reference alert-correlation pattern; already have the epsilon-coalition seed in `global_workspace.py` |
| 6 | Workspace replay/rumination | **`cpprb`** (MIT, PyPI, standalone `PrioritizedReplayBuffer`) | **vendor the storage pattern**, build the rumination/pattern-mining pass |
| 7 | Cross-modal binding (evidence combination) | `scipy.stats.combine_pvalues` (Stouffer, weighted); `pyds` (archived/dead); `pgmpy`/`bayespy` (real but overkill) | **build**, anchored on scipy's weighted-Stouffer + a hand-rolled linear/log opinion pool |
| 8 | Higher-order monitoring (metacognition) | **`pybreaker`** (BSD, actively maintained, closed/open/half-open state machine) | **reference-the-pattern** (circuit-breaker state machine); build the metrics loop |
| 9 | Indicator scoreboard | **`river`** (`utils.Rolling`, per-source metric tracker); `trueskill`/Elo (stale but good reference) | **vendor river's rolling-metric primitive**; reference Elo/TrueSkill for long-run standing |

**Wholesale-vendor check (cognitive-architecture packages):** none of LIDA (Java-only; the one Python
claimant `mindpixel20/lida` is a 3★ single-commit repo — too immature to trust), pyClarion (67★,
"highly experimental," no attention/self-model/GWT-competition code in its README — wrong theory
surface entirely), ctm-ai (Apache-2.0, README confirms only single-winner up-tree→STM→down-tree
broadcast — no coalition grouping, no replay/consolidation, so it does not extend past what
research/123 already built), OpenCog/AtomSpace (real active hypergraph DB with generic self-query,
but no packaged self-model/attention-schema component — self-representation discussion is 2018-era
wiki design notes, not code), ACT-R python (`pyactr`, `python_actr` — real, maintained, but no
self-referential/metacognitive module in either), or Soar (BSD-2, 426★, active, 10k+ commits — README
confirms zero self-model/introspection component; Python access is a thin SWIG/`soar-sml` bridge to
the C++ core) provides a usable off-the-shelf attention-codelet, self-model, or metacognition
implementation. This is a confirmed ecosystem gap (direct README/repo fetches, not a search miss),
consistent with research/123's finding that no production GWT package exists.

## Part-by-part detail

### 1 — Selective attention
- **`asmo` / asmo_python** — https://github.com/airobots/asmo_python, `pip install asmo`, BSD-3-Clause.
  From Rony Novianto's 2014 PhD thesis *"Flexible Attention-based Cognitive Architecture for Robots"*
  (UTS) — the closest theoretical match to symbolic/architectural (non-neural) attention filtering
  found anywhere. PyPI last released v0.4 in March 2016; Snyk marks it INACTIVE (health 36/100); 16★,
  no commits in 6+ years; README gave no confirmable attention-filter module names.
- `github.com/topics/blackboard-architecture` — every current repo (9 checked) is an LLM multi-agent
  orchestration toy, 0–5★, none implement classical focus-of-control/priority-gating (BB1/Hearsay-II
  style). No usable candidate.
- stdlib `heapq`/`queue.PriorityQueue` — real, maintained, but a raw data structure, not a
  context-aware admission filter.
- **Verdict: build** — reference ASMO's thesis model for the shape; nothing installable/maintained
  implements "admit top-K of N faculty signals by context-relevance before competition."

### 2 — State-dependent attention
- Homeostatic/allostatic-RL literature (arXiv 2109.06580; eLife 2018 "Homeostatic RL"; Nature Sci Rep
  2025) describes exactly the needed pattern (an allostatic controller scheduling competing drives) —
  papers only, no GitHub reference implementation found.
- **`empyrical`** — https://github.com/quantopian/empyrical, Apache-2.0, widely used. Gives rolling
  max-drawdown/vol metrics — the raw "internal state" input, not an attention modulator itself.
- `drawdown-control` (oronimbus) — MIT, 7★, single notebook replicating an EVT/CVaR sizing paper;
  drawdown→throttle formula is a usable reference pattern for the risk-halt-proximity signal, not a
  library.
- No PyPI package for "affect-modulated attention" / "arousal-weighted priority" exists as code.
- **Verdict: build** — reuse empyrical for the raw state metrics (drawdown, loss-streak), reference the
  homeostatic-RL/allostatic-controller literature for how one scalar drive biases competing signals.

### 3 — Self-model
- **`metacognition-skill`** — https://github.com/velumkai/metacognition-skill, no install package
  (drop-in script), license unspecified, 2 commits/12★ — early-stage. Implements
  "Experience → Perception → Self-Model → Meta-Observation → Modified Lens," a strength-weighted
  perception registry + learned overrides + confidence-scored self-observations — closest conceptual
  match found to a queryable "what am I right now" object.
- `conscio` (PyPI, `pip install conscio`) — numpy+sqlite3, PEP 561 typed, but built around Claude Code
  slash-commands/skills specifically, not a general agent self-model API.
- `Orchestrator-Agent-Trust` — MIT, 4★/16 commits, IEEE-Access companion code; computes trust via
  calibration metrics (ECE/OCR/CCC) at runtime, not as a persistent stored self-state.
- `netcal`/`calibration-framework` confirmed a pure output-calibration stats library (ECE, reliability
  diagrams) — no self-state concept at all.
- **Verdict: build** — reference `metacognition-skill`'s Experience→Perception→Self-Model loop shape;
  nothing maintained/general-purpose exists.

### 4 — Attention schema
- `kathrynfarrell/attention_schemas_in_anns` — unlicensed, 2★, Jupyter research code for a multi-agent
  RL cooperation paper; needs a 5.26GB external dataset; static archive.
- `KietzmannLab/Attention-Schema-Analysis` — unlicensed, 1★, CogSci 2024 paper code in the
  Wilterson/Graziano lineage; research code, not packaged.
- ASAC (arXiv 2509.16058, 2025) — transformer+VQ-VAE AST-inspired module — **no linked GitHub repo at
  all**. The foundational Wilterson & Graziano PNAS 2021 paper also has no public code.
- **Verdict: build (pure reference)** — confirms the task's premise: AST is genuinely uncomputed in
  OSS. Reference Graziano/Wilterson theory directly; zero code prior art exists anywhere.

### 5 — Coalition formation
- Correctly rejected as wrong-domain: `bilateralshapley` (Mesa-based bilateral Shapley-value coalition
  game theory) and the broader Shapley-value/MARL-reward-reallocation literature — payoff-splitting
  among agents, not signal grouping.
- **`river`** — https://github.com/online-ml/river, BSD-3, 5.9k★, active. Online-clustering module
  (CluStream/DenStream/DBSTREAM/STREAMKMeans) is "the most complete open-source" set per survey, but
  built for unbounded continuous feature streams — heavyweight for clustering ~5 named discrete
  same-cycle signals.
- AIOps alert-correlation pattern (Keep/BigPanda/LogicMonitor docs: time-window + attribute/direction
  match + storm threshold → grouped composite) — domain knowledge, not a package, but maps closely to
  "bind co-active near-salience signals sharing direction."
- **Verdict: build** — the actual shape (group ~5 already-scored signals by epsilon-salience [already
  exists in `global_workspace.py`'s `coalition` tuple] + direction agreement) is a small grouping
  routine; reference the alert-correlation pattern rather than adopting river's streaming-clustering
  machinery.

### 6 — Workspace replay / rumination
- **`cpprb`** — https://pypi.org/project/cpprb/, `pip install cpprb`, MIT, mature, Cython-accelerated,
  standalone `ReplayBuffer`/`PrioritizedReplayBuffer` (segment-tree priority sampling) usable
  independent of any RL training loop; only NumPy required at runtime.
- `ReplayTables-andnp` — PyPI, MIT, pure-Python alternative (no C++ build dep), lighter but less mature
  (last release Sep 2023).
- Neuroscience replay/consolidation research (Sleep Replay Consolidation, GR-HMI) confirms the analogy
  is real and studied, but is continual-learning research code, not a drop-in utility.
- **Verdict: vendor the storage pattern** from `cpprb`'s `PrioritizedReplayBuffer` (store recent
  broadcasts, sample/iterate weighted by recency+salience); the "detect recurring dominant concerns"
  frequency-mining pass has no library and must be hand-written on top of the buffer.

### 7 — Cross-modal binding (evidence combination) — deepest check, per user's ask
- **`pyds`** — https://github.com/reineking/pyds, BSD-3, 145★. Real Dempster-Shafer belief-mass
  combination library — **but explicitly archived by its own owner (May 16, 2021)**, author's README
  now recommends "probabilistic alternatives with a more solid theoretical foundation." The PyPI name
  `pyds` is actually an unrelated NASA Planetary-Data-System label reader — the real library isn't
  even pip-installable by that name; would require vendoring GitHub source directly into a dead
  project.
- **`pgmpy`** — https://pgmpy.org / github.com/pgmpy/pgmpy, MIT, 3.3k★, ~3,650 commits, actively
  developed. Full Bayesian-network/causal-DAG toolkit — no lightweight "combine N confidence scores"
  primitive; would require building a BN model just to fuse a handful of scalars. Overkill for the
  shape.
- **`bayespy`** — github.com/bayespy/bayespy, MIT, 704★. Same issue: requires constructing an explicit
  variational-Bayes model; workflow overhead not worth it for ad hoc fusion.
- **`scipy.stats.combine_pvalues`** — already a near-universal dependency. Confirmed: Fisher's,
  Stouffer's (supports per-source **weights**), Tippett's, Pearson's, Mudholkar-George methods for
  merging independent evidence on one hypothesis. Genuine tested primitive, zero new dependency; needs
  a small transform layer (confidence score → z/p equivalent).
- Opinion pooling (linear/logarithmic) — no maintained Python package (`maxbiostat/opinion_pooling` is
  4★ academic scaffolding whose real implementation is an R package; `skfolio` has an `OpinionPooling`
  class but it's embedded in a full portfolio-optimization framework — wrong dependency weight). The
  formulas themselves (weighted average / weighted geometric mean of beliefs) are textbook-stable,
  ~10 lines, no non-trivial edge cases.
- Late-fusion / sensor-fusion searches surfaced only deep-learning multimodal-fusion frameworks
  (TorchMultimodal, Fusilli, OMML) and IMU/Kalman sensor-fusion libs (`imufusion`) — wrong domain for
  abstract scalar confidence scores.
- **Verdict: build**, anchored on `scipy.stats.combine_pvalues`'s weighted-Stouffer method plus a
  hand-rolled linear/logarithmic opinion pool. The one purpose-built library (`pyds`) is dead; the two
  maintained probabilistic frameworks (`pgmpy`, `bayespy`) are real but structurally overkill; no
  maintained opinion-pooling package exists. scipy is already in the dependency tree and its weighted
  Stouffer method is a legitimate tested combiner; opinion pooling is simple/well-established enough
  to implement directly rather than depend on a fragile or abandoned package.

### 8 — Higher-order monitoring (metacognition)
- No generic "metacognition library" exists for GOFAI-style architectures — search returned only
  LLM-introspection research papers, not installable packages.
- **`pybreaker`** — https://github.com/danielfm/pybreaker, PyPI, BSD, confirmed v1.4.1 released
  Sept 21 2025 — actively maintained. Closed/open/half-open circuit-breaker state machine, opens after
  N consecutive failures, auto-recovery attempt after a reset timeout, event listeners on every state
  transition, decorator/context-manager/direct-call APIs, thread-safe, optional Redis backing.
- `watchdog` (filesystem-event monitoring) — false lead despite the name. `healthcheck-python` exists
  but is thin, scoped to multiprocessing health aggregation.
- **Verdict: reference-the-pattern** — pybreaker's closed/open/half-open state machine + listener hooks
  is exactly the right shape for "is the workspace igniting too often/too rarely, back off and
  recover," but it protects a single call site, not a multi-faculty statistics loop, so borrow the
  design, build the metrics loop itself.

### 9 — Indicator scoreboard
- **`river`** — confirmed `metric.update(y_true, y_pred)` API usable standalone per named source, plus
  `utils.Rolling` for sliding-window metrics — a legitimate lightweight per-faculty rolling-score
  tracker without adopting river's full online-learning pipeline.
- `trueskill` (github.com/sublee/trueskill, 800★/122 forks) and siblings (`elote`, `openskill.py`,
  PyPI `elo`) implement Elo/TrueSkill/Glicko rating updates from win/loss/draw outcomes; `trueskill`
  itself shows age (deprecated Travis CI, 28 open issues) — mature but stale.
  Credit-scorecard libraries (Scorecard-Bundle, skorecard) were checked and rejected — WOE/IV binning
  for classification risk scoring, wrong shape.
- **Verdict: vendor** river's rolling-metric primitive (`utils.Rolling` + `metric.update`) for live
  per-faculty reliability numbers; **reference** Elo/TrueSkill rating math for long-run faculty
  standing (trading faculties naturally "win/lose" over time) rather than depending on the stale rating
  packages.

## Overall recommendation
Only **two** of the nine parts get real vendor value: **part 6** (workspace replay) should vendor
`cpprb`'s `PrioritizedReplayBuffer` storage primitive, and **part 9** (indicator scoreboard) should
vendor `river`'s `utils.Rolling`/`metric.update` per-faculty tracker — both are maintained, tested,
lightweight, and fit the shape without dragging in a training loop. **Part 8** should reference (not
depend on) `pybreaker`'s circuit-breaker state machine for the health monitor's throttle/recover logic.
**Part 7** is the one part with a real purpose-built library (`pyds`) — but it is dead/archived, so
build on `scipy.stats.combine_pvalues` (weighted Stouffer, already a transitive dependency) plus a
hand-rolled opinion pool instead of vendoring an abandoned Dempster-Shafer package or dragging in
`pgmpy`/`bayespy`'s full graphical-model machinery. **Parts 1–5** (selective attention, state-dependent
attention, self-model, attention schema, coalition formation) have no installable, maintained OSS at
all — every hit was either dead (ASMO, pyds's spirit), sub-10-star single-author research code, or
theoretical papers with zero linked code (attention schema is the starkest case: even a 2025 paper
shipped none) — build these from scratch, informed by the cited theory/pattern references above. No
complete cognitive-architecture package (LIDA, pyClarion, ctm-ai, OpenCog/AtomSpace, ACT-R python,
Soar) has a usable off-the-shelf attention-codelet, self-model, or metacognition implementation to
vendor wholesale — confirmed by direct README/repo fetches, matching research/123's earlier finding
that no production GWT package exists.

## Rule K (queued — honest grading)
This is a sourcing pass only (no code). Building parts 1–9 into `sentience/global_workspace.py` (or
sibling modules) against these findings is the QUEUED next VIII implementation slice — track in
`docs/BACKLOG.md` under Trunk VIII when that slice starts.
