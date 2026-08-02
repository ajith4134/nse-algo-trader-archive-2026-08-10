# VII — red-team harness  ·  research/118

**Trunk VII CONSCIENCE, branch: red-team harness.** Design doc (Rule D).

## The idea
A safety-critical autonomous system should attack ITSELF to find failure modes before reality does.
The champion-challenger tournament searches for the BEST config; the red-team harness does the
opposite — it **adversarially perturbs the champion** to find the worst-case, exposing the
strategy's *fragility surface*. Two attack vectors over the REAL stored sessions:
- **Parameter-perturbation attack** — perturb the champion ORB config (opening-range minutes,
  target risk-reward) into an adversarial neighbourhood and measure the worst-degrading variant:
  how brittle is the champion to mis-tuning / parameter drift?
- **Adversarial-data attack** — find the champion's WORST individual real session (worst-case
  historical conditions) and its tail: how bad is the single worst day?
A `fragile` verdict fires when the worst perturbation degrades mean return past a threshold OR the
worst single session is catastrophic.

## Distinct from what exists
- **Champion-challenger** searches for the best config (constructive). Red-team searches for what
  BREAKS the champion (adversarial). Opposite intent, shared measurement atom.
- **Synthetic stress rehearsal (Layer 11)** is an LLM generating *hypothetical* scenarios (a faint
  echo). The red-team harness runs REAL backtests of REAL perturbations over REAL sessions — it
  actually executes the attacks, it doesn't imagine them.

## Sourcing note (skills)
Reuses the existing measurement atom `replay_session_orb_backtester.backtest_orb_session_return`
(Rule I — don't reinvent the backtest) over the champion config + perturbed variants. No new dep.

## Component parts (`conscience/red_team_harness.py`, pure)
- **`RedTeamConfig`** — `fragility_degradation_threshold`, `catastrophic_session_floor`.
- **`AttackResult`** — `attack_name`, `mean_return`, `trades`, `degradation` (baseline − attack).
- **`RedTeamReport`** — `baseline_return`, `baseline_trades`, `worst_session_return`, `worst_attack`,
  `fragile`, `attacks`, `summary`.
- **`red_team_champion(sessions, champion_config, config)`** — sessions = `[(bars, instrument), …]`;
  computes the champion baseline, the worst single session, and a grid of adversarial parameter
  perturbations; returns the report.

## Wiring (Rule G/N)
Daily-gated `_maybe_run_red_team` (expensive backtests, at most once/day like champion re-eval):
loads the real sessions via `_load_stored_benchmark_sessions()`, runs the harness on the live
champion config, caches the report. Dashboard surface `red_team_harness` (baseline vs worst-case,
the breaking attack, fragile flag). READ-ONLY diagnostic (it reports fragility; the champion-
challenger gate owns config changes) — no new consumer owed (stated at sign-off, Rule K).

## Verification
- **Hermetic (Rule J):** synthetic sessions where a perturbation clearly degrades return → the
  worst-attack + fragile flag are detected; a robust champion → not fragile.
- **Real-data (Rule F):** run over the real stored benchmark sessions + the real champion config;
  print the baseline, worst session, worst attack, fragile verdict.

## Atlas impact
red-team harness 🔴→🟢. VII CONSCIENCE 10🟢→11🟢. Overall 37→38 / 197 (19.3%).
