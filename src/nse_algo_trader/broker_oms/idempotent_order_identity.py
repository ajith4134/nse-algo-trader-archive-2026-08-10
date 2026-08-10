"""Deterministic, idempotent client-order identity for the Kite OMS.

Zerodha Kite Connect has NO native idempotency key: if a `place_order`
call is retried (network timeout, process crash-restart mid-flight) the
exchange happily accepts and double-fills the *same logical order*. There
is no server-side "I've seen this request" guard.

This module manufactures one deterministically. Given an `OrderIntent`
and a `session_key` (normally the trading date), it derives a **stable,
collision-resistant client order id**: the SAME logical intent always
hashes to the SAME id, in this process or a fresh one after a restart, on
any machine. A write-ahead log (built separately, `docs/research/168`)
keys on that id to recognise and suppress a duplicate placement before it
reaches the broker.

Two forms are produced (`ClientOrderIdentity`):
  * `full_hex_id`   — 64 hex chars (256-bit BLAKE2b), the WAL primary key.
  * `broker_tag`    — 20 alphanumeric chars, carried in Kite's `tag`
                      field (Kite hard-caps tags at 20 chars), so the
                      broker's own order record echoes the idempotency key
                      back on reconciliation.

Why not Python's `hash()` / a random uuid:
  * `hash()` is PYTHONHASHSEED-salted for str/bytes and differs across
    processes — it cannot survive a crash-restart, defeating the purpose.
  * a uuid4 is fresh every call — a retry would mint a NEW id and the WAL
    would never see the duplicate.
Only a keyed cryptographic digest over a canonical serialization of the
identifying fields is stable across processes AND unique per intent.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from nse_algo_trader.broker_oms.order_types import OrderIntent

# --- Tunables (domain constants, not magic thresholds) -----------------------

# Kite Connect caps the order `tag` field at 20 characters (see
# kite_broker_client._KITE_TAG_MAX_LENGTH); the broker_tag must fit it.
BROKER_TAG_LENGTH = 20

# 256-bit digest -> 64 hex chars. Ample collision resistance for the WAL key.
_FULL_DIGEST_SIZE_BYTES = 32

# BLAKE2b personalization: domain-separates THIS hash from any other
# BLAKE2b use in the codebase, so an identical byte payload hashed for a
# different purpose can never collide with an order id. Max 16 bytes.
_HASH_PERSONALIZATION = b"nse-oms-idem/v1"

# Alphanumeric alphabet for the broker tag (digits, upper, lower = 62 symbols).
_BASE62_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"

# 62**43 >= 2**256, so 43 base62 digits always represent the full 256-bit
# digest with room to spare; we then take the high-order BROKER_TAG_LENGTH.
_BASE62_FULL_WIDTH = 43

# Per-value type tags. They make the serialization injective across types:
# None, the number 0, and the string "0" get distinct encodings, so a null
# limit price can never be confused with a zero one, nor a numeric field
# with a string field that happens to share a rendering.
_TYPE_TAG_NULL = "null"
_TYPE_TAG_NUMBER = "num"
_TYPE_TAG_TEXT = "str"


def session_key_for_date(trading_date: date) -> str:
    """Canonical session key for a trading day (ISO ``YYYY-MM-DD``).

    Folding the trading date into the id means the SAME setup on two
    different days yields two DIFFERENT ids (they are genuinely two
    distinct orders), while a retry *within* the same day reproduces the
    id (it is the same order) — exactly the idempotency window we want.
    """
    return trading_date.isoformat()


def _canonical_number_text(value: float | int) -> str:
    """Render a number to a value-canonical decimal string.

    ``100`` (int), ``100.0`` and ``100.00`` (float) must all map to the
    SAME text or the hash would drift on a meaningless int/float or
    trailing-zero difference. Going through ``Decimal(str(value))`` avoids
    binary-float noise (``0.1`` stays ``"0.1"``), and ``normalize()``
    strips trailing zeros / unifies scale; ``format(..., "f")`` forces
    plain decimal notation (never ``1E+2``).
    """
    normalized = Decimal(str(value)).normalize()
    # normalize() maps 0 -> Decimal("0"); guard the "-0" corner explicitly.
    if normalized == 0:
        return "0"
    return format(normalized, "f")


def _typed_field_encoding(value: object) -> list[str]:
    """Encode one identifying value as a ``[type_tag, text]`` pair.

    Enums are reduced to their ``.value`` (the stable wire string). ``None``
    gets its own tag so it is distinguishable from any real value.
    """
    if value is None:
        return [_TYPE_TAG_NULL, ""]
    # Enum members (OrderSide / OrderType / OrderVariety / ExchangeSegment)
    # are str-Enums whose `.value` is the canonical wire token.
    enum_value = getattr(value, "value", None)
    if isinstance(enum_value, str):
        return [_TYPE_TAG_TEXT, enum_value]
    if isinstance(value, bool):
        # bool is an int subclass — pin it explicitly so True/1 differ.
        return [_TYPE_TAG_TEXT, "true" if value else "false"]
    if isinstance(value, (int, float)):
        return [_TYPE_TAG_NUMBER, _canonical_number_text(value)]
    if isinstance(value, str):
        return [_TYPE_TAG_TEXT, value]
    raise TypeError(f"unhashable identifying value of type {type(value)!r}")


def _canonical_identity_mapping(
    order_intent: OrderIntent, session_key: str
) -> dict[str, list[str]]:
    """The IDENTIFYING fields of an order, as a name -> typed-encoding map.

    Only fields that make an order a *different logical order* participate.
    Deliberately EXCLUDED: `product` (fixed to intraday MIS project-wide),
    `time_in_force` / `validity_ttl_minutes`, `disclosed_quantity`,
    `iceberg_legs` — execution-shaping knobs, not identity. Two intents
    differing only there are the same order for dedup purposes.

    The instrument is pinned by its broker `instrument_token` (the stable
    unique key) PLUS `trading_symbol` + `exchange_segment` for defence in
    depth. Because this is a dict keyed by field name and serialized with
    ``sort_keys=True`` downstream, the field insertion order here never
    affects the resulting hash.
    """
    instrument = order_intent.instrument
    return {
        "instrument_token": _typed_field_encoding(instrument.instrument_token),
        "trading_symbol": _typed_field_encoding(instrument.trading_symbol),
        "exchange_segment": _typed_field_encoding(instrument.exchange_segment),
        "side": _typed_field_encoding(order_intent.side),
        "quantity": _typed_field_encoding(order_intent.quantity),
        "strategy_tag": _typed_field_encoding(order_intent.strategy_tag),
        "order_type": _typed_field_encoding(order_intent.order_type),
        "limit_price": _typed_field_encoding(order_intent.limit_price),
        "trigger_price": _typed_field_encoding(order_intent.trigger_price),
        "variety": _typed_field_encoding(order_intent.variety),
        "session_key": _typed_field_encoding(session_key),
    }


def _canonical_serialization(
    order_intent: OrderIntent, session_key: str
) -> bytes:
    """Serialize the identity mapping to canonical, order-independent bytes.

    ``sort_keys=True`` makes field order irrelevant; compact separators and
    ``ensure_ascii=True`` make the byte string reproducible on every
    platform / interpreter.
    """
    mapping = _canonical_identity_mapping(order_intent, session_key)
    canonical_json = json.dumps(
        mapping,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return canonical_json.encode("utf-8")


def _stable_digest_bytes(order_intent: OrderIntent, session_key: str) -> bytes:
    """Keyed BLAKE2b digest over the canonical serialization (256-bit).

    Deterministic across processes and machines — NOT salted like the
    built-in ``hash()`` — so it survives a crash-restart, which is the
    whole point of an idempotency key.
    """
    return hashlib.blake2b(
        _canonical_serialization(order_intent, session_key),
        digest_size=_FULL_DIGEST_SIZE_BYTES,
        person=_HASH_PERSONALIZATION,
    ).digest()


def _base62_encode(digest: bytes, width: int) -> str:
    """Big-endian base62 of ``digest``, left-padded to exactly ``width``.

    Pure arithmetic on the digest bytes, hence deterministic. Padding to a
    fixed width guarantees a stable, uniform-length output even in the
    (astronomically unlikely) case of a digest with many leading zero bits.
    """
    number = int.from_bytes(digest, byteorder="big")
    encoded: list[str] = []
    if number == 0:
        encoded.append(_BASE62_ALPHABET[0])
    while number > 0:
        number, remainder = divmod(number, 62)
        encoded.append(_BASE62_ALPHABET[remainder])
    encoded.reverse()
    text = "".join(encoded)
    return text.rjust(width, _BASE62_ALPHABET[0])


def _broker_tag_from_digest(digest: bytes) -> str:
    """Take the HIGH-ORDER ``BROKER_TAG_LENGTH`` base62 chars of the digest.

    Truncation / collision profile: 20 base62 chars encode ~119 bits of the
    256-bit digest (log2(62**20) approx 119). Under the birthday bound, even
    at an implausible 100,000 distinct orders in a single session the
    collision probability is ~ (1e5)**2 / (2 * 2**119) approx 8e-27 —
    negligible. The full 256-bit ``full_hex_id`` remains the WAL primary
    key; the tag is a broker-echoed convenience whose only failure mode is a
    tag collision between two genuinely different orders, guarded by the
    above margin.
    """
    return _base62_encode(digest, _BASE62_FULL_WIDTH)[:BROKER_TAG_LENGTH]


@dataclass(frozen=True)
class ClientOrderIdentity:
    """Both stable forms of an order's idempotency key.

    ``full_hex_id`` is the write-ahead-log primary key; ``broker_tag`` is
    the <=20-char alphanumeric form for Kite's ``tag`` field.
    """

    full_hex_id: str
    broker_tag: str


def deterministic_client_order_id(
    order_intent: OrderIntent, session_key: str
) -> str:
    """Stable 64-hex-char idempotency id for a logical order intent.

    Deterministic across processes/restarts: identical
    ``(order_intent, session_key)`` inputs always yield this exact string.
    Derived from the intent's identifying fields (instrument identity, side,
    quantity, strategy_tag, order_type, limit/trigger price, variety) plus
    ``session_key`` via a keyed BLAKE2b over a canonical serialization.
    """
    return _stable_digest_bytes(order_intent, session_key).hex()


def deterministic_broker_tag(
    order_intent: OrderIntent, session_key: str
) -> str:
    """Stable <=20-char alphanumeric idempotency tag for Kite's ``tag`` field."""
    return _broker_tag_from_digest(
        _stable_digest_bytes(order_intent, session_key)
    )


def client_order_identity(
    order_intent: OrderIntent, session_key: str
) -> ClientOrderIdentity:
    """Compute both idempotency forms in a single hashing pass.

    Preferred entry point for the broker path: the digest is computed once
    and both the WAL key and the broker tag are derived from it.
    """
    digest = _stable_digest_bytes(order_intent, session_key)
    return ClientOrderIdentity(
        full_hex_id=digest.hex(),
        broker_tag=_broker_tag_from_digest(digest),
    )
