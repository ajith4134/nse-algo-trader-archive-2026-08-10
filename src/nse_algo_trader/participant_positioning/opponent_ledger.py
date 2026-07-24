"""The opponent ledger: "who is on the other side of the market?"

Turns a raw participant-wise OI snapshot into the small set of directional /
divergence signals a trader actually reads from it (docs/research/47 §4):
- FII index-futures net & long-short ratio — the headline institutional lean.
- Client (retail) net — treated as the contrarian "other side" leg.
- FII-vs-Client divergence in index futures and index options — the classic
  reversal-trap tell (retail piling in while institutions fade).

This is a CONFIRMATION input, not an intraday trigger — every source stresses
it is a multi-day leaning indicator. The read model stays pure so it can be
unit-tested on injected snapshots (Rule J) and run on real NSE bytes (Rule F).
"""

from dataclasses import dataclass

from nse_algo_trader.participant_positioning.participant_positioning_source import (
    ParticipantCategory,
    ParticipantPositioningSnapshot,
)


def _long_short_ratio(long_contracts: int, short_contracts: int) -> float | None:
    if short_contracts <= 0:
        return None
    return round(long_contracts / short_contracts, 3)


@dataclass(frozen=True)
class OpponentLedgerReading:
    """Derived opponent-ledger signals for one trade date. `directional_lean`
    is a coarse label ('bullish'/'bearish'/'neutral') from FII futures net;
    `retail_on_other_side` is True when Client is leaning opposite FII in index
    futures (the reversal-trap divergence)."""

    report_date_iso: str
    fii_index_futures_net: int
    fii_index_futures_long_short_ratio: float | None
    client_index_futures_net: int
    fii_vs_client_futures_divergence: bool
    fii_index_options_net_call_bias: int
    client_index_options_net_call_bias: int
    fii_vs_client_options_divergence: bool
    directional_lean: str
    retail_on_other_side: bool
    headline: str


def _directional_lean(fii_index_futures_net: int, ratio: float | None) -> str:
    # A modest deadband so tiny nets read as neutral rather than flipping.
    if fii_index_futures_net > 0 and (ratio is None or ratio >= 1.1):
        return "bullish"
    if fii_index_futures_net < 0 and (ratio is None or ratio <= 0.9):
        return "bearish"
    return "neutral"


def read_opponent_ledger(
    snapshot: ParticipantPositioningSnapshot,
) -> OpponentLedgerReading | None:
    """Compute the opponent-ledger reading, or None if the FII/Client rows are
    absent (a malformed report)."""
    fii = snapshot.row_for(ParticipantCategory.FII)
    client = snapshot.row_for(ParticipantCategory.CLIENT)
    if fii is None or client is None:
        return None

    fii_futures_net = fii.future_index_net_long
    client_futures_net = client.future_index_net_long
    ratio = _long_short_ratio(fii.future_index_long, fii.future_index_short)
    # Divergence = the two are leaning opposite ways (opposite signs), which is
    # the "retail on the other side of institutions" tell.
    futures_divergence = (fii_futures_net > 0 > client_futures_net) or (
        fii_futures_net < 0 < client_futures_net
    )
    fii_options_bias = fii.index_options_net_call_bias
    client_options_bias = client.index_options_net_call_bias
    options_divergence = (fii_options_bias > 0 > client_options_bias) or (
        fii_options_bias < 0 < client_options_bias
    )
    lean = _directional_lean(fii_futures_net, ratio)
    retail_other_side = futures_divergence

    ratio_text = f"{ratio:.2f}" if ratio is not None else "n/a"
    divergence_text = (
        " — retail leaning the OTHER way (reversal-trap watch)"
        if retail_other_side
        else ""
    )
    headline = (
        f"FII index-futures {lean} (net {fii_futures_net:+,}, L/S {ratio_text}); "
        f"Client net {client_futures_net:+,}{divergence_text}."
    )
    return OpponentLedgerReading(
        report_date_iso=snapshot.report_date.isoformat(),
        fii_index_futures_net=fii_futures_net,
        fii_index_futures_long_short_ratio=ratio,
        client_index_futures_net=client_futures_net,
        fii_vs_client_futures_divergence=futures_divergence,
        fii_index_options_net_call_bias=fii_options_bias,
        client_index_options_net_call_bias=client_options_bias,
        fii_vs_client_options_divergence=options_divergence,
        directional_lean=lean,
        retail_on_other_side=retail_other_side,
        headline=headline,
    )
