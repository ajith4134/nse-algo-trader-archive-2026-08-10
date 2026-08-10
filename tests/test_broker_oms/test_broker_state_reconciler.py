"""Tests for the broker-truth state reconciler (L3 crash-safety trio, part C).

Covers: both-flat clean; exact match; each discrepancy class incl. sign flip;
a mixed multi-instrument report; pending WAL intents surfaced; conservative
corrective-action defaults; duplicate-token aggregation and zero-qty handling;
and the is_clean / summary / human_readable surfaces. Plus property-based
invariants over random position universes.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from nse_algo_trader.broker_oms.broker_state_reconciler import (
    DEFAULT_CORRECTIVE_ACTIONS,
    CorrectiveAction,
    DiscrepancyKind,
    PositionSnapshot,
    ReconciliationReport,
    reconcile,
)


def _snap(token: int, qty: int) -> PositionSnapshot:
    return PositionSnapshot(instrument_token=token, net_quantity=qty)


# --------------------------------------------------------------------------- #
# Clean paths                                                                 #
# --------------------------------------------------------------------------- #


def test_both_flat_is_clean() -> None:
    report = reconcile([], [])
    assert report.is_clean is True
    assert report.summary()["total_discrepancies"] == 0
    assert report.discrepancies == ()
    assert "CLEAN" in report.human_readable()


def test_exact_match_is_clean_and_matched() -> None:
    report = reconcile([_snap(101, 100)], [_snap(101, 100)])
    assert report.is_clean is True
    assert len(report.matched) == 1
    match = report.matched[0]
    assert match.kind is DiscrepancyKind.MATCHED
    assert match.suggested_action is CorrectiveAction.NONE
    assert match.is_discrepancy is False
    assert report.summary()["matched"] == 1


def test_flat_on_both_sides_via_zero_qty_is_clean() -> None:
    # A token reported explicitly as net 0 on both sides is flat, not a match.
    report = reconcile([_snap(7, 0)], [_snap(7, 0)])
    assert report.is_clean is True
    assert report.matched == ()
    assert report.summary()["aggregation_warnings"] == 2  # one per side


# --------------------------------------------------------------------------- #
# Discrepancy classes                                                         #
# --------------------------------------------------------------------------- #


def test_orphan_local_bot_thinks_open_broker_flat() -> None:
    report = reconcile([_snap(200, 50)], [])
    assert report.is_clean is False
    assert len(report.orphan_local) == 1
    orphan = report.orphan_local[0]
    assert orphan.kind is DiscrepancyKind.ORPHAN_LOCAL
    assert orphan.local_net_quantity == 50
    assert orphan.broker_net_quantity == 0
    assert orphan.suggested_action is CorrectiveAction.INVESTIGATE


def test_unknown_broker_must_not_be_ignored_and_alerts_human() -> None:
    report = reconcile([], [_snap(300, -75)])
    assert report.is_clean is False
    assert len(report.unknown_broker) == 1
    unknown = report.unknown_broker[0]
    assert unknown.kind is DiscrepancyKind.UNKNOWN_BROKER
    assert unknown.local_net_quantity == 0
    assert unknown.broker_net_quantity == -75
    # Conservative: never silently adopt/flatten — a human decides.
    assert unknown.suggested_action is CorrectiveAction.ALERT_HUMAN
    assert report.requires_human_attention is True


def test_quantity_mismatch_partial_fill() -> None:
    report = reconcile([_snap(400, 100)], [_snap(400, 60)])
    assert len(report.quantity_mismatch) == 1
    mismatch = report.quantity_mismatch[0]
    assert mismatch.kind is DiscrepancyKind.QUANTITY_MISMATCH
    assert mismatch.local_net_quantity == 100
    assert mismatch.broker_net_quantity == 60
    assert mismatch.suggested_action is CorrectiveAction.ALERT_HUMAN
    assert "SIGN FLIP" not in mismatch.detail


def test_sign_flip_is_a_mismatch_not_a_match() -> None:
    # +100 local vs -100 broker: same magnitude, opposite side — a mismatch.
    report = reconcile([_snap(500, 100)], [_snap(500, -100)])
    assert report.matched == ()
    assert len(report.quantity_mismatch) == 1
    mismatch = report.quantity_mismatch[0]
    assert mismatch.suggested_action is CorrectiveAction.ALERT_HUMAN
    assert "SIGN FLIP" in mismatch.detail


# --------------------------------------------------------------------------- #
# Pending intents                                                             #
# --------------------------------------------------------------------------- #


def test_pending_intents_surface_and_break_cleanliness() -> None:
    # Positions all match, but an unacked WAL intent means NOT clean.
    report = reconcile(
        [_snap(101, 100)],
        [_snap(101, 100)],
        pending_intent_ids=["intent-abc", "intent-def"],
    )
    assert report.matched  # positions agree
    assert report.is_clean is False
    assert report.unresolved_pending_intents == ("intent-abc", "intent-def")
    assert report.requires_human_attention is True
    assert report.summary()["unresolved_pending_intents"] == 2
    assert "intent-abc" in report.human_readable()


def test_pending_intents_none_defaults_to_empty() -> None:
    report = reconcile([], [], pending_intent_ids=None)
    assert report.unresolved_pending_intents == ()
    assert report.is_clean is True


# --------------------------------------------------------------------------- #
# Mixed multi-instrument report                                               #
# --------------------------------------------------------------------------- #


def test_mixed_multi_instrument_report() -> None:
    local = [
        _snap(1, 100),   # matched
        _snap(2, 50),    # orphan_local (broker flat)
        _snap(4, 100),   # quantity_mismatch
    ]
    broker = [
        _snap(1, 100),   # matched
        _snap(3, -30),   # unknown_broker
        _snap(4, 40),    # quantity_mismatch
    ]
    report = reconcile(local, broker, pending_intent_ids=["x"])

    assert report.summary() == {
        "matched": 1,
        "orphan_local": 1,
        "unknown_broker": 1,
        "quantity_mismatch": 1,
        "unresolved_pending_intents": 1,
        "aggregation_warnings": 0,
        "total_discrepancies": 3,
    }
    assert report.is_clean is False
    # Every discrepancy token accounted for, none lost.
    disc_tokens = {d.instrument_token for d in report.discrepancies}
    assert disc_tokens == {2, 3, 4}


# --------------------------------------------------------------------------- #
# Corrective-action policy                                                    #
# --------------------------------------------------------------------------- #


def test_corrective_action_defaults_are_conservative() -> None:
    # The single source of truth for the policy — unknown/mismatch alert a human.
    assert DEFAULT_CORRECTIVE_ACTIONS[DiscrepancyKind.MATCHED] is (
        CorrectiveAction.NONE
    )
    assert DEFAULT_CORRECTIVE_ACTIONS[DiscrepancyKind.ORPHAN_LOCAL] is (
        CorrectiveAction.INVESTIGATE
    )
    assert DEFAULT_CORRECTIVE_ACTIONS[DiscrepancyKind.UNKNOWN_BROKER] is (
        CorrectiveAction.ALERT_HUMAN
    )
    assert DEFAULT_CORRECTIVE_ACTIONS[DiscrepancyKind.QUANTITY_MISMATCH] is (
        CorrectiveAction.ALERT_HUMAN
    )
    # No default ever silently trades.
    for action in DEFAULT_CORRECTIVE_ACTIONS.values():
        assert action in {
            CorrectiveAction.NONE,
            CorrectiveAction.INVESTIGATE,
            CorrectiveAction.ALERT_HUMAN,
        }


# --------------------------------------------------------------------------- #
# Robustness: duplicate tokens, zero qty, aggregation                         #
# --------------------------------------------------------------------------- #


def test_duplicate_local_token_is_aggregated_with_warning() -> None:
    # Two legs of the same token net to a single position.
    report = reconcile([_snap(9, 40), _snap(9, 60)], [_snap(9, 100)])
    assert len(report.matched) == 1
    assert report.matched[0].local_net_quantity == 100
    assert any("appeared 2 times" in w for w in report.aggregation_warnings)


def test_duplicate_tokens_can_net_to_flat() -> None:
    # +50 and -50 on the bot side net to flat; broker also flat -> clean.
    report = reconcile([_snap(9, 50), _snap(9, -50)], [])
    assert report.is_clean is True
    assert report.matched == ()
    assert report.orphan_local == ()


def test_zero_qty_entry_treated_as_flat_but_noted() -> None:
    report = reconcile([_snap(11, 0)], [_snap(11, 100)])
    # Local net is flat -> broker's 100 is unknown_broker, not a mismatch.
    assert len(report.unknown_broker) == 1
    assert report.quantity_mismatch == ()
    assert any("net_quantity=0" in w for w in report.aggregation_warnings)


def test_snapshot_rejects_negative_token() -> None:
    import pytest

    with pytest.raises(ValueError):
        PositionSnapshot(instrument_token=-1, net_quantity=10)


# --------------------------------------------------------------------------- #
# Surface correctness                                                         #
# --------------------------------------------------------------------------- #


def test_human_readable_lists_every_discrepancy() -> None:
    report = reconcile([_snap(2, 50)], [_snap(3, -30)])
    text = report.human_readable()
    assert "DIRTY" in text
    assert "orphan_local" in text
    assert "unknown_broker" in text
    assert "token=2" in text
    assert "token=3" in text


def test_summary_counts_match_list_lengths() -> None:
    report = reconcile(
        [_snap(1, 10), _snap(2, 10)],
        [_snap(1, 10), _snap(3, 10)],
    )
    summary = report.summary()
    assert summary["matched"] == len(report.matched)
    assert summary["orphan_local"] == len(report.orphan_local)
    assert summary["unknown_broker"] == len(report.unknown_broker)
    assert summary["quantity_mismatch"] == len(report.quantity_mismatch)
    assert summary["total_discrepancies"] == len(report.discrepancies)


# --------------------------------------------------------------------------- #
# Property-based invariants                                                   #
# --------------------------------------------------------------------------- #


_positions = st.lists(
    st.builds(
        _snap,
        st.integers(min_value=0, max_value=20),
        st.integers(min_value=-500, max_value=500),
    ),
    max_size=30,
)


@given(local=_positions, broker=_positions)
def test_every_token_classified_exactly_once(
    local: list[PositionSnapshot], broker: list[PositionSnapshot]
) -> None:
    report = reconcile(local, broker)
    all_entries = (
        *report.matched,
        *report.orphan_local,
        *report.unknown_broker,
        *report.quantity_mismatch,
    )
    tokens = [e.instrument_token for e in all_entries]
    # No token appears in two classes (each netted token classified once).
    assert len(tokens) == len(set(tokens))

    # The classified tokens are exactly the union of non-flat netted tokens.
    def _net(snaps: list[PositionSnapshot]) -> set[int]:
        acc: dict[int, int] = {}
        for s in snaps:
            acc[s.instrument_token] = acc.get(s.instrument_token, 0) + s.net_quantity
        return {t for t, q in acc.items() if q != 0}

    assert set(tokens) == _net(local) | _net(broker)


@given(local=_positions, broker=_positions)
def test_is_clean_iff_only_matches(
    local: list[PositionSnapshot], broker: list[PositionSnapshot]
) -> None:
    report = reconcile(local, broker)
    only_matches = (
        not report.orphan_local
        and not report.unknown_broker
        and not report.quantity_mismatch
    )
    assert report.is_clean is only_matches


@given(local=_positions, broker=_positions)
def test_matched_means_equal_nonzero_quantities(
    local: list[PositionSnapshot], broker: list[PositionSnapshot]
) -> None:
    report = reconcile(local, broker)
    for match in report.matched:
        assert match.local_net_quantity == match.broker_net_quantity
        assert match.local_net_quantity != 0
        assert match.suggested_action is CorrectiveAction.NONE


@given(local=_positions, broker=_positions)
def test_report_is_a_reconciliation_report(
    local: list[PositionSnapshot], broker: list[PositionSnapshot]
) -> None:
    report = reconcile(local, broker)
    assert isinstance(report, ReconciliationReport)
    # human_readable never raises regardless of content.
    assert isinstance(report.human_readable(), str)
