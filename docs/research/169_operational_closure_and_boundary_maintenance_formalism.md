# 169 · Operational closure & boundary maintenance — a computable formalism

**Trunk:** X · AUTOPOIESIS / SELF-PRODUCTION (`docs/AI_CONCEPT_TREE_STATUS.md` lines 189-194;
`docs/research/31_autonomous_organism_concept_tree.md`). Targets the two still-🔴 branches:
`operational closure` and `boundary maintenance`, plus feeds `component self-maintenance` and
`component lifecycle manager`.

**Method:** real web research (WebSearch + WebFetch across arXiv, PMC, HAL, Wikipedia, MDPI,
Frontiers, ResearchGate mirrors, GitHub, networkx docs) — no claim below is from memory alone. Every
claim is tagged with a source grade (A = primary/peer-reviewed fetched directly, B = reputable
secondary confirmed to represent a primary source, C = search-snippet-level, flagged as such). A
`§6 Could-not-verify` section lists everything a fetch failed to render in full.

---

## 1. Autopoiesis, formalized enough to compute

### 1.1 Maturana & Varela's original definition (A — quoted from *Autopoiesis and Cognition*, 1972/1980, via Wikipedia's sourced quotation)

> "An autopoietic machine is a machine organized (defined as a unity) as a network of processes of
> production (transformation and destruction) of components which: (i) through their interactions and
> transformations continuously regenerate and realize the network of processes (relations) that
> produced them; and (ii) constitute it (the machine) as a concrete unity in space in which they (the
> components) exist by specifying the topological domain of its realization as such a network."

Two computable obligations fall out of this: **(i) regeneration** — every component's production
network must, taken as a whole, keep re-producing itself (closure/circularity), and **(ii)
topological unity** — the network specifies its own boundary (this is boundary maintenance, §3).

Source: [Autopoiesis — Wikipedia](https://en.wikipedia.org/wiki/Autopoiesis) (B, secondary but
directly quotes the 1972 primary text with citation).

### 1.2 Varela's organizational/operational closure and the "Closure Thesis" (B)

Varela ties autonomy to closure directly: **"every autonomous system is operationally closed"** —
i.e. the system's own processes reference only its own components and each other, never an external
"designer" process. Autopoiesis is the special case of operational closure realized at the
chemical/molecular level with **material** production relations between constituents (as opposed to,
e.g., a social system's closure over communications, per Luhmann/Bednarz's 1988 application of the
same idea to social systems).

Source: [Autopoiesis — Wikipedia](https://en.wikipedia.org/wiki/Autopoiesis); cross-checked against
[Bednarz 1988, "Autopoiesis: The organizational closure of social systems", *Systems Research*](https://onlinelibrary.wiley.com/doi/abs/10.1002/sres.3850050107).

### 1.3 Luisi's review and reappraisal (B — citation confirmed, full text not fetched)

Luisi, P.L. (2003). *"Autopoiesis: a review and reappraisal."* **Naturwissenschaften** 90, 49–59.
DOI confirmed via search: `10.1007/s00114-002-0389-9`
([Springer record](https://link.springer.com/article/10.1007/s00114-002-0389-9)). Reviews Maturana &
Varela's theory from decades of direct contact with Varela and connects it to *chemical* autopoiesis
(experimentally realizable minimal cells) — the bridge from the philosophical definition (§1.1-1.2)
toward the operational one (§1.5). Full text was not fetchable (paywalled); cited at abstract-level
only — see §6.

### 1.4 Montévil & Mossio: "closure of constraints" (A/B mixed — abstract + secondary summaries fetched; two PDF mirrors of the full text rendered as binary garbage, see §6)

**Montévil, M. & Mossio, M. (2015). "Biological organisation as closure of constraints."** *Journal
of Theoretical Biology* 372, 179–191. DOI `10.1016/j.jtbi.2015.02.029`.
([HAL open-access record](https://hal.science/hal-01192916v1)).

The paper distinguishes two causal regimes:
- **Processes** — changes occurring under non-equilibrium, open thermodynamic conditions (the
  "doing" of the system).
- **Constraints** — entities that act on processes (they causally shape/channel a process) while
  themselves being approximately **conserved** at the relevant timescale (they are the "structure").

**Closure criterion:** biological organization is a *closure of constraints* when the constraints
exhibit **mutual dependence** — each constraint both **depends on** (is produced/maintained by) and
**contributes to maintaining** at least one other constraint in the set, such that the network as a
whole is self-sustaining. This is explicitly offered as **"an operational tool for marking the
boundaries between interacting biological systems"** — i.e. the same formalism is meant to answer
both operational closure (§this) and boundary identity (§3) at once.

Follow-ups (found via `montevil.org/tags/closure`, B-grade index page, links verified):
- Mossio, Montévil et al. (2016). *"Theoretical principles for biology: organization."* Prog. Biophys.
  Mol. Biol. DOI `10.1016/j.pbiomolbio.2016.07.005`.
- Montévil & Mossio et al. (2020). *"The identity of organisms in scientific practice."* Front.
  Physiol. DOI `10.3389/fphys.2020.00611`.

**What this gives us computationally:** a dependency relation "constraint Ci is maintained by
constraint Cj" over a finite set of named constraints, and a closure test = **is the maintenance
relation such that no constraint's maintenance need "leaks" outside the set** (mutual/cyclic
dependency, not a linear chain terminating outside). This is qualitatively identical to Chemical
Organization Theory's "closed set" (§1.5) but stated at a more abstract, non-chemical level — which is
exactly why it is the right frame for a software organism (our "constraints" are engines/modules, not
molecules). Montévil-Mossio do **not**, in the fetchable material, give a graph-theoretic algorithm —
COT is the one that does (next section).

### 1.5 Chemical Organization Theory (Dittrich & Speroni di Fenizio) — the directly implementable formalism

**Dittrich, P. & Speroni di Fenizio, P. (2007). "Chemical Organisation Theory."** *Bulletin of
Mathematical Biology* 69, 1199–1231. DOI `10.1007/s11538-006-9130-8`. Preprint:
[arXiv:q-bio/0501016](https://arxiv.org/abs/q-bio/0501016) (A — fetched via
[PMC2712341](https://pmc.ncbi.nlm.nih.gov/articles/PMC2712341/), which quotes the formalism verbatim
while applying it to model-checking).

**Formalism.** A reaction network is a pair `(M, R)`: a finite set of **species** `M = {m1..mn}` and a
finite set of **reaction rules** `R`, each `ρ ∈ R` of the form `LHS(ρ) → RHS(ρ)` (multisets of
species). For a subset `A ⊆ M`, `R_A ⊆ R` is the set of reactions triggerable using only species in
`A` (`LHS(ρ) ⊆ A`). `N_A` is the stoichiometric matrix restricted to `A` and `R_A`.

- **Closed set (A):** `A` is closed **iff** for every reaction `ρ ∈ R_A`, `RHS(ρ) ⊆ A` — i.e. no
  reaction triggerable from inside `A` ever produces a species outside `A`. *(Quoted, PMC2712341: "for
  all reaction rules ρ∈ℛ_A, RHS(ρ)∈A.")*
- **Semi-self-maintaining (B, via secondary synthesis of the primary definition — see §6):** `A` is
  semi-self-maintaining iff every species **consumed** by some reaction in `R_A` is also **produced**
  by some reaction in `R_A` — a *qualitative* (existence-only) closure of the consumption side. It is
  strictly weaker than, and a necessary precondition for, self-maintenance, and is cheap to check
  (pure set membership, no linear program).
- **Self-maintaining (A):** `A` is self-maintaining **iff** there exists a strictly positive flux
  vector `v' ∈ ℝ^{|R_A|}_{>0}` such that `N_A · v' ≥ 0` — every species' net production rate under
  *some* positive reaction-rate assignment is non-negative. This is the *quantitative* version: it's
  not enough that a producer exists (semi-self-maintenance); production must be able to match or
  exceed consumption. Checking this is a linear-feasibility problem (solvable by LP/Farkas' lemma).
- **Organization:** `A` is an **organization** iff it is both **closed** and **self-maintaining**.
  `A` is **reactive** if every species in it participates in at least one reaction; an **elementary
  organization** is a reactive organization that cannot be built as a union of smaller reactive
  organizations. Under the **Feinberg condition** ("each reaction has non-zero flux iff all its
  reactants have positive concentration"), *every steady state or growth state of the network
  corresponds to some organization* — i.e. organizations are exactly the dynamically-stable
  candidate configurations of the whole system. Algorithm for enumerating all organizations
  (producing the *organization lattice*): referenced to Centler, Kaleta, di Fenizio & Dittrich
  (2008) but not itself re-derived in the fetched text (see §6).

**Non-chemical applications (A — MDPI/Frontiers 2026 fetched directly):** COT has been applied,
unmodified in its abstract form, to a dairy-farm resource-cycle model (Veloz et al. 2022), to
ecosystem models (plants/fungi/insects/beavers), and to urban-infrastructure network analysis — i.e.
practitioners already treat "species" as an abstract stand-in for *any* maintained resource/component,
not literal molecules. This directly licenses treating our engines/data-feeds/state-stores as `M` and
"X's health-check reads/writes Y" as the reaction relation.
Sources: [MDPI 12(4):111, "Chemical Organization Theory as a General Modeling Framework for
Self-Sustaining Systems"](https://www.mdpi.com/2079-8954/12/4/111) (fetch of the abstract page was
blocked 403; content below is from the companion Frontiers article which cites and restates it) and
[Frontiers 2026, "Chemical organizations as a conceptual tool: from synthetic biology to
interdisciplinary systems and back"](https://www.frontiersin.org/journals/bioengineering-and-biotechnology/articles/10.3389/fbioe.2026.1801128/full)
(A — fetched directly).

**pyCOT** (`pycot.utem.cl`) is the reference computational platform: an interactive web app that
computes organizational hierarchies and runs perturbation/reorganization simulations. **We could not
find a GitHub repository or PyPI package for it** — see §5/§6; we borrow the *definitions*, not the
code.

### 1.6 Computational / ALife operationalizations of autopoiesis

- **Varela, Maturana & Uribe (1974).** *"Autopoiesis: the organization of living systems, its
  characterization and a model."* *BioSystems* 5, 187–196
  ([ScienceDirect record](https://www.sciencedirect.com/science/article/abs/pii/0303264774900318)).
  The first computational instantiation: a 2-D cellular-automaton "artificial chemistry" (particle
  types + local reaction/diffusion rules; named variants **Protobio** and **Bittorio**) built to show
  a membrane-bounded, self-repairing unity emerging from simple local rules — i.e. the first
  existence proof that closure + boundary can arise from a rule-based dependency network, not just be
  asserted philosophically. (B — abstract/description confirmed via multiple search results including
  a 2022 retrospective at [stream.syscoi.com](https://stream.syscoi.com/2022/04/28/autopoiesis-the-organization-of-living-systems-its-characterization-and-a-model-varela-maturana-uribe-1974/).)
- **Ono & Ikegami (1999-2001), "SCL model" / Lattice Artificial Chemistry.** A coarse-grained
  artificial-chemistry model of a self-replicating, self-maintaining protocell; later work (Suzuki &
  Ikegami) added membrane maintenance under motion. Confirms self-maintenance and reproduction can be
  decoupled and separately engineered/tested — relevant because our engine should check
  self-maintenance (closure) **independent of** growth/reproduction concerns (which this project's
  AUTOPOIESIS trunk does not need). (B — via search synthesis of
  [30 Years of Computational Autopoiesis: A Review](https://www.researchgate.net/publication/242657349_30_Years_of_Computational_Autopoiesis_A_Review).)
- **Minary (2026), arXiv:2601.04501, "The Minary Primitive of Computational Autopoiesis"** (A —
  fetched). A recent, purely matrix-algebraic (not graph-based) demonstration that a learning signal
  can be made provably independent of external input ("operational closure" as *algebraic
  cancellation* of a perturbation term, proved as a convergence theorem). Cites Maturana & Varela but
  **not** COT or Montévil/Mossio. Interesting as a second, independent notion of "closure" (closure of
  an *update rule* against its inputs) but **not directly reusable** here — our system's "components"
  are heterogeneous software engines, not a single matrix update; the graph/COT formalism (§1.5, §2)
  is the fit, this is noted for completeness and rejected as an implementation basis.

**Bottom line for §7:** Chemical Organization Theory (§1.5) is the only one of these giving exact,
checkable, finite conditions (`closed`, `self-maintaining`, `organization`) that transfer without
metaphor-strain onto a directed dependency graph. Montévil-Mossio (§1.4) supplies the right
vocabulary ("constraint", "mutual dependence", boundary-as-closure) for *why* this is the correct
criterion for an autonomous system, not just an arbitrary graph property.

---

## 2. Graph algorithms that implement the criteria

### 2.1 The substrate

Define a directed graph `G_maintains = (V, E)` where `V` = registered components (engines, data
adapters, state stores, monitors — anything with a name in `docs/SYSTEM_MAP.md`) and an edge `u → v`
means **"u is maintained/produced by v"** (v keeps u alive/current/correct — e.g. `v` is the
write-path, health-check, or restart-supervisor for `u`). This is **not** the same as the Python
import graph: an import edge means "u *uses* v's code," which is neither necessary nor sufficient for
"v maintains u." COT's species are named, explicit entities (§1.5) — so `G_maintains` must be a
**curated overlay**, not something inferred purely from `ast.parse` (the AST import graph, already
producible from the repo — `networkx` is already installed transitively, confirmed at
`.venv/lib/python3.12/site-packages/networkx 3.6.1`, though not yet a declared direct dependency in
`pyproject.toml` — is the right substrate for computing *both* graphs and is a small, pure-Python
library well matched to this repo's graph size, hundreds of nodes, not millions; see §5).

### 2.2 SCC / condensation → closure candidates

Networkx confirmed available in-repo: `strongly_connected_components`, `condensation`,
`kosaraju_strongly_connected_components`, `is_strongly_connected`, `number_strongly_connected_components`.
**Collapsing each SCC of `G_maintains` into one node always yields a DAG** (the condensation) — this
is a mathematical necessity of the SCC definition, confirmed via
[PuppyGraph's SCC guide](https://www.puppygraph.com/blog/strongly-connected-components) and
[CMU 15-451 lecture notes](https://www.cs.cmu.edu/~15451-f20/LectureNotes/dfs-scc.pdf) (B, standard
CS references — this is textbook graph theory, not disputed).

**Mapping to COT:** a non-trivial SCC (size ≥ 2, or a size-1 node with a self-loop) is a **candidate
closed, mutually-maintaining cluster** — the graph-theoretic image of a COT "organization" or a
Montévil-Mossio "closure of constraints." A **source node of the condensation DAG** (an SCC with
in-degree 0) is, by construction, maintained by nothing inside the graph — it is either a legitimate
**EXOGENOUS boundary input** (declared: broker API, NSE feed, OS clock, the human operator) or a
**closure violation** (an internal component nobody maintains).

### 2.3 Structural definition of a closure violation

A **closure violation** = any node `v ∈ V` that is (a) not tagged `EXOGENOUS`, and (b) either has
in-degree 0 in `G_maintains`, or belongs to a condensation-DAG source SCC that is not itself
self-looping/cyclic. In COT terms: `{v}` (or its SCC) fails **self-maintenance** — no active
maintainer produces it. This is the audit target: walk `G_maintains`, compute the condensation,
report every non-exogenous source SCC.

### 2.4 Feedback vertex set (FVS) → the load-bearing cyclic core

A **feedback vertex set** is a minimum set of nodes whose removal makes the graph acyclic — NP-hard
in general (`O(1.7548^n)` exact and various FPT/kernelization results for practical sizes; confirmed
via [PACE 2022 solver description](https://arxiv.org/pdf/2301.11927) and
[Iterative reduction to vertex cover](https://drops.dagstuhl.de/storage/00lipics/lipics-vol265-sea2023/LIPIcs.SEA.2023.10/LIPIcs.SEA.2023.10.pdf)).
The **complement** reading is what matters for us: **the cycles an FVS breaks ARE the maintenance
loops COT calls organizations.** Computing an (approximate — repo-scale graphs of a few hundred nodes
make even exact FVS tractable) FVS identifies exactly which nodes participate in closure loops at
all; a component in zero cycles and with in-degree > 0 only from acyclic chains is "maintained" but
not itself *closed* — a distinction worth surfacing (linear maintenance chains are more fragile than
cyclic mutual-maintenance).

### 2.5 Articulation points & bridges → single points of failure inside the closure structure

`networkx.articulation_points`, `networkx.bridges`, `networkx.has_bridges`, `networkx.local_bridges`
are all present. An articulation point in the **undirected projection** of `G_maintains` is a
component whose removal disconnects the maintenance structure — i.e. a maintenance chain with **no
redundancy**. Even inside a technically-closed SCC, an articulation point marks a fragile link (one
failure breaks the loop). Report articulation-point status per node as a secondary fragility signal,
distinct from the boolean closure-violation flag.

### 2.6 Criticality ranking

Combine two complementary signals, both directly supported by real prior art on software/package
dependency criticality:

- **Reverse-PageRank** — PageRank computed on the **reversed** edges of `G_maintains` (`v → u`
  instead of `u → v`). A node with high reverse-PageRank is one whose failure would transitively
  propagate to many dependents — confirmed methodology: *"To compute the importance of a node, PageRank
  can be computed in the graph where the directed edges are reversed... A critical node is a node with
  a high PageRank and Reverse PageRank simultaneously"* — used in package-ecosystem criticality
  research; see
  [Kikas, Gousios et al., "Structure and Evolution of Package Dependency Networks"](https://gousios.org/pub/ecosystems-evolution.pdf)
  and the 2026 PyPI ecosystem-impact study
  [arXiv:2605.06164](https://arxiv.org/pdf/2605.06164) (B — search-synthesis of both, methodology
  description directly quoted from search output, not independently re-derived from the PDFs).
- **Betweenness centrality** (`networkx.betweenness_centrality`) — fraction of shortest maintenance
  paths passing through a node; flags brokers/bottlenecks even when not formally an articulation
  point (e.g. technically-redundant but practically load-bearing paths).

**Criticality score** = `is_articulation_point (boolean gate) → rank by reverse_pagerank *
betweenness_centrality` among non-articulation nodes too, so the ranking is a total order usable for a
dashboard "vital organs" panel.

---

## 3. Boundary maintenance / self vs non-self

### 3.1 Negative selection (Forrest et al., 1994) — mechanism and honestly-reported failure mode

**Forrest, S., Perelson, A.S., Allen, L., Cherukuri, R. (1994). "Self-Nonself Discrimination in a
Computer."** *Proc. 1994 IEEE Symposium on Security and Privacy*, 202–212
([ACM record](https://dl.acm.org/doi/10.5555/882490.884218)). Mechanism (B — via
[Wikipedia: Artificial immune system](https://en.wikipedia.org/wiki/Artificial_immune_system), which
itself cites the primary literature): generate random candidate "detectors"; discard any that match a
known-self pattern (mirroring thymic T-cell negative selection); the survivors form a detector set
that fires only on **non-self** (novel/anomalous) patterns, without ever having to enumerate non-self
directly.

**Known, serious criticism (triangulated across 3 independent sources — A/B):**
- *Scaling / curse of dimensionality*: "NS algorithms operating in high-dimensional space suffer from
  the ubiquitous 'curse of dimensionality', requiring ever more general detectors to cover the space
  effectively" (Stibor et al., cited via
  [arXiv:2105.06109, "Negative Selection Algorithm Research and Applications in the last decade: A
  Review"](https://arxiv.org/abs/2105.06109)).
- The **"hole problem"**: detector generation in high dimensions leaves uncovered gaps ("holes") in
  non-self space that never get a detector, because random generation concentrates in unlikely regions
  — confirmed independently via a 2025 network-intrusion-detection paper
  ([Scientific Reports, 2025](https://www.nature.com/articles/s41598-025-20516-6)) and the review
  above.
- Detector-count blowup: *"too many detectors and high time complexity are major problems of existing
  negative selection algorithms, which limit the practical applications"* — same review, corroborated
  in the earlier ScienceDirect survey
  ([Negative selection in anomaly detection — A survey](https://www.sciencedirect.com/science/article/abs/pii/S1574013723000242), abstract-level only, paywalled body).

### 3.2 Danger theory / Dendritic Cell Algorithm (Greensmith & Aickelin)

Mechanism (B — via Wikipedia's Artificial Immune System page; **the primary DCA arXiv PDFs
(1006.5008, 1001.2411, etc.) could not be rendered as text — see §6**, so this is reported at
secondary-source confidence only): danger theory reframes immune activation as responding to **danger
signals** from damaged/stressed tissue rather than to a fixed self/non-self boundary. The Dendritic
Cell Algorithm fuses multiple signal streams (commonly described in the literature as PAMP/danger/safe
signal categories) per antigen-context window and classifies the aggregate context as
"mature"(anomalous) vs "semi-mature"(normal) via a population of artificial dendritic cells; a
**Mature Context Antigen Value (MCAV)** scores how anomalous a given antigen is across the population.
Wikipedia itself flags that "it remains debated whether \[danger theory] provides substantially novel
abstractions beyond existing approaches" — i.e. even within the AIS community this is contested, not
settled engineering.

### 3.3 Clonal selection & immune network (B, brief — for completeness only)

Clonal selection (affinity maturation via selection + hypermutation, "parallel hill-climbing... without
recombination") and immune-network theory (idiotypic antibody-antibody graphs, Jerne) are optimization/
clustering metaphors, not self/non-self boundary mechanisms — noted for completeness, not relevant to
boundary maintenance.
Source: [Wikipedia: Artificial immune system](https://en.wikipedia.org/wiki/Artificial_immune_system).

### 3.4 Verdict: mostly cargo-cult for this system — be honest about it

Negative selection's core failure mode (curse of dimensionality, detector-count blowup, the hole
problem) is a **direct, well-documented mismatch** for a real-time intraday trading system: our
"non-self" space is not an abstractly huge shape-space needing randomized detector coverage — it's a
small, enumerable, well-typed set of concrete sources (≤215 option underlyings, ~2,000 cash names,
~5 broker/data adapters, one OS clock). Enumerating and validating **known-self** directly (allowlist,
schema, provenance) is strictly cheaper, more auditable, and has none of NSA's coverage-gap risk.
DCA/danger-theory is contested even within its own literature and adds a population-based fuzzy signal
-fusion layer with no accuracy advantage demonstrated over direct multi-signal fusion (which
`market_data_integrity_defense` and `causal_leakage_firewall` already do, deterministically, per bar).
**Recommendation: do not implement negative selection or DCA.** They are namechecked here (per the
task) and rejected on documented technical grounds, not dismissed a priori.

### 3.5 What is genuinely worth building (the pragmatic engineering equivalent)

- **Membership registry ("self")**: an explicit allowlist of `{component_id, data_source_id,
  adapter_version}` tuples — this is literally the `V` vertex set of `G_maintains` (§2.1) plus a
  parallel registry for external data producers. This *is* the computable form of "the organism knows
  what is a member of itself" — no learning, no negative-space sampling, just a maintained roster,
  exactly as COT's species set `M` is an explicit finite list, not something inferred by scanning
  "not-M."
- **Provenance attestation** (borrowing SLSA/in-toto's core idea, not the tooling — SLSA/in-toto are
  build-supply-chain frameworks for software artifacts, not market-data streams, so the library isn't
  reusable, but the pattern is): every inbound datum should carry `{source_id, adapter_version,
  ingestion_timestamp}`, checked against the membership registry before it reaches a decision path.
  ([SLSA overview](https://slsa.dev/blog/2023/05/in-toto-and-slsa),
  [in-toto attestation framework](https://mikael.barbero.tech/blog/post/2023-12-28-slsa-and-in-toto/) — B, general pattern reference.)
- **Schema/contract validation** at every DI seam: `pydantic` (already installed transitively in this
  repo's `.venv`, confirmed `pydantic 2.13.4`) is the correct, already-present tool for this — no new
  dependency needed.
- **Drift/anomaly detection on the boundary stream**: `river`'s streaming drift detectors (ADWIN, DDM,
  Page-Hinkley) are the right *class* of tool — and this project **already uses Page-Hinkley** for a
  different purpose (`predictive_core/surprise_monitor`, per `docs/AI_CONCEPT_TREE_STATUS.md` line
  185: *"surprise/free-energy monitor — per-mechanism cross-entropy + Page-Hinkley spike"*), so adding
  a second Page-Hinkley/ADWIN instance scoped to per-source data-boundary drift is a consistent reuse
  of an already-adopted statistical test, not a new algorithmic risk.
  ([river GitHub](https://github.com/online-ml/river) — BSD-3-Clause, 5.9k★, active, Python 3.11+,
  `learn_one`/`predict_one` streaming API — fetched directly, A.)
- **Existing organs already ARE two of the three boundary checks** — read directly from source in this
  repo:
  - `src/nse_algo_trader/paper_trading/causal_leakage_firewall.py` — **temporal** boundary (no
    future-timestamped datum may be observed; monotonic virtual clock).
  - `src/nse_algo_trader/conscience/market_data_integrity_defense.py` — **value-integrity** boundary
    (positive prices, OHLC consistency, single-bar move limit, timestamp monotonicity/duplication).
  - **Missing piece**: **component-identity** boundary — is this record's *source* itself a registered
    member of "self" at all (allowlist + provenance + drift), independent of whether its *values* look
    plausible. This is the gap this research is meant to close (see §7).

---

## 4. Homeostasis, formally

### 4.1 Ashby's ultrastability and the Homeostat (B — triangulated across 3 search-derived sources)

Ashby's **Homeostat** (a four-unit electromechanical device, needle-in-conducting-fluid actuators,
cross-coupled) demonstrated **ultrastability**: a system with **two nested feedback loops** — a fast
loop that absorbs ordinary perturbations within a fixed parameterization, and a slow loop that
**randomly re-parameterizes** the fast loop's own control law whenever a monitored **essential
variable** exits its allowed range (the **viability zone**, defined by lower/upper bounds on each
essential variable). Essential variables must be **directly exposed** to environmental input — routing
them through intermediaries risks saturation/unresponsiveness.
Sources: [Battle, "A Mobile Homeostat with Three Degrees of Freedom"](https://cdn.ima.org.uk/wp/wp-content/uploads/2017/12/Battle-A-Mobile-Homeostat-with-Three-Degrees-of-Freedom.pdf);
[ResearchGate ultrastability diagram description](https://www.researchgate.net/figure/Diagram-illustrating-Ashbys-principle-of-ultrastability-as-a-double-feedback-loop-in-a_fig2_277596924).

### 4.2 Viability theory (Aubin) — the modern, set-based generalization

The **viability kernel** of a control system under a constraint set `K`: the set of all states
`x ∈ K` from which **some** admissible control trajectory stays inside `K` for all future time. It is
provably closed under general conditions, and Aubin's **Frankowska characterization** expresses it as
the intersection of backward-invariance and forward-viability. A **viable regulation map** restricts
the controller's admissible actions, at each state, to only those that keep the trajectory inside the
kernel — on the boundary of the kernel this can be a *small* admissible set, in the interior it can be
the full control range.
Sources: [ESAIM:COCV, "Viability Kernels and Control Sets"](https://www.esaim-cocv.org/articles/cocv/pdf/2000/01/cocvVol5-7.pdf);
[collectionscanada.gc.ca thesis, "Viability Kernels for Nonlinear Systems"](https://www.collectionscanada.gc.ca/obj/thesescanada/vol2/002/MR45014.PDF).
A concrete engineering precedent exists — [arXiv:1701.08735, "Real-Time Control for Autonomous Racing
Based on Viability Theory"](https://arxiv.org/pdf/1701.08735) — confirming viability-kernel-based
control has been deployed in a real-time, safety-critical control loop; **full text of this specific
paper could not be rendered (binary PDF), so its detail is not claimed beyond the title/topic — flagged
in §6.**

### 4.3 Ashby/viability-theory vs PID — is either genuinely better?

**Yes, and the difference is structural, not incremental.** A PID loop regulates **one scalar**
against **one setpoint** via an error signal — it has no concept of a *feasible region* or of
switching its own control law. Ashby's ultrastability and Aubin's viability kernel both regulate a
**vector of essential variables jointly against a feasible SET** (the viability zone / kernel), and
critically both provide a principled answer to **"what do you do when regulation is about to fail"**:
Ashby re-parameterizes the fast loop; viability theory's regulation map explicitly narrows to only the
subset of controls that keep the trajectory inside the kernel, refusing actions that would exit it.
Neither is "a PID with extra math" — they are a genuinely different computational object (a
**set-membership problem plus a second-order adaptation policy**, not a single error-driven
control law), which matters for a trading system: the "essential variables" (max drawdown, order rate,
capital deployed, position concentration) are jointly constrained, not independently regulatable, and
the interesting failure mode is precisely "the current control policy no longer keeps the joint state
viable" — which a scalar PID loop per-variable cannot detect or respond to structurally.

---

## 5. OSS sourcing verdicts (every rejection surfaced, per Rule O)

| Candidate | Verdict | Reason |
|---|---|---|
| **networkx** (3.6.1, already installed transitively; confirmed API: `strongly_connected_components`, `condensation`, `articulation_points`, `bridges`, `has_bridges`, `betweenness_centrality`, `pagerank`) | **INTEGRATE** | Pure-Python, zero new install (already present transitively — needs promoting to a direct `pyproject.toml` dependency), and this repo's dependency graph is hundreds of nodes, nowhere near the scale (100k+) where networkx's ~40-250x slower-than-graph-tool performance would matter. Confirmed via [graph-tool performance page](https://graph-tool.skewed.de/performance.html) and an [igraph-vs-networkx benchmark discussion](https://www.timlrx.com/blog/benchmark-of-popular-graph-network-packages/). |
| **igraph** | **REJECT (for now)** | Faster than networkx at scale, but adds a compiled-C dependency for a graph size where the speed difference is unmeasurable (single-digit milliseconds either way). Revisit only if the maintenance graph ever exceeds ~10⁴-10⁵ nodes. |
| **graph-tool** | **REJECT** | Fastest of the three, but has a "steeper learning curve and setup complexity" and heavy compile-time cost ([graph-tool performance page](https://graph-tool.skewed.de/performance.html)) — unjustified for our node count; would violate "acquire what's needed" (Rule I) in the other direction — acquiring more than needed. |
| **pyCOT** (`pycot.utem.cl`) | **REJECT as a dependency** | It is a hosted interactive web application; **no GitHub repository or PyPI package could be found** despite a dedicated search (see §6). We borrow its *definitions* (already public via the peer-reviewed papers, §1.5) and re-implement `closed`/`self-maintaining`/`organization` as small predicate functions over a networkx graph — a few dozen lines, not worth vendoring a web app for. |
| **river** (BSD-3, 5.9k★, `online-ml/river`) | **INTEGRATE** | Real streaming API (`learn_one`/`predict_one`), includes ADWIN/DDM/Page-Hinkley drift detectors, and this project already trusts Page-Hinkley for `predictive_core/surprise_monitor` — extending the same statistical test to the data-provenance boundary (§3.5) is consistent, not a new algorithmic bet. Needs adding to `pyproject.toml` (not currently installed). |
| **pyod** (BSD-2, 9.9k★, `yzhao062/pyod`, 61+ detectors) | **CONDITIONAL REJECT for v1 / queue for later (Rule K)** | Confirmed **primarily batch/transductive** — "most detectors operate on static data; graph and time-series methods are transductive (train-only)" — a poor fit for a live per-bar boundary gate, and it duplicates domain logic `market_data_integrity_defense` already encodes deterministically (OHLC consistency, move limits) with none of pyod's generic-model false-positive risk. Worth revisiting later as a **cross-sectional** anomaly layer (flagging one symbol behaving unlike its peer universe) — logged as a named backlog item, not built now. |
| **Any negative-selection / DCA Python package** | **REJECT** | No actively-maintained, production-track-record package was found in this search, and §3.4 gives the technical reasons (curse of dimensionality, hole problem, contested value of danger theory) to not build this ourselves either. |

---

## 6. Could-not-verify (explicit)

- **Full text of Montévil & Mossio (2015), JTB.** Two independent PDF mirrors
  (`hal.science/hal-01192916v1/file/...pdf` and `gbragafibra.github.io/papers/...pdf`) both rendered as
  unparseable binary/stream data through WebFetch. Relied on the abstract, the `montevil.org/tags/closure`
  secondary index page, and cross-citation from the 2016/2020 follow-up abstracts. The exact
  mathematical notation for "constraint dependency" (if any beyond prose) is **not verified**.
- **"Semi-self-maintaining" exact original wording.** Obtained via a search-engine synthesis of
  multiple secondary snippets, not a direct quoted sentence from the Dittrich & Speroni di Fenizio
  primary text (unlike `closed`/`self-maintaining`/`organization`, which were directly quoted via
  PMC2712341). The *content* triangulates consistently across ≥3 independent sources, so confidence is
  high, but it is graded B, not A.
- **Full text of Greensmith & Aickelin's Dendritic Cell Algorithm papers** (arXiv:1006.5008,
  1001.2411, 1006.1512, 1004.3196). All attempted fetches (direct and via `ar5iv`) returned
  unparseable binary PDF content or redirected to the non-HTML abstract page. DCA mechanism above is
  reported at Wikipedia-secondary-source confidence only (§3.2).
- **Full text of the autonomous-racing viability-theory paper** (arXiv:1701.08735). PDF fetch returned
  binary content; only the title/topic is confirmed, not the specific kernel-approximation method used.
- **Whether pyCOT has any open-source repository.** A dedicated search (`pyCOT github`) found no
  matching repository; the only confirmed URL is the hosted app `pycot.utem.cl`. Absence of evidence
  is not proof of absence — it is reported honestly as "not found," not "does not exist."
- **Centler, Kaleta, di Fenizio & Dittrich (2008)** organization-computation algorithm — referenced by
  PMC2712341 as the source of "algorithmic details" but not itself fetched; we do not claim to know its
  exact complexity or pseudocode.
- **Luisi (2003) full text** — paywalled; cited at bibliographic/abstract level only (§1.3).

---

## 7. §RECOMMENDATION — the exact computable definitions to implement

### 7.1 Two graphs, not one

1. **`G_import`** — automatically derived (AST-parse `src/nse_algo_trader/**/*.py`, already the kind
   of ground truth `docs/SYSTEM_MAP.md` is supposed to track per Rule H). Necessary substrate,
   **not sufficient**: importing a module is not the same as maintaining it.
2. **`G_maintains`** (new, curated overlay) — each registered component declares, at definition time,
   `maintained_by: tuple[ComponentId, ...]` naming which health-check / restart-supervisor / write-path
   / test keeps it demonstrably current and correct. This mirrors COT treating species as an explicit
   named set (§1.5), not something inferred by scanning "everything that touches it."
   `EXOGENOUS` is a reserved pseudo-component-id for legitimate unmaintained boundary inputs (broker
   APIs, the NSE feed, the OS clock, the human operator) — declaring a node `EXOGENOUS` requires a
   one-line justification string, logged, so it can't be used to silently launder a real violation
   (Rule K: no silent skips).

### 7.2 Computable operational closure (ported from COT §1.5, direction-adjusted for a "maintained-by" edge)

For a candidate set `S ⊆ V` of `G_maintains`:

- **CLOSED(S)** ⟺ no node in `S` has a `maintained_by` edge pointing to a node outside `S ∪ {EXOGENOUS}`.
  *(COT: no reaction from `A` produces outside `A`; here: no maintenance dependency inside `S` reaches
  outside it — S doesn't secretly depend on something the audit didn't account for.)*
- **SELF-MAINTAINING(S)** ⟺ every node in `S` has **at least one currently-ACTIVE** maintainer inside
  `S` (active = its last successful heartbeat/run, sourced from the existing `monitoring_alerts`
  self-monitoring health loop, is within its declared SLA window). This is the boolean/discrete analog
  of COT's `N_A·v' ≥ 0` flux condition — we don't have continuous chemical flux, but "is the maintainer
  demonstrably alive and running" is the direct operational equivalent.
- **ORGANIZATION(S)** = `CLOSED(S) ∧ SELF-MAINTAINING(S)`.

### 7.3 The audit algorithm

1. Build `G_maintains` from the component registry.
2. Compute `condensation(G_maintains)` (networkx) → a DAG of SCCs.
3. **CLOSURE VIOLATION** = any non-`EXOGENOUS` node/SCC that is a **source** of the condensation DAG
   (in-degree 0 — nobody maintains it) **or** whose only inbound maintenance edges originate from
   nodes that are *themselves* closure-violating (a chain hanging off nothing) — i.e. propagate the
   violation transitively forward through the condensation DAG from every unjustified source.
4. Compute an (exact, tractable at this node count) **feedback vertex set** to identify which nodes
   actually sit inside true maintenance *cycles* (the load-bearing organizational core) vs. nodes that
   are merely maintained by an acyclic chain (technically non-violating, but structurally more
   fragile — surfaced as a secondary "fragility" tag, not a hard violation).
5. Compute **articulation points**, **bridges**, **reverse-PageRank**, and **betweenness centrality**
   over `G_maintains`; rank all nodes by criticality (articulation-point flag first, then
   `reverse_pagerank × betweenness_centrality`) → the dashboard's "vital organs" ranking.

### 7.4 Violation reporting & action (Rule K-compliant)

- Every closure violation is written to `docs/BACKLOG.md` under a `component-lifecycle-homeostat`
  heading (what: which component, why: no active maintainer found, done-looks-like: either a real
  maintainer is wired or the node is explicitly declared `EXOGENOUS` with justification) and surfaces
  on the dashboard as an **"Operational Closure"** panel (Rule N: visible feature) — violation count,
  the list, and each entry cross-linked to its `SYSTEM_MAP.md` node.
- **No automatic remediation in v1.** A violation is a loud, tracked alert, never silently patched by
  auto-generating a fake maintainer — that would defeat the entire point (Rule O: never a degraded
  silent stand-in). This audit is, in effect, an AUTOPOIESIS-framed automation of the project's
  existing Rule G ("no orphaned features/files") — the same discipline, now checked by a real graph
  algorithm against a real registry instead of only by human review at sign-off.

### 7.5 Computable boundary membership (self vs non-self)

- **SELF** = the union of (a) the `G_maintains` vertex registry (§7.1) and (b) a parallel **data-source
  registry**: `{source_id, adapter_version}` tuples for every broker/data adapter this system is
  configured to trust, registered at deploy/config time — never learned via negative-selection
  sampling (§3.4's rejection).
- Every inbound datum is tagged (or annotated at ingestion) with `{source_id, adapter_version,
  ingestion_timestamp}`. It is **NON-SELF and quarantined** if any of:
  1. `source_id` is not in the registry, or `adapter_version` is not an approved version for it
     (provenance check, §3.5);
  2. it fails the existing `causal_leakage_firewall` (temporal boundary) or
     `market_data_integrity_defense` (value-integrity boundary) checks;
  3. a `river` ADWIN/Page-Hinkley detector, scoped per-source, flags a distributional break versus
     that source's recent self-baseline (the genuinely new boundary organ this research identifies as
     missing — **component/statistical-identity** boundary, distinct from the two organs that already
     exist).
- **Quarantine action** (never silent-drop, Rule O): route the datum to a logged dead-letter path,
  increment a per-source corruption/drift counter, and if the counter crosses a threshold within a
  session, **suspend that source** (stop consuming it) and surface the suspension on the dashboard and
  in `docs/BACKLOG.md` pending operator review — never an unattended permanent ban, consistent with
  this project's "no auth-bypass, no unattended irreversible action" posture.

### 7.6 What this closes vs what stays open

This closes the *formalism* gap for both 🔴 branches (`operational closure`, `boundary maintenance`)
with real, cited, checkable definitions and a concrete algorithm. It does **not** itself constitute the
built engine — per Rule P this spec is the input to `building-engine-grade-features` for the actual
`component_lifecycle_homeostat` engine (registry + `G_maintains` builder + audit + dashboard panel +
tests against the real `SYSTEM_MAP`), which is the next step, not part of this research deliverable.
