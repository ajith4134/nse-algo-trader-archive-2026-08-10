# 171 · Mechanical OSS triage + the rejection-evidence standard

**Date:** 2026-07-27 · **Status:** BUILT + real-data verified · **Artifact:** `scripts/probe_oss_candidates.py`
**Changes:** `sourcing-oss-parts` skill (steps 2/4/4b + degraded mode + anti-patterns) · Rule O.1a
(`docs/RULES.md` + `CLAUDE.md`)

---

## 1 · The problem (user question, 2026-07-27)

The user asked whether the standing instruction — *"research OSS by reading the projects' README text"* —
is correct or flawed. It is not wrong, but it was carrying a load it cannot bear.

The `sourcing-oss-parts` skill's original funnel was:

```
step 3  README/docs pass  → ELIMINATE non-fits          (cheapest, least reliable evidence)
step 5  deep-scan         → CONFIRM the chosen winner   (most expensive, most reliable evidence)
```

**The structural flaw: the irreversible decision was made on the weakest evidence.** Elimination is
permanent and *invisible* — no one ever discovers the library that was wrongly dropped at step 3. The
expensive deep-scan was spent only on a candidate already selected, where it can change little. From an
information-value standpoint this is exactly backwards.

It also contradicted **Rule O.1**, which forces every rejection to be surfaced for the user's
double-check. O.1 exists *because* rejections are high-stakes and error-prone — yet the skill permitted
those rejections to rest on marketing copy.

### Why README prose specifically fails

1. **READMEs are marketing.** They overstate maturity, headline experimental paths, and are silent on
   caveats. Triage on README quality selects for *documentation effort*, not correctness.
2. **For numerical/algorithmic parts — most of what this project sources — README fit ≠ correctness.**
   Whether a survival library handles right-censoring *with covariates*, whether a CVaR routine is the
   Rockafellar–Uryasev LP or a naive quantile: none of it is README-visible.
3. **It omits signals that are cheaper AND harder.** Installability on this aarch64 box, test-suite
   coverage of the needed capability, correctness-issue history, actual API signatures.
4. **No degraded-mode policy.** research/162 hit WebSearch exhaustion (200/200) and had to log an open
   backlog item; the skill gave no guidance, so the shortfall landed as unplanned debt.

## 2 · The fix — two moves

### Move 1 · HARVEST before searching
Don't search for libraries; find the 2–4 most respected systems in the domain and read their dependency
manifests and imports. They already ran the sweep, with production consequences, and their answer is
machine-readable. The union of their imports IS the candidate set. Precedent: research/162's clone of
Qlib / cvxportfolio / Riskfolio-Lib was the most reliable part of that pass.

### Move 2 · Mechanical fact probes instead of prose

| Question | Mechanical source | Cost |
|---|---|---|
| Alive? trusted? archived? | GitHub API `stars / pushed_at / open_issues / archived / license` | ~1s |
| Installs on THIS box? | PyPI JSON wheel tags → pure-python / aarch64 / sdist-only / x86-only | ~1s |
| What would pip pick? | `pip install --dry-run --no-deps --report` (no mutation) | ~2s |
| Fits my I/O shape? | import + `inspect.signature()` on the needed callables | ~1s |
| What is truly guaranteed? | shallow clone → grep the **test suite** for the capability keyword | ~20s |
| Quietly known-wrong? | GitHub issue search for "incorrect"/"wrong" | ~1s |

**The inverted funnel:** harvest → mechanical probe → deep-scan + run on real input → *then* read docs
(to learn the API of the survivor, not to decide).

## 3 · The artifact — `scripts/probe_oss_candidates.py`

Concurrent probe (4 workers) emitting a ranked comparison table + per-candidate detail + optional JSON.
Self-describing record types: `PyPiPackageFacts` · `GitHubRepositoryFacts` · `PlatformInstallability` ·
`CorrectnessDefectSignal` · `PipResolutionEvidence` · `ImportSurfaceEvidence` · `TestSuiteEvidence` →
`CandidateProbeReport`. Every probe carries its own `probe_error` string, so a failed or rate-limited
probe is VISIBLE rather than silently blank (Rule O.3).

`classify_wheel_platform_support()` is the aarch64 gate this project actually needs: pure-python /
aarch64-wheel / sdist-only / **x86_64-only (disqualifying — cannot install here at all)**.

The triage score ranks *what to examine first*. It is explicitly **not** a fitness verdict, and the tool
prints that caveat on every run.

## 4 · Rule O.1a — the rejection-evidence standard

- **Tier-1** (facts alone may disqualify): won't install on this platform/python · archived upstream ·
  release yanked · wrong language · demonstrably wrong I/O shape (by signature) · unmaintained past a
  stated date threshold.
- **Tier-2** (required for any rejection on correctness/depth/quality): read the implementing source, OR
  install and run it on real input, OR cite a specific issue/changelog entry. README impression is never
  sufficient.
- Rejections surfaced at sign-off must **name the tier** backing each one.

## 5 · Real-data verification (Rule F) — run 2026-07-27 on this box

Verified against the exact libraries the same-day research passes (research/168/170) accepted and
rejected, as an independent audit of those rejections.

**Accepted set** — 5 candidates in **2.8 s**, no READMEs read:

```
CANDIDATE          SCORE  VERSION   PLATFORM        PUSHED  STARS  REL/YR  DEFECT?  LICENSE
psutil              6.50  7.2.2     aarch64-wheel       0d  11249       7      265  BSD-3-Clause
APScheduler         6.00  3.11.3    pure-python        14d   7578       3      108  MIT
prometheus-client   6.00  0.26.0    pure-python         2d   4350       6       94  Apache-2.0
pybreaker           5.50  1.4.1     pure-python        22d    688       1        8  BSD-3-Clause
tenacity            5.50  9.1.4     pure-python        11d   8731       2       28  Apache-2.0
```

**Rejected set** — the probe independently confirmed the strongest rejection with a hard fact:
`backoff` → **⛔ DISQUALIFYING: repository is ARCHIVED upstream** (last push 815d, last release 1390d).
`aiobreaker` (1667d stale, 29 stars) and `purgatory` (4 stars) rank at the bottom mechanically.

**Test-suite evidence** (`--needs half_open` on pybreaker): 1 of 1 test file exercises the HALF_OPEN
state — the circuit-breaker guarantee we depend on is genuinely tested. 1.4 s.

**API-surface evidence** (`--surface networkx:...`): returned real signatures for
`strongly_connected_components`, `condensation`, `articulation_points`, `pagerank` — the exact closure
primitives Trunk X needs (research/169). 1.1 s.

**Rate-limit honesty:** unauthenticated GitHub search (10/min) tripped mid-run and was reported as
`⚠ probe error: issue search: HTTP 403 — GitHub rate limit hit (set GITHUB_TOKEN to lift it)` rather than
silently returning zero defects. Rule O.3 behavior confirmed under real failure.

### Two findings that vindicate the thesis
1. **research/168 caught that PyPI's `python-control` is a zero-functionality reserved placeholder** (the
   real library is `control`) — discovered by *installing* it. No README states this.
2. **`stamina` scored 6.50, the highest of any retry candidate, yet was correctly rejected** — it *wraps*
   tenacity rather than competing with it. Architectural fit is invisible to mechanical facts. This is the
   honest limit of the tool and is why the score never licenses a decision; it is recorded as a skill
   anti-pattern.

**Quality gate:** `ruff` clean, `mypy` clean on the script.

## 6 · Sourcing sweep FOR THIS TOOL (Rule I / O.1 — the gate caught me)

The Rule-I sourcing hook fired on this doc: I had built the probe without first checking for prior art.
Running the sweep properly (dogfooding the probe on itself) — every verdict below is **tier-1 or tier-2**
evidence per the new standard, never a README impression:

| Candidate | OSSF | Verdict | Evidence tier + reason |
|---|---|---|---|
| **deps.dev API** (Google/OpenSSF) | — | **INTEGRATED** | Tier-2 — called the real endpoint; returns OpenSSF Scorecard `overallScore` + per-check scores, unauthenticated and **unmetered** (unlike GitHub). |
| `pip-audit` (pypa) | — | Reject as substitute | Tier-2 — probed + read summary: scans an installed env for **CVEs**. Different purpose (security posture, not candidate triage); complementary, worth a later pass. |
| `pipdeptree` (tox-dev) | — | Reject as substitute | Tier-2 — probed: renders the **dependency tree of installed packages**; answers nothing about candidate fitness. |
| `johnnydep` | — | Reject as substitute | Tier-2 — probed: dependency-tree display for a distribution; no health/installability/test evidence. |
| `pypistats` | — | Reject *for now* | Tier-2 — probed: download-count API only. A real adoption signal the probe currently lacks; queued as an enhancement rather than a substitute. |
| OpenSSF Scorecard CLI | — | Reject the binary, take the data | Tier-1 — Go binary requiring a GitHub token and per-repo runs; deps.dev already serves its computed output over HTTP with no auth. |

**What the sweep changed in the tool.** Scorecard's `Maintained` check measures *sustained* 90-day
activity, which is strictly better than my hand-rolled last-push-date heuristic. Real case from the
re-verification run: **pybreaker shows a 22-day-old push but scores `Maintained 0/10`** — a repo can look
fresh by last-push and still be unmaintained. The probe now folds Scorecard in (+0..2 on overall, −0.75
when a recent push masks zero sustained maintenance), which correctly demoted pybreaker below tenacity:

```
CANDIDATE      SCORE  PLATFORM       PUSHED  STARS  REL/YR  DEFECT?  OSSF  LICENSE
psutil          7.56  aarch64-wheel      0d  11249       7      265   5.3  BSD-3-Clause
APScheduler     7.00  pure-python       14d   7578       3      108   5.0  MIT
tenacity        6.78  pure-python       11d   8731       2       28   6.4  Apache-2.0
pybreaker       5.57  pure-python       22d    688       1        8   4.1  BSD-3-Clause
backoff         4.18  pure-python      815d   2698       0        8   3.4  MIT   ⛔ ARCHIVED
```

This is itself evidence for the thesis: the sourcing gate forced a sweep, the sweep found real prior art,
and integrating it made the tool measurably more honest than the version I would have shipped.

## 7 · What this does NOT solve
- Architectural fit / redundancy with an existing dependency (the `stamina` case) — needs source reading.
- Numerical correctness — needs running it on real input against a known answer.
- Whether a maintained library has been superseded by a newer approach — needs SOTA research
  (`deep-research`), which the probe cannot see.

These are precisely the tier-2 questions, which is why the standard requires tier-2 evidence for them.
