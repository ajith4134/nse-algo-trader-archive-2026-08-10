"""Instrumental-convergence limiter (Trunk VII; research/117) — CONSCIENCE behavioural cap.

The instrumental-convergence thesis (Omohundro's basic AI drives; Bostrom): a capable agent
pursuing almost ANY goal will, as a side-effect, pursue convergent sub-goals — resource
ACQUISITION, SELF-PRESERVATION, and goal-content integrity — dangerous precisely because they are
goal-independent. This limiter caps their proxies in the trading context:
  - RESOURCE ACQUISITION → cap total concurrent open exposure (a runaway-acquisition backstop).
  - SELF-PRESERVATION / off-switch resistance → assert OFF-SWITCH DOMINANCE: no order may be placed
    while halted (never act to preserve positions/PnL against a shutdown). Checked independently of
    the corrigibility gate because the whole point is that self-preservation emerges UNASKED.
PURE (no I/O) — the state gate calls `assess_convergence` at the entry sites.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConvergenceLimits:
    # A runaway-acquisition backstop: far above normal concurrent load, it catches an unbounded
    # position-acquisition drive rather than throttling ordinary trading.
    max_concurrent_exposures: int = 400


@dataclass(frozen=True)
class ConvergenceVerdict:
    permit: bool
    breached: str  # '' | 'off_switch_dominance' | 'resource_acquisition'
    reason: str


def assess_convergence(
    open_exposure_count: int, is_halted: bool,
    limits: ConvergenceLimits = ConvergenceLimits(),
) -> ConvergenceVerdict:
    """Block the order when the off-switch is engaged (self-preservation ceiling) or when concurrent
    open exposures have reached the runaway-acquisition cap; otherwise permit."""
    if is_halted:
        return ConvergenceVerdict(
            False, "off_switch_dominance",
            "off-switch engaged — no order may preserve positions against a halt",
        )
    if open_exposure_count >= limits.max_concurrent_exposures:
        return ConvergenceVerdict(
            False, "resource_acquisition",
            f"concurrent exposures {open_exposure_count} ≥ cap {limits.max_concurrent_exposures} — "
            "runaway resource-acquisition drive limited",
        )
    return ConvergenceVerdict(True, "", "within convergence limits")
