# Research/63 — Prequential forecast scorer: OSS sourcing pass (§53 slice 3b)

**Skill:** `sourcing-oss-parts` (Rule D persistence of the sweep so it is not
re-run). Ran 2026-07-25 while building §53 slice 3a; this piece belongs to the
QUEUED **slice 3b** (the dense per-step prequential scorer, §8.1). Recorded now so
the verdict is on file before 3b starts.

## The piece's shape
Stream of `(forecast probability p∈[0,1], then revealed outcome y∈{0,1})` arriving
one at a time (online) → a **running mean log-loss and Brier**, queryable at any
point, ideally per cohort/group. Python 3, light deps, embeddable, offline.
License is NOT a filter (personal use, Rule E).

## Sweep (search by function, ≥4 sources)
PyPI · GitHub · libraries.io · web. Terms: "prequential evaluation python",
"progressive validation python", "online log loss brier streaming", "incremental
metrics river", "sequential probability scoring", "calibration streaming metrics".

## Ranked candidates
| Candidate | Fit | Tested | Maintained | Deps | Verdict |
|---|---|---|---|---|---|
| **river.metrics.LogLoss + stats.Mean + metrics.base** | exact — `update/get/revert`, O(1) incremental, no numpy in these files | yes (in-repo) | yes (5.9k★, BSD-3, active) | package pulls numpy + **needs Python ≥3.11** | **VENDOR** (chosen) |
| river.evaluate.progressive_val_score | partial — coupled to a River model (`predict_proba_one`) & `(x,y)` dataset | yes | yes | same | **REJECT** (wrong shape; our p is our own) |
| river.metrics.BrierScore | **does not exist** — only `log_loss.py`/`cross_entropy.py` | — | — | — | write a ~15-line twin |
| scikit-multiflow / creme | superseded by River | some | **no** (dormant/deprecated) | numpy | reject |
| scoringrules / properscoring | right formulas, **batch-array**, no running state | some | active-ish | numpy | reject (wrong execution model) |
| python-prediction-scorer (yhoiseth) | Brier+log **functions**, pure-python | yes (100%) | weak (6★) | none | reference only (no streaming accumulator) |
| superior-scoring-rules | multiclass research metric | minimal | low | numpy | reject |
| evidently / whylogs | segment metrics, mature | yes | yes | heavy (pandas/pydantic) | reject (over-scoped) |

## Recommendation (for slice 3b)
**Vendor-and-adapt River's metric-object pattern**, NOT `progressive_val_score`
(model-coupled). Lift ~100–150 LOC, zero numpy in this slice:
- `river.stats.Mean` (Welford running mean),
- `river.metrics.base.MeanMetric` / `BinaryMetric` (the `update`/`revert`/`get` scaffold),
- `river.metrics.LogLoss` (as-is or as template),
- **write** `BrierScore(MeanMetric, BinaryMetric)` with `_eval(y, p) = (p - y) ** 2`.
Per-cohort scores = a plain `dict[group_key, LogLoss()]` (River's own per-output
pattern). Record provenance in a header comment (source `online-ml/river`,
BSD-3-Clause, commit/version, "adapted: dropped package-level numpy/Py-3.11
constraint"). Do NOT `pip install river` (numpy + Python ≥3.11 pull-in for ~100 LOC).

## Provenance-tagging (slice 3a, done)
No OSS library exists for tagging streamed samples live-vs-replay in an online
evaluator. The established pattern (mirrored by River's per-group metric dict) is
a **plain per-sample field routed as a dict key** — no library. This is exactly
what slice 3a did: `data_provenance` on `ClosedExperiment` + the
`calibration_board(data_provenance=...)` filter + `experiment_count_by_provenance`.

## Sources
- https://github.com/online-ml/river/blob/main/river/metrics/log_loss.py
- https://github.com/online-ml/river/blob/main/river/metrics/base.py
- https://github.com/online-ml/river/blob/main/river/evaluate/progressive_validation.py
- https://github.com/online-ml/river/tree/main/river/metrics/multioutput
- https://pypi.org/project/river/ · https://github.com/yhoiseth/python-prediction-scorer · https://scoringrules.readthedocs.io/
