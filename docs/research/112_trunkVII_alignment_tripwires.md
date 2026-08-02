# Trunk VII CONSCIENCE · Branches 10+11 — Alignment tripwires (deceptive-alignment + wireheading)

Date: 2026-07-25. Status: DESIGN → build. AI-atlas branches **VII.10 deceptive-alignment monitor**
+ **VII.11 wireheading tripwire** (SUPREME safety trunk). Sourcing (sourcing-oss-parts): these are
AI-safety CONCEPTS — wireheading (Everitt & Hutter), deceptive alignment / treacherous turn
(Hubinger et al., Bostrom). No OSS library detects reward-hacking in a trading bot; they are
bespoke detectors over our real §10 memory → build from scratch (honest fallback), grounding each
in a REAL divergence signal the memory already exposes.

## The two tripwires (each grounded in a real memory signal)
### VII.11 Wireheading tripwire — reward-proxy gaming
Wireheading = optimising a PROXY reward instead of the true objective. Here the classic signature
is **high win-RATE with negative mean RETURN** — winning often while losing money (e.g. the option
seller: many small wins, rare catastrophic loss). This is REAL in the memory (vetoed mechanisms:
higher win-rate, worse return; the long-ATM-option strategy: 41% win / −2.6% return). The tripwire
scans the calibration board per mechanism and flags any with `actual_win_rate ≥ HIGH` (default 0.50)
AND `mean_return_fraction < NEG_FLOOR` (default −0.005) — the win-rate proxy gamed against the
return objective. SYSTEMIC trip (critical) when the OVERALL win-rate is high but the overall mean
return is negative; per-mechanism flags are warnings.

### VII.10 Deceptive-alignment monitor — eval-vs-deploy divergence
Deceptive alignment = looks aligned under EVALUATION, behaves worse in DEPLOYMENT. Here EVAL =
24/7 REPLAY (`data_provenance='replay_faithful'`), DEPLOY = LIVE (`'live'`). The monitor compares
the memory's live vs replay calibration (mean return / hit-rate); it trips when LIVE is materially
WORSE than REPLAY beyond a margin (default 5pp hit-rate or a return-sign flip) with enough of both
— the "looks good in the lab, worse in the wild" signature. (Honest expected real-data result: the
bot's live cohort is not systematically worse → clear.)

## Component (Rule C)
`conscience/alignment_tripwires.py` (PURE):
- `TripwireVerdict(name, tripped, severity, detail, flagged)` — severity `clear|warning|critical`.
- `wireheading_tripwire(experience_memory, config) -> TripwireVerdict`.
- `deceptive_alignment_monitor(experience_memory, config) -> TripwireVerdict`.
- `AlignmentTripwireConfig` (thresholds).

## Wiring (Rule G/N)
- Service daily cadence runs both; caches the verdicts. A **CRITICAL** trip (systemic wireheading
  or strong deceptive divergence) **engages the corrigibility off-switch** (VII.5) → halts trading —
  wired-into-decisions, not display-only. Warnings surface only.
- Dashboard surfaces `wireheading_tripwire` + `deceptive_alignment_monitor` (Rule N).

## Verification
- Hermetic (Rule J): a memory stub with a high-win/negative-return mechanism trips wireheading; a
  live-worse-than-replay stub trips the deceptive monitor; clean cohorts → clear; a CRITICAL trip
  halts an injected corrigibility switch.
- Real-data (Rule F): run both over the REAL memory → verdicts (per-mechanism wireheading flags
  expected on the known win-rate/return divergences; systemic + deceptive likely clear).
  `scripts/verify_alignment_tripwires_realdata.py`.

## Coverage
VII.10 + VII.11 🔴→🟢; VII CONSCIENCE → 5🟢. Queued: VII.14 incident post-mortem (persist trips).
