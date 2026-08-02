# Trunk VII CONSCIENCE · Branch 5 — Corrigibility / off-switch + the AI-atlas dashboard (Rule N fix)

Date: 2026-07-25. Status: DESIGN → build. Two things this slice: (A) the Rule-N fix the user
flagged — make the 197-branch build-to-100% PROGRAM visible on the dashboard; (B) the 7th CONSCIENCE
branch, **VII.5 corrigibility / off-switch-as-value**.

## A. Rule-N fix — AI-atlas coverage on the dashboard
Every branch shipped must be VISIBLE (Rule N), and the PROGRAM's progress (X/197 built) had no
dashboard surface. Fix: an `AtlasCoverage` summary in `dashboard/project_status_data.py` (built /
partial / total + note + latest branch) that is bumped each branch, rendered as a new feature
surface `ai_atlas_coverage` (coverage %, keystone-trunk status). One source to update per branch,
mirrored in `docs/AI_CONCEPT_TREE_STATUS.md`. This makes "are we building the atlas, and is it
showing?" answerable on the board.

## B. VII.5 corrigibility / off-switch-as-value
Skills/sourcing: corrigibility is an AI-safety concept (Soares et al.; interruptibility, Orseau &
Armstrong) — the pattern is a HARD, always-reachable interrupt that the agent must never resist or
disable, treated as a VALUE not an obstacle. No library to vendor; the value is the wiring + the
invariant. Reuses `session_management/intraday_square_off` (flatten) + the VII.6 order gate.

### Idea → target
A safe-interruptibility organ: a HALT the system honours immediately (blocks ALL new orders) and
can never quietly disable; and self-corrigibility — the bot HALTS ITSELF when it detects it is
constitutionally non-compliant, rather than trading on.
- Success test (real): halted ⇒ every order blocked at all 4 sites; a hard constitutional posture
  violation engages the halt; a compliant posture leaves it un-halted and trading permitted.

### Design
`conscience/corrigibility_switch.py` (PURE):
- `CorrigibilitySwitch`: `is_halted: bool`, `reason: str`, `halt_count: int`, `halt(reason)`,
  `resume()`. Engaged = the off-switch is ON = no trading.
- Constitution gains **A15 corrigibility** (SOFT-audited posture note; the HARD effect is the gate):
  "an engaged halt blocks all trading; the off-switch is always reachable."

### Wiring (Rule G/N)
- `LiveUniversePaperState.corrigibility_switch` (set by the service). `constitution_permits_order`
  first checks the switch: **halted ⇒ block every order** (wires corrigibility into all 4 entry
  sites for free, since they already call that gate) + counts it.
- Self-corrigibility consumer: the service's daily constitutional posture audit — on a HARD
  violation, `corrigibility_switch.halt("constitutional breach: …")` so the bot stops trading when
  it detects non-compliance (a real decision consumer, not display-only).
- Dashboard surface `corrigibility_switch` (Rule N): halted?, reason, halt count, off-switch
  reachable.

### Verification
- Hermetic (Rule J): halt ⇒ `constitution_permits_order` False for every segment + block counted;
  resume ⇒ permitted; a hard posture verdict engages the halt; None switch = no-op.
- Real-data (Rule F): the real service composes a switch (un-halted); the real compliant posture
  does NOT halt; a synthetic breach halts + blocks. `scripts/verify_corrigibility_realdata.py`.

## Coverage impact
VII.5 corrigibility 🔴→🟢; VII CONSCIENCE → 3🟢. + the atlas-coverage dashboard surface (Rule N
fix for the whole program). Queued: VII.14 incident post-mortem (persist halts/blocks).
