"""Broker-truth state reconciler — L3 ops floor, crash-safety trio part C.

Design doc: ``docs/research/168_L3_ops_floor_crash_safety.md`` (§3.C).

On restart (or periodically) the bot must not trust its own memory about what
is open. A crash mid-session can leave three kinds of divergence between the
bot's BELIEF and reality:

* the bot thinks a position is open that the broker shows flat (a fill the bot
  recorded but the broker never actually took, OR a broker-side close/square-off
  the bot missed while it was down) — ``orphan_local``;
* the broker holds a position the bot has no record of (an order that filled
  after the bot crashed but before it persisted, or a manual/broker action) —
  ``unknown_broker``; this MUST be adopted or flattened, never ignored;
* both sides hold the instrument but at a different signed quantity (a partial
  fill, a missed leg, or a full sign flip) — ``quantity_mismatch``.

The BROKER is the source of truth. This engine takes plain position snapshots
from both sides plus the write-ahead-log's still-pending intent ids, and emits
a :class:`ReconciliationReport` classifying every instrument, each discrepancy
carrying a conservative suggested :class:`CorrectiveAction`. It NEVER decides to
trade: unknown-broker and quantity-mismatch default to ``ALERT_HUMAN`` so a
human confirms before any adopt/flatten runs against live capital.

Inputs are deliberately plain value objects (:class:`PositionSnapshot`) that the
integrator maps into from the paper/live loop's ``OpenPaperPosition`` shape or
the broker client's positions payload; this module depends on neither, so it is
reusable and trivially testable.

Sourcing (Rule O.1) — queries + tier-labelled rejects recorded in the task's
final report. Summary: no reusable part exists. ``nautilus_trader`` reconciliation
is welded to its own ExecutionEngine/Cache (reconcile only surfaces in
venue-specific live exec testers) — framework-coupled, wrong shape for one pure
diff function. ``deepdiff`` / ``dictdiffer`` are generic structural diff libs
with zero model of signed position quantity or long/short side semantics (no test
covers reconciliation). ``ib_insync`` is archived upstream (tier-1). Built bespoke.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum

__all__ = [
    "PositionSnapshot",
    "DiscrepancyKind",
    "CorrectiveAction",
    "PositionDiscrepancy",
    "ReconciliationReport",
    "reconcile",
    "DEFAULT_CORRECTIVE_ACTIONS",
]


@dataclass(frozen=True)
class PositionSnapshot:
    """A single instrument's net position on one side of the reconciliation.

    ``net_quantity`` is SIGNED and always in **shares, never lots** (the repo
    convention, see ``broker_oms/order_types.py``): ``+`` long, ``-`` short,
    ``0`` flat. The instrument is identified only by its integer
    ``instrument_token`` so this stays decoupled from the ``Instrument`` model.
    """

    instrument_token: int
    net_quantity: int  # signed shares: +long / -short / 0 flat

    def __post_init__(self) -> None:
        if self.instrument_token < 0:
            raise ValueError("instrument_token must be a non-negative integer")


class DiscrepancyKind(str, Enum):
    """How one instrument's local belief relates to broker truth."""

    MATCHED = "matched"  # same non-zero signed quantity on both sides
    ORPHAN_LOCAL = "orphan_local"  # bot holds it, broker flat/absent
    UNKNOWN_BROKER = "unknown_broker"  # broker holds it, bot unaware
    QUANTITY_MISMATCH = "quantity_mismatch"  # both hold it, different signed qty


class CorrectiveAction(str, Enum):
    """Suggested remediation for a discrepancy. Conservative by construction —
    nothing here auto-trades; ``ADOPT_BROKER_TRUTH`` / ``FLATTEN_UNKNOWN`` are
    the *recommended human decision*, surfaced for confirmation, not executed."""

    NONE = "none"  # matched — no action
    ADOPT_BROKER_TRUTH = "adopt_broker_truth"  # align local belief to broker
    FLATTEN_UNKNOWN = "flatten_unknown"  # square off a broker position we disown
    ALERT_HUMAN = "alert_human"  # stop, surface, wait for a person
    INVESTIGATE = "investigate"  # reconcile against the WAL / fills before acting


#: The conservative default action per discrepancy class. Exposed (and unit
#: tested) so the policy is auditable in one place. ``unknown_broker`` and
#: ``quantity_mismatch`` deliberately map to ``ALERT_HUMAN`` — a human confirms
#: before any live adopt/flatten. ``orphan_local`` maps to ``INVESTIGATE``: the
#: bot's phantom belief should be resolved against the WAL/fills (was it a fill
#: the broker never took, or a close the bot missed?) before it is dropped.
DEFAULT_CORRECTIVE_ACTIONS: dict[DiscrepancyKind, CorrectiveAction] = {
    DiscrepancyKind.MATCHED: CorrectiveAction.NONE,
    DiscrepancyKind.ORPHAN_LOCAL: CorrectiveAction.INVESTIGATE,
    DiscrepancyKind.UNKNOWN_BROKER: CorrectiveAction.ALERT_HUMAN,
    DiscrepancyKind.QUANTITY_MISMATCH: CorrectiveAction.ALERT_HUMAN,
}


@dataclass(frozen=True)
class PositionDiscrepancy:
    """One instrument's reconciliation outcome, including matched positions.

    ``local_net_quantity`` / ``broker_net_quantity`` are the AGGREGATED signed
    share counts each side reported for this token (0 == flat/absent).
    """

    instrument_token: int
    kind: DiscrepancyKind
    local_net_quantity: int
    broker_net_quantity: int
    suggested_action: CorrectiveAction
    detail: str

    @property
    def is_discrepancy(self) -> bool:
        """True for anything other than a clean match."""
        return self.kind is not DiscrepancyKind.MATCHED


@dataclass(frozen=True)
class ReconciliationReport:
    """The full diff of bot belief vs broker truth for one reconciliation pass.

    Every instrument seen on either side lands in exactly one of the four lists.
    ``unresolved_pending_intents`` carries the WAL client-order-ids that were
    still pending at restart (neither confirmed placed/filled nor rejected) — an
    in-flight intent whose fate is unknown and must be resolved by probing the
    broker before the bot resumes.
    """

    matched: tuple[PositionDiscrepancy, ...] = ()
    orphan_local: tuple[PositionDiscrepancy, ...] = ()
    unknown_broker: tuple[PositionDiscrepancy, ...] = ()
    quantity_mismatch: tuple[PositionDiscrepancy, ...] = ()
    unresolved_pending_intents: tuple[str, ...] = ()
    #: Non-fatal notes, e.g. a token that appeared more than once on one side
    #: (the quantities were aggregated) or a snapshot with net_quantity == 0.
    aggregation_warnings: tuple[str, ...] = field(default=())

    @property
    def discrepancies(self) -> tuple[PositionDiscrepancy, ...]:
        """Every non-matched outcome, in a single stable-ordered tuple."""
        return (
            *self.orphan_local,
            *self.unknown_broker,
            *self.quantity_mismatch,
        )

    @property
    def is_clean(self) -> bool:
        """True iff there are NO position discrepancies AND no unresolved WAL
        intents — the only state in which the bot may resume trading without a
        human decision. (Aggregation warnings alone do not make it dirty, but
        they are still surfaced.)"""
        return not self.discrepancies and not self.unresolved_pending_intents

    @property
    def requires_human_attention(self) -> bool:
        """True iff any suggested action is ``ALERT_HUMAN`` (or an intent is
        unresolved) — the dashboard/alerting gate."""
        if self.unresolved_pending_intents:
            return True
        return any(
            d.suggested_action is CorrectiveAction.ALERT_HUMAN
            for d in self.discrepancies
        )

    def summary(self) -> dict[str, int]:
        """Counts per class for a dashboard surface (Rule N)."""
        return {
            "matched": len(self.matched),
            "orphan_local": len(self.orphan_local),
            "unknown_broker": len(self.unknown_broker),
            "quantity_mismatch": len(self.quantity_mismatch),
            "unresolved_pending_intents": len(self.unresolved_pending_intents),
            "aggregation_warnings": len(self.aggregation_warnings),
            "total_discrepancies": len(self.discrepancies),
        }

    def human_readable(self) -> str:
        """A compact multi-line report for logs / a Telegram alert."""
        lines: list[str] = []
        if self.is_clean:
            lines.append(
                "RECONCILIATION CLEAN — local belief matches broker truth "
                f"({len(self.matched)} matched position(s)), no unresolved intents."
            )
        else:
            lines.append(
                "RECONCILIATION DIRTY — "
                f"{len(self.discrepancies)} discrepancy(ies), "
                f"{len(self.unresolved_pending_intents)} unresolved intent(s)."
            )
        counts = self.summary()
        lines.append(
            "  counts: matched={matched} orphan_local={orphan_local} "
            "unknown_broker={unknown_broker} "
            "quantity_mismatch={quantity_mismatch}".format(**counts)
        )
        for discrepancy in self.discrepancies:
            lines.append(
                f"  [{discrepancy.kind.value}] token={discrepancy.instrument_token} "
                f"local={discrepancy.local_net_quantity:+d} "
                f"broker={discrepancy.broker_net_quantity:+d} "
                f"-> {discrepancy.suggested_action.value}: {discrepancy.detail}"
            )
        if self.unresolved_pending_intents:
            lines.append(
                "  unresolved WAL intents (probe broker before resume): "
                + ", ".join(self.unresolved_pending_intents)
            )
        for warning in self.aggregation_warnings:
            lines.append(f"  note: {warning}")
        return "\n".join(lines)


def _aggregate_by_token(
    snapshots: list[PositionSnapshot],
    side_label: str,
    warnings: list[str],
) -> dict[int, int]:
    """Collapse a side's snapshots to one signed net-quantity per token.

    A token appearing more than once is summed (a legitimate representation of
    several legs/lots the caller did not pre-net) and a warning is recorded so
    the aggregation is never silent. Zero-quantity snapshots are noted and drop
    out as flat.
    """
    seen_token_count: dict[int, int] = defaultdict(int)
    net_by_token: dict[int, int] = defaultdict(int)
    for snapshot in snapshots:
        seen_token_count[snapshot.instrument_token] += 1
        net_by_token[snapshot.instrument_token] += snapshot.net_quantity
        if snapshot.net_quantity == 0:
            warnings.append(
                f"{side_label} token={snapshot.instrument_token} snapshot had "
                "net_quantity=0 (treated as flat)"
            )
    for token, count in seen_token_count.items():
        if count > 1:
            warnings.append(
                f"{side_label} token={token} appeared {count} times "
                f"(aggregated to net_quantity={net_by_token[token]:+d})"
            )
    # Drop tokens that net to flat — they are not positions.
    return {
        token: net for token, net in net_by_token.items() if net != 0
    }


def reconcile(
    local_positions: list[PositionSnapshot],
    broker_positions: list[PositionSnapshot],
    pending_intent_ids: list[str] | None = None,
) -> ReconciliationReport:
    """Reconcile the bot's believed positions against broker truth.

    Args:
        local_positions: what the bot believes is open (its own memory / DB).
        broker_positions: the broker's reported net positions — the SOURCE OF
            TRUTH.
        pending_intent_ids: WAL client-order-ids still pending at reconciliation
            time (unacked in-flight intents to resolve). ``None``/empty == none.

    Returns:
        A :class:`ReconciliationReport` classifying every instrument and carrying
        a conservative suggested corrective action per discrepancy. This function
        is pure — it computes and reports, it never places or cancels orders.
    """
    warnings: list[str] = []
    local_net = _aggregate_by_token(local_positions, "local", warnings)
    broker_net = _aggregate_by_token(broker_positions, "broker", warnings)

    matched: list[PositionDiscrepancy] = []
    orphan_local: list[PositionDiscrepancy] = []
    unknown_broker: list[PositionDiscrepancy] = []
    quantity_mismatch: list[PositionDiscrepancy] = []

    for token in sorted(set(local_net) | set(broker_net)):
        local_qty = local_net.get(token, 0)
        broker_qty = broker_net.get(token, 0)

        if local_qty == broker_qty:
            # Both non-zero and equal (a flat/flat token never enters this loop
            # because _aggregate_by_token dropped it from both maps).
            matched.append(
                _build(
                    token,
                    DiscrepancyKind.MATCHED,
                    local_qty,
                    broker_qty,
                    detail=(
                        f"both sides agree at {local_qty:+d} shares"
                    ),
                )
            )
        elif local_qty != 0 and broker_qty == 0:
            orphan_local.append(
                _build(
                    token,
                    DiscrepancyKind.ORPHAN_LOCAL,
                    local_qty,
                    broker_qty,
                    detail=(
                        f"bot believes {local_qty:+d} shares open but broker is "
                        "flat — a fill the bot recorded that the broker never "
                        "took, or a broker-side close the bot missed while down"
                    ),
                )
            )
        elif local_qty == 0 and broker_qty != 0:
            unknown_broker.append(
                _build(
                    token,
                    DiscrepancyKind.UNKNOWN_BROKER,
                    local_qty,
                    broker_qty,
                    detail=(
                        f"broker holds {broker_qty:+d} shares the bot has no "
                        "record of — must be adopted or flattened, never ignored"
                    ),
                )
            )
        else:
            # Both non-zero, different signed quantity (includes a full sign
            # flip, e.g. +100 local vs -100 broker).
            detail = (
                f"bot believes {local_qty:+d} shares, broker holds "
                f"{broker_qty:+d} — partial fill / missed leg"
            )
            if (local_qty > 0) != (broker_qty > 0):
                detail += " (SIGN FLIP: long/short disagree)"
            quantity_mismatch.append(
                _build(
                    token,
                    DiscrepancyKind.QUANTITY_MISMATCH,
                    local_qty,
                    broker_qty,
                    detail=detail,
                )
            )

    return ReconciliationReport(
        matched=tuple(matched),
        orphan_local=tuple(orphan_local),
        unknown_broker=tuple(unknown_broker),
        quantity_mismatch=tuple(quantity_mismatch),
        unresolved_pending_intents=tuple(pending_intent_ids or ()),
        aggregation_warnings=tuple(warnings),
    )


def _build(
    instrument_token: int,
    kind: DiscrepancyKind,
    local_net_quantity: int,
    broker_net_quantity: int,
    detail: str,
) -> PositionDiscrepancy:
    """Construct a discrepancy with the policy-default corrective action."""
    return PositionDiscrepancy(
        instrument_token=instrument_token,
        kind=kind,
        local_net_quantity=local_net_quantity,
        broker_net_quantity=broker_net_quantity,
        suggested_action=DEFAULT_CORRECTIVE_ACTIONS[kind],
        detail=detail,
    )
