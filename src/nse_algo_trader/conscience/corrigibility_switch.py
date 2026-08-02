"""Corrigibility / off-switch-as-value (Trunk VII.5; research/111).

Safe interruptibility: a HARD, always-reachable off-switch the system honours immediately and must
never quietly disable or resist — treated as a VALUE, not an obstacle (the corrigibility /
interruptibility safety concept). When ENGAGED, no new order may be placed; the bot stops trading.
Paired with self-corrigibility: the bot HALTS ITSELF when it detects it is constitutionally
non-compliant, rather than trading on. PURE (no I/O); the block is enforced through the same
constitutional order-gate the Referee uses, so engaging the halt stops all 4 entry sites at once.
"""

from __future__ import annotations


class CorrigibilitySwitch:
    """The off-switch. `is_halted` True = trading stopped. `halt()`/`resume()` are always
    available; a halt can never be silently ignored (the order gate consults it)."""

    def __init__(self) -> None:
        self.is_halted = False
        self.reason = ""
        self.halt_count = 0

    def halt(self, reason: str) -> None:
        """Engage the off-switch — no new orders until resumed. Idempotent per engagement; each
        fresh engagement (from un-halted) counts once."""
        if not self.is_halted:
            self.halt_count += 1
        self.is_halted = True
        self.reason = reason

    def resume(self) -> None:
        """Release the off-switch — trading may resume once the breach is cleared."""
        self.is_halted = False
        self.reason = ""

    def permits_trading(self) -> bool:
        """True when the off-switch is NOT engaged. The order gate blocks all orders when False."""
        return not self.is_halted
