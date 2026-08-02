"""Turns an opponent-ledger reading into an entry-time bias (the ledger's
primary consumer — it affects DECISIONS, not just the dashboard).

Honors the rule that participant-wise OI is a multi-day CONFIRMATION input,
never a trigger: this never *forces* a trade, it only flags when a new entry
would be initiated on the side retail is trapped on while institutions (FII)
lean the other way — the classic reversal-trap. Callers use it to DEFER such
entries (existing positions are never touched). See docs/research/47 §slice-1.
"""


def institutional_positioning_opposes_entry(
    reading, entry_is_bullish: bool
) -> bool:
    """True only in the strong divergence case: FII (institutions) leaning
    against this entry's direction while retail is on the other side.

    `reading` is an OpponentLedgerReading or None (no report yet → never
    opposes). A bullish entry (cash LONG / long CE / bullish put-credit-spread)
    is opposed when FII lean is bearish; a bearish entry (cash SHORT / long PE /
    bearish call-credit-spread) is opposed when FII lean is bullish — and in
    both cases only when `retail_on_other_side` confirms the divergence."""
    if reading is None or not getattr(reading, "retail_on_other_side", False):
        return False
    # Slice 2: only act on a divergence the volume report shows is backed by
    # active FII trading. A "low"-conviction (thin/stale) divergence is not
    # enough to defer an entry. None conviction (no volume report) → defer as in
    # slice 1 (the divergence stands on the OI signal alone).
    if getattr(reading, "participation_conviction", None) == "low":
        return False
    # Slice 3: don't fade the retail side when the multi-day trend shows FII are
    # already COVERING the very position we'd be leaning on (an early reversal) —
    # a "weakening" trend suppresses the defer. Confirming/flat/None → defer.
    if getattr(reading, "fii_net_trend", None) == "weakening":
        return False
    lean = getattr(reading, "directional_lean", "neutral")
    if entry_is_bullish and lean == "bearish":
        return True
    if not entry_is_bullish and lean == "bullish":
        return True
    return False


# ---------------------------------------------------------------------------------------------
# B16: the graded replacement for the binary veto above.
#
# `institutional_positioning_opposes_entry` is a BOOLEAN, and callers turned it into a hard defer.
# Measured on this book's own closed trades (2026-07-27): a "bearish" lean blocked EVERY bullish
# entry, all day, on 145 of 377 decisions — and the long book was the profitable side
# (82 trades / 50% win / +10,282) while the forced short book carried the entire loss
# (294 trades / 9.5% win / -45,033). A confirmation signal was acting as a trigger-strength veto,
# which this module's own docstring says it must never be.
#
# Two fixes, both here:
#   1. GRADED — opposition sizes DOWN instead of refusing. Tighten-only: never above 1.0.
#   2. RELEVANCE-SCALED — this is ONE market-wide NSE index-futures reading. It is genuinely about
#      the index, so an index option gets its full weight; a single mid-cap cash equity, which the
#      reading says very little about, gets the least. Applying it unscaled to individual stocks was
#      a category error.
# ---------------------------------------------------------------------------------------------

#: How much a full-strength opposing reading may size an entry down, by how RELEVANT the
#: index-futures signal is to that instrument. 1.0 would be no effect; 0.0 would be the old veto.
POSITIONING_SIZE_DOWN_BY_INSTRUMENT_KIND: dict[str, float] = {
    "index_option": 0.50,   # the reading is literally about this index
    "stock_option": 0.75,   # single-name, but derivative flow correlates with index positioning
    "cash_equity": 0.85,    # a market-wide index reading says least about one stock
}

#: Floor for any instrument kind not listed — deliberately the mildest effect, so an unmapped kind
#: fails SAFE (barely sized down) rather than silently inheriting the harshest multiplier.
DEFAULT_POSITIONING_SIZE_DOWN = 0.85


def positioning_size_down_multiplier(
    reading, entry_is_bullish: bool, instrument_kind: str = "cash_equity"
) -> float:
    """How much to size an entry DOWN because institutions lean against it. Never blocks.

    Returns 1.0 when the reading does not oppose this entry (including every early-return case the
    boolean gate already honours: no reading, retail not on the other side, low conviction, or a
    weakening FII trend). Otherwise returns the instrument-appropriate size-down factor.

    Structurally tighten-only: the result is clamped to (0, 1], so no reading, configuration, or
    future instrument kind can ever INCREASE a position.
    """
    if not institutional_positioning_opposes_entry(reading, entry_is_bullish):
        return 1.0
    multiplier = POSITIONING_SIZE_DOWN_BY_INSTRUMENT_KIND.get(
        instrument_kind, DEFAULT_POSITIONING_SIZE_DOWN
    )
    return max(0.01, min(float(multiplier), 1.0))
