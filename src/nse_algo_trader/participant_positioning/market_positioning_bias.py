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
    lean = getattr(reading, "directional_lean", "neutral")
    if entry_is_bullish and lean == "bearish":
        return True
    if not entry_is_bullish and lean == "bullish":
        return True
    return False
