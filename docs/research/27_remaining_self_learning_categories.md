# 27 — Remaining Self-Learning/Intelligence Categories (Expand-Idea Sweep)

Final expand-idea pass on the "self-learning AI / becoming intelligent /
autonomous research" domain: identifies the full category taxonomy,
marks what's already covered by this project's 16 prior research passes,
and researches the branches that were named conceptually in
`research/06` but never matched to a real project — plus branches never
named at all. Every project verified via direct README/docs fetch,
2026-07-23. License informational only, per `CLAUDE.md` Rule E.

**Status: research only. Nothing implemented.**

## Coverage map

| Branch | Status |
|---|---|
| Self-learning AI taxonomies, autonomous research agents | ✅ covered (`research/05`, `08`, `09`) |
| Memory/knowledge-graph frameworks | ✅ covered (Graphiti, Cognee, Mem0, LightRAG) |
| Continual learning | ✅ covered (Avalanche, River) |
| GP/evolutionary strategy discovery | ✅ covered (gplearn, DEAP, Darwinia, OpenEvolve) |
| Self-modifying agents | ✅ covered (MATS, DGM, ADAS, SEAL, Absolute Zero Reasoner, Eureka, SPIN) |
| Multi-agent trading frameworks | ✅ covered |
| Integration frameworks | ✅ covered (eliza, AGiXT, LangGraph, Hummingbot) |
| **Meta-learning** | named conceptually (`research/06` #20), **no project ever matched — closed here** |
| **Active learning** | named conceptually (`research/06` #19), **no project ever matched — closed here** |
| **Federated learning** | named conceptually (`research/06` #27), **no project ever matched — closed here** |
| **Synthetic time-series data generation** | only project-specific CoFinDiff reference existed — **extended here** |
| **Explainability/interpretability** | only SHAP mentioned generically — **a real library catalogue added here** |
| **Cognitive architectures** | not covered at all — **new branch, researched here** |
| **Curriculum learning** | not covered — **new branch, researched here** |
| **Novelty/anomaly detection** (distinct from drift detection) | drift detection covered; novelty detection was not — **new branch, researched here** |
| **Quality-Diversity / open-endedness** | not identified in any prior pass — **new branch, found unprompted** |

## Findings per branch

**Meta-learning** — [learn2learn](https://github.com/learnables/learn2learn)
(2.9k★, MIT, stalled since 2023) implements MAML/ANIL/Meta-SGD/Reptile/
ProtoNets on PyTorch. [facebookresearch/higher](https://github.com/facebookresearch/higher)
(1.6k★, Apache-2.0, **archived** Oct 2023) does differentiable
unrolled-optimization for backprop-through-training-steps. **Fit**: this
literally implements `research/06` #20 ("which sub-strategy works in
which regime") — a MAML-style outer loop over per-regime inner-loop fits
could learn strategy-initialization priors that fast-adapt to a new
regime, with candidates still routed through the existing gate. Both
libraries are stale — reference implementations to port ideas from, not
drop-in dependencies.

**Active learning** — [modAL](https://github.com/modAL-python/modAL)
(2.4k★, MIT) is a scikit-learn/Keras uncertainty-sampling/query-by-
committee framework. [baal](https://github.com/baal-org/baal) (933★,
Apache-2.0, actively released through 2025) does MC-Dropout/Bayesian
deep-learning uncertainty estimation with a ready-made
`ActiveLearningLoop`. **Fit**: directly implements `research/06` #19 —
baal's uncertainty heuristics can be the literal trigger for "ask the
user for a label" instead of a bespoke uncertainty metric.

**Federated learning** — [Flower](https://github.com/adap/flower) (7k★,
Apache-2.0, very active) is framework-agnostic federated orchestration
(PyTorch/TF/sklearn/XGBoost). [PySyft](https://github.com/OpenMined/PySyft)
(9.9k★, Apache-2.0, active) does privacy-preserving compute where data
owners approve results before sharing. **Fit**: implements `research/06`
#27 — if multiple paper-mode strategy instances ever run in parallel,
Flower's client/server round pattern pools learned weights without
pooling raw trade data, still landing at the same human gate before
promotion.

**Synthetic time-series data** — [SDV](https://github.com/sdv-dev/SDV)
(3.5k★, Business Source License) does GaussianCopula/CTGAN tabular +
sequential synthesis. [ydata-synthetic](https://github.com/ydataai/ydata-synthetic)
(1.6k★, MIT, active) implements **TimeGAN** and **DoppelGANger**
specifically, with example notebooks on stock data. **Fit**: extends
`research/06` #22 (synthetic stress rehearsal) beyond the
project-specific CoFinDiff reference with a working notebook already
demonstrated on stock data.

**Explainability/interpretability** — [Captum](https://github.com/pytorch/captum)
(5.7k★, BSD-3, Meta-maintained) does Integrated Gradients/GradCAM/TCAV/
TracIn for any PyTorch model. [InterpretML](https://github.com/interpretml/interpret)
(6.9k★, MIT, active) provides Explainable Boosting Machines (glassbox,
accuracy near XGBoost) plus SHAP/LIME wrappers. **Fit**: extends
`research/06` #28 (end-to-end explainable audit trail) and doubles as
literal SEBI white-box registration evidence — EBM as the model class
itself, Captum for any neural component, both auditable per-decision.

**Cognitive architectures** — [Soar](https://github.com/SoarGroup/Soar)
(426★, BSD-2, active) is the classical academic cognitive architecture
(production rules, working memory, chunking). [daveshap/ACE_Framework](https://github.com/daveshap/ACE_Framework)
(1.5k★, MIT, **archived** Aug 2024) is a modern LLM-native layered
cognitive architecture (aspirational → global-strategy → agent-model →
executive-function → cognitive-control → task-prosecution). **Found this,
wasn't asked**: ACE is the closest thing found to "becoming intelligent"
at its most literal, but archived/unmaintained — worth reading for the
layering idea, not for adoption.

**Curriculum learning** — [flowersteam/TeachMyAgent](https://github.com/flowersteam/TeachMyAgent)
(78★, MIT, ICML 2021 benchmark) benchmarks automatic-curriculum-learning
teacher algorithms (ADR, ALP-GMM, RIAC) that progressively adjust RL task
difficulty. **Honest gap**: this branch is thin — no mature
general-purpose (non-RL) curriculum-learning library exists. The concrete
idea worth porting: an ALP-GMM-style teacher that sequences paper-mode
training from calm to volatile/rare market regimes, rather than training
on all historical regimes at once — directly relevant to `research/26`'s
continuous-replay design, since the replay engine now has a
regime-sequencing decision to make, not just a data source to serve.

**Novelty/anomaly detection (distinct from drift detection)** —
[PyOD](https://github.com/yzhao062/pyod) (9.9k★, BSD-2, very active) has
60+ detectors across tabular/time-series/graph, including
time-series-specific KShape/MatrixProfile/AnomalyTransformer.
[STUMPY](https://github.com/stumpy-dev/stumpy) (4.1k★, BSD-3, active)
does matrix-profile "discord" discovery for time series. **Fit**:
distinct from drift detection (which compares live vs. training
*distributions*) — these flag a specific *novel pattern* inside live
data the model has never seen, a second, complementary trigger for the
`research/12` hypothesis pipeline or a halt-and-flag signal.

**Quality-Diversity/open-endedness (found unprompted)** —
[pyribs](https://github.com/icaros-usc/pyribs) (264★, MIT, active)
implements MAP-Elites/CMA-ME/CMA-MAE. Unlike gplearn/DEAP/OpenEvolve (all
single-objective), QD maintains an *archive of diverse high-performers
across a behavior-space grid*. **This is a near-literal implementation of
`research/06` #16's "validated skill library"** — archive cells could be
regime-type × risk-profile niches, each holding the best-known strategy
variant for that niche, still gated before promotion.

## What this changes about the plan

Every item in this file closes a specific "described but never matched to
a real project" gap in `research/06`'s 28-feature taxonomy — items #16,
#19, #20, #22, #27, #28 now each have at least one real, fetchable
implementation to study, not just a conceptual description. Cognitive
architectures and curriculum learning are honestly thin branches (best
available options are archived or narrow) — recorded as such rather than
overstated.

## Ranked — most valuable to read full source from next

1. **PyOD** — most mature, most directly installable; highest near-term
   signal-to-effort ratio for the `research/12` hypothesis pipeline.
2. **pyribs** — the clearest real implementation yet of the "validated
   skill library" concept that's been informal since `research/06`.
3. **ydata-synthetic (TimeGAN)** — concretely fills the synthetic-stress-
   rehearsal gap with a working notebook already run on stock data.
4. **baal** — smallest lift to wire the existing active-learning feature
   idea to real uncertainty math instead of a bespoke heuristic.
5. **InterpretML** — most directly relevant to the SEBI white-box
   audit-trail requirement, not just a research nicety.

This closes the self-learning/intelligence research thread. Combined with
`research/22`-`25`, the project has now run 18 research passes and
README/paper-verified over 110 real projects across every AI-related
category discussed.
