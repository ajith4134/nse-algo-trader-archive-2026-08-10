"""Constitutional Referee — the enforcer (Trunk VII.6; research/110).

Turns the constitution (VII.1) from a passive posture MONITOR into a HARD ENFORCER: before any
order is placed, the Referee reviews the proposed action and BLOCKS it (order not placed) when a
HARD article is violated, keeping an audited trail of the block. In a correctly-built system it
permits every order — its value is defense-in-depth: any code path that ever formed an
overnight / out-of-scope / naked-leg / direct-to-exchange order is caught and stopped. PURE
(no I/O); the persistent forensic audit store is the queued incident-post-mortem branch.
"""

from __future__ import annotations

from nse_algo_trader.conscience.constitutional_core import (
    ConstitutionalCore,
    ConstitutionalVerdict,
    ProposedTradingAction,
)

_RECENT_BLOCKS_KEPT = 20


class ConstitutionalReferee:
    """Adjudicates proposed orders against the constitution and blocks the non-compliant ones."""

    def __init__(self, core: ConstitutionalCore | None = None) -> None:
        self._core = core or ConstitutionalCore()
        self.permitted_count = 0
        self.blocked_count = 0
        self._recent_blocks: list[ConstitutionalVerdict] = []

    def adjudicate_order(self, action: ProposedTradingAction) -> bool:
        """True (permit) when the action is constitutionally compliant; False (block) otherwise —
        the caller must NOT place a blocked order. A block is recorded for the audit trail."""
        verdict = self._core.review_action(action)
        if verdict.permitted:
            self.permitted_count += 1
            return True
        self.blocked_count += 1
        self._recent_blocks.append(verdict)
        del self._recent_blocks[:-_RECENT_BLOCKS_KEPT]
        return False

    @property
    def recent_blocks(self) -> tuple[ConstitutionalVerdict, ...]:
        return tuple(self._recent_blocks)

    @property
    def orders_adjudicated(self) -> int:
        return self.permitted_count + self.blocked_count
