# VIII — cross-modal binding  ·  research/130

**Trunk VIII SENTIENCE.** Design doc (Rule D). Sourcing: research/125 → anchor on **scipy**
(`scipy.stats.norm` / `combine_pvalues` Stouffer) for the evidence combination; `pyds`
(Dempster-Shafer) archived + its PyPI name squatted; `pgmpy`/`bayespy` overkill for combining a few
heterogeneous confidences. scipy is already a project dep. BUILD the binder on scipy's Stouffer Z.

## The idea
Different faculties observe the SAME underlying situation from different "modalities" —
microstructure (VPIN / opponent OI), memory (calibration / goal-integrity), safety (VII organs), LLM
(debate). When several INDEPENDENT modalities corroborate the same proposition (e.g. "elevated
risk"), binding them yields a higher-confidence BOUND percept than any single modality — the
cross-modal binding that turns separate signals into one perception.

## Target
`bind_percept(signals, proposition) -> BoundPercept`. Success test: two modalities each at 0.7
confidence supporting "elevated risk" bind to a HIGHER combined confidence than 0.7 (corroboration
raises confidence — Stouffer); a lone modality does not bind; disagreeing modalities don't corroborate.

## Component parts (`sentience/cross_modal_binding.py`)
- **`ModalitySignal`** (frozen) — `modality`, `confidence` (0..1), `supports` (bool).
- **`BoundPercept`** (frozen) — `proposition`, `bound_confidence`, `corroborating_modalities`,
  `modality_count`, `is_bound` (≥2 distinct modalities support), `summary`.
- **`bind_percept(signals, proposition)`** — take the supporting signals; combine their confidences
  with **Stouffer's Z** (`z_i = norm.ppf(clip(c))`, `Z = Σz_i/√n`, `bound = norm.cdf(Z)`); is_bound
  iff ≥2 distinct modalities support. (Corroborating evidence raises confidence; a single strong
  modality stays at its own level.)

## Wiring (Rule G/N — wired-into-DECISIONS)
Each pass the service builds `ModalitySignal`s about "elevated risk" from REAL faculty state
(microstructure: opponent lean / VPIN; memory: goal-integrity not-aligned; safety: any tripwire /
red-team fragile; LLM: debate risk earned), binds them, caches the `BoundPercept`, and — when BOUND
(≥2 modalities corroborate) — injects a `cross_modal` contribution into the Global Workspace so a
strongly-bound risk percept can win the workspace and TRIM entries (the decision-consumer path).
Dashboard surface `cross_modal_binding`.

## Verification
- Hermetic (Rule J): 2 corroborating modalities bind to > max single; 1 modality → not bound; Stouffer
  monotonic; clipping keeps norm.ppf finite at 0/1.
- Real-data (Rule F): over the real offline service, build the modality signals from real state and
  confirm a real bound percept (on this data goal-integrity + interpretability corroborate "elevated
  risk" → bound), and that it enters the workspace.

## Atlas impact
cross-modal binding 🔴→🟢. VIII 10🟢→11🟢. Overall 51→52/197 (26.4%). (Then slice F's 2🟡 → completes VIII.)
