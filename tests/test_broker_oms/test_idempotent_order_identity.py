"""Unit + property + adversarial tests for deterministic client order ids.

The core guarantee under test: the SAME logical order intent (plus the
same trading-day session key) always hashes to the SAME id, in this
process or a fresh one after a crash-restart — and clearly different
intents get different ids. That is what lets a write-ahead log suppress a
duplicate Kite placement (Kite has no native idempotency key).
"""

import hashlib
import json
from dataclasses import replace
from datetime import date

import pytest

from nse_algo_trader.broker_oms.idempotent_order_identity import (
    BROKER_TAG_LENGTH,
    ClientOrderIdentity,
    client_order_identity,
    deterministic_broker_tag,
    deterministic_client_order_id,
    session_key_for_date,
)
from nse_algo_trader.broker_oms.order_types import (
    OrderIntent,
    OrderSide,
    OrderType,
    OrderVariety,
)

from .broker_oms_test_fixtures import CASH_INSTRUMENT, make_put_instrument

_SESSION_KEY = session_key_for_date(date(2026, 7, 22))


def _limit_buy(**overrides: object) -> OrderIntent:
    base = OrderIntent(
        instrument=CASH_INSTRUMENT,
        side=OrderSide.BUY,
        quantity=10,
        strategy_tag="orb_v1",
        order_type=OrderType.LIMIT,
        limit_price=100.0,
    )
    return replace(base, **overrides)  # type: ignore[arg-type]


# --- Determinism -------------------------------------------------------------


def test_same_intent_same_session_key_yields_same_id() -> None:
    intent = _limit_buy()
    assert deterministic_client_order_id(
        intent, _SESSION_KEY
    ) == deterministic_client_order_id(intent, _SESSION_KEY)
    assert deterministic_broker_tag(
        intent, _SESSION_KEY
    ) == deterministic_broker_tag(intent, _SESSION_KEY)


def test_equal_but_distinct_intent_objects_yield_same_id() -> None:
    """Value-identity, not object-identity: two separately constructed but
    field-equal intents must hash the same (proves no reliance on id())."""
    assert deterministic_client_order_id(
        _limit_buy(), _SESSION_KEY
    ) == deterministic_client_order_id(_limit_buy(), _SESSION_KEY)


def test_id_is_stable_against_independently_computed_digest() -> None:
    """Recompute the expected BLAKE2b digest from scratch, using the
    documented canonical scheme, and assert equality.

    This is the anti-``hash()`` proof: Python's salted ``hash()`` would
    differ from an independently computed cryptographic digest and would
    vary by PYTHONHASHSEED. A keyed BLAKE2b over a canonical serialization
    does not.
    """
    intent = _limit_buy()
    expected_mapping = {
        "instrument_token": ["num", "408065"],
        "trading_symbol": ["str", "INFY"],
        "exchange_segment": ["str", "NSE_CASH"],
        "side": ["str", "buy"],
        "quantity": ["num", "10"],
        "strategy_tag": ["str", "orb_v1"],
        "order_type": ["str", "limit"],
        "limit_price": ["num", "100"],
        "trigger_price": ["null", ""],
        "variety": ["str", "regular"],
        "session_key": ["str", "2026-07-22"],
    }
    canonical = json.dumps(
        expected_mapping, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    expected_hex = hashlib.blake2b(
        canonical, digest_size=32, person=b"nse-oms-idem/v1"
    ).hexdigest()
    assert deterministic_client_order_id(intent, _SESSION_KEY) == expected_hex


def test_golden_values_are_frozen_across_interpreters() -> None:
    """Hard-coded golden id/tag. If these ever change, the WAL keys of every
    previously-logged order silently break — so this pins them. Computing
    them here (a fresh interpreter each pytest run) and matching a constant
    proves cross-process stability."""
    identity = client_order_identity(_limit_buy(), _SESSION_KEY)
    assert identity.full_hex_id == (
        "e545726ff97531a1bf036a603be7f6f9eb8462b03672af37395445c393d25207"
    )
    assert identity.broker_tag == "sMlpQW1uuvHxVtWIe0U7"


def test_client_order_identity_matches_standalone_functions() -> None:
    intent = _limit_buy()
    identity = client_order_identity(intent, _SESSION_KEY)
    assert isinstance(identity, ClientOrderIdentity)
    assert identity.full_hex_id == deterministic_client_order_id(intent, _SESSION_KEY)
    assert identity.broker_tag == deterministic_broker_tag(intent, _SESSION_KEY)


# --- Sensitivity: different identity -> different id -------------------------


@pytest.mark.parametrize(
    "changed",
    [
        {"quantity": 11},
        {"side": OrderSide.SELL},
        {"strategy_tag": "orb_v2"},
        {"limit_price": 100.05},
        {"variety": OrderVariety.AFTER_MARKET},
    ],
)
def test_changing_any_identifying_field_changes_the_id(
    changed: dict[str, object],
) -> None:
    base_id = deterministic_client_order_id(_limit_buy(), _SESSION_KEY)
    changed_id = deterministic_client_order_id(_limit_buy(**changed), _SESSION_KEY)
    assert base_id != changed_id


def test_changing_instrument_changes_the_id() -> None:
    cash_id = deterministic_client_order_id(_limit_buy(), _SESSION_KEY)
    option_intent = _limit_buy(instrument=make_put_instrument(24000))
    assert cash_id != deterministic_client_order_id(option_intent, _SESSION_KEY)


def test_changing_trigger_price_changes_stop_order_id() -> None:
    stop_a = OrderIntent(
        instrument=CASH_INSTRUMENT, side=OrderSide.SELL, quantity=10,
        strategy_tag="orb_v1", order_type=OrderType.STOP_MARKET, trigger_price=95.0,
    )
    stop_b = replace(stop_a, trigger_price=94.0)
    assert deterministic_client_order_id(
        stop_a, _SESSION_KEY
    ) != deterministic_client_order_id(stop_b, _SESSION_KEY)


def test_different_session_key_changes_the_id() -> None:
    intent = _limit_buy()
    id_day1 = deterministic_client_order_id(
        intent, session_key_for_date(date(2026, 7, 22))
    )
    id_day2 = deterministic_client_order_id(
        intent, session_key_for_date(date(2026, 7, 23))
    )
    assert id_day1 != id_day2


# --- Numeric / None robustness ----------------------------------------------


def test_none_price_distinguished_from_zero_price() -> None:
    """A null limit price must NOT collide with a zero one."""
    market_no_price = OrderIntent(
        instrument=CASH_INSTRUMENT, side=OrderSide.BUY, quantity=10,
        strategy_tag="orb_v1", order_type=OrderType.MARKET, limit_price=None,
    )
    zero_price = replace(market_no_price, limit_price=0.0)
    assert deterministic_client_order_id(
        market_no_price, _SESSION_KEY
    ) != deterministic_client_order_id(zero_price, _SESSION_KEY)


def test_float_and_int_price_do_not_drift() -> None:
    """100.0, 100, and 100.00 are the same price -> the same id."""
    id_float = deterministic_client_order_id(_limit_buy(limit_price=100.0), _SESSION_KEY)
    id_int = deterministic_client_order_id(_limit_buy(limit_price=100), _SESSION_KEY)
    id_trailing = deterministic_client_order_id(
        _limit_buy(limit_price=100.00), _SESSION_KEY
    )
    assert id_float == id_int == id_trailing


def test_fractional_price_is_preserved() -> None:
    assert deterministic_client_order_id(
        _limit_buy(limit_price=100.5), _SESSION_KEY
    ) != deterministic_client_order_id(_limit_buy(limit_price=100.0), _SESSION_KEY)


# --- Broker tag shape --------------------------------------------------------


def test_broker_tag_fits_kite_limit_and_is_alphanumeric() -> None:
    for intent in (
        _limit_buy(),
        _limit_buy(instrument=make_put_instrument(24000)),
        OrderIntent(
            instrument=CASH_INSTRUMENT, side=OrderSide.SELL, quantity=1,
            strategy_tag="x", order_type=OrderType.MARKET,
        ),
    ):
        tag = deterministic_broker_tag(intent, _SESSION_KEY)
        assert len(tag) == BROKER_TAG_LENGTH <= 20
        assert tag.isalnum()
        assert tag.isascii()


# --- Adversarial: collision resistance in the truncated tag form ------------


def test_many_distinct_intents_do_not_collide_in_tag_form() -> None:
    """A reasonable sample of clearly-different intents must map to distinct
    tags even in the 20-char truncated form."""
    tags: set[str] = set()
    full_ids: set[str] = set()
    sample_size = 0
    for quantity in range(1, 26):
        for price_paise in range(40):
            for side in (OrderSide.BUY, OrderSide.SELL):
                intent = _limit_buy(
                    quantity=quantity,
                    limit_price=round(100.0 + price_paise * 0.05, 2),
                    side=side,
                )
                tags.add(deterministic_broker_tag(intent, _SESSION_KEY))
                full_ids.add(deterministic_client_order_id(intent, _SESSION_KEY))
                sample_size += 1
    assert sample_size == 25 * 40 * 2
    assert len(full_ids) == sample_size  # full ids never collide
    assert len(tags) == sample_size  # nor does the truncated tag


def test_field_order_of_construction_does_not_affect_hash() -> None:
    """Building the same intent via different keyword orders is irrelevant —
    the canonical serialization sorts by field name."""
    a = OrderIntent(
        instrument=CASH_INSTRUMENT, side=OrderSide.BUY, quantity=10,
        strategy_tag="orb_v1", order_type=OrderType.LIMIT, limit_price=100.0,
    )
    b = OrderIntent(
        limit_price=100.0, order_type=OrderType.LIMIT, strategy_tag="orb_v1",
        quantity=10, side=OrderSide.BUY, instrument=CASH_INSTRUMENT,
    )
    assert deterministic_client_order_id(
        a, _SESSION_KEY
    ) == deterministic_client_order_id(b, _SESSION_KEY)
