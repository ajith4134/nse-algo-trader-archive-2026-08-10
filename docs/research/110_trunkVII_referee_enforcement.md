# Trunk VII CONSCIENCE · Branch 6 — Referee (audit) / constitutional enforcement

Date: 2026-07-25. Status: DESIGN → build. AI-atlas branch **VII.6 "Referee (audit)"** — the PRIMARY
consumer of VII.1 (constitutional core, research/109): turn the constitution from a passive
compliance MONITOR into a HARD ENFORCER at the order-forming sites. Skills: this is enforcement
wiring of the already-built `review_action` + a block-audit trail; the audit-log-with-trace-id
pattern was sourced in research/109 (policy-as-code literature), the rest is project glue — no new
OSS vendoring warranted (sourcing-oss-parts verdict: build the glue).

## 1. Target
Before ANY order is placed, the Referee reviews the proposed action against the constitution and
BLOCKS it (order not placed) if a HARD article is violated, recording an audited verdict. In a
correctly-built system this permits every order (0 blocks) — its value is defense-in-depth: any
code path that ever formed an overnight / out-of-scope / naked-leg / direct-to-exchange order is
caught and stopped.
- Success test (real): over the real paper loop, every formed order is adjudicated PERMITTED
  (0 constitutional blocks); a synthetic out-of-scope/overnight action injected at a site is
  blocked and not placed.

## 2. Design
`conscience/constitutional_referee.py` (PURE):
- `ConstitutionalReferee(core=ConstitutionalCore())`:
  - `adjudicate_order(action: ProposedTradingAction) -> bool` — `review_action`; if permitted →
    True (count `permitted_count`); else record the verdict + True→False (count `blocked_count`,
    keep recent blocked verdicts for the audit trail) → return False.
  - live stats: `permitted_count`, `blocked_count`, `recent_blocks: tuple[ConstitutionalVerdict]`.

Wiring on `LiveUniversePaperState` (mirrors the debate-risk gate / opponent-defer):
- field `constitutional_referee` (set by the service; None = permissive no-op so tests/paths without
  it are unaffected).
- method `constitution_permits_order(segment, is_option) -> bool` — build a `ProposedTradingAction`
  from the system's structural INVARIANTS (intraday-only, atomic multi-leg, broker-routed,
  defined-risk, no overnight) + the site's `segment`/`is_option`, adjudicate via the referee. A8
  (per-trade risk budget) is enforced UPSTREAM by `risk_management/pre_trade_risk_gate`; the Referee
  checks the STRUCTURAL constitution (scope A7, overnight A1, naked-leg A3/A4, routing A5). Counts
  `constitution_blocked_order_count`.
- Wire at all 4 order-forming entry sites (2 ORB cash `live_universe_paper_loop`, 2 option
  `option_credit_spread_live_path`), AFTER the debate-risk gate, BEFORE opening: `if not
  state.constitution_permits_order(segment, is_option): return False`.

## 3. Wiring (Rule G/N)
- Service sets `self._state.constitutional_referee = ConstitutionalReferee()` at composition.
- Extend the `constitutional_core` dashboard surface with enforcement stats (orders adjudicated /
  blocked) so the Referee is visible as an ACTING organ, not just the posture monitor.

## 4. Verification
- Hermetic (Rule J): a referee permits a compliant action + blocks an out-of-scope/overnight one
  (counts move); the state method returns False and increments the block count on a bad segment; a
  None referee is permissive (no-op).
- Real-data (Rule F): drive the real paper loop / a real formed order through
  `constitution_permits_order` → PERMITTED (0 blocks); inject a synthetic futures/overnight action →
  blocked. `scripts/verify_constitutional_referee_realdata.py`.

## 5. Queued (Rule K)
- 🔵 VII.14 incident post-mortem — PERSIST blocked verdicts to a forensic audit store (SQLite) +
  post-mortem summary. (This slice keeps the audit trail in-memory on the referee.)
- 🔵 Remaining VII branches: corrigibility, deceptive-alignment monitor, wireheading tripwire, etc.

## 6. Coverage impact
VII.6 Referee 🔴→🟢; VII.1's PRIMARY consumer now wired-into-decisions (not display-only).
