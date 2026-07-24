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
    # Slice 2 (participant VOLUME): is today's positioning backed by active
    # trading? None when no volume report is supplied. `participation_conviction`
    # is a tier on FII index-futures churn (volume ÷ OI): a divergence backed by
    # real FII activity ("normal"/"high") is worth acting on; a thin/stale one
    # ("low") is not — the positioning gate suppresses the defer on "low".
    fii_index_futures_volume: int | None = None
    fii_index_futures_churn: float | None = None
    fii_volume_share: float | None = None
    participation_conviction: str | None = None
    # Slice 3 (multi-day trend): the recent FII index-futures net TREND relative
    # to today's lean. None when no history supplied. `fii_net_trend` is
    # 'confirming' (FII building the leaned-into position), 'weakening' (FII
    # covering it — an early reversal), or 'flat'. The gate suppresses a defer on
    # 'weakening' (don't fade retail when institutions are already unwinding).
    fii_net_trend: str | None = None
    fii_net_change_over_window: int | None = None
    fii_net_window_days: int | None = None


# FII index-futures churn (volume ÷ open interest) tiers — thresholds grounded
# in real 23-Jul data (FII 0.35, Client 0.48, Pro 0.73); see research/47 §slice-2.
_CONVICTION_HIGH_CHURN = 0.60
_CONVICTION_LOW_CHURN = 0.30


def _participation_conviction(churn: float | None) -> str | None:
    if churn is None:
        return None
    if churn >= _CONVICTION_HIGH_CHURN:
        return "high"
    if churn < _CONVICTION_LOW_CHURN:
        return "low"
    return "normal"


def _least_squares_slope(series: list[int]) -> float:
    """Slope (contracts/day) of the series against its index 0..n-1 — robust to
    a single-day blip in a way endpoint-difference is not."""
    n = len(series)
    mean_x = (n - 1) / 2.0
    mean_y = sum(series) / n
    covariance = sum((i - mean_x) * (y - mean_y) for i, y in enumerate(series))
    variance = sum((i - mean_x) ** 2 for i in range(n))
    return covariance / variance if variance > 0 else 0.0


def _fii_net_trend_vs_lean(
    recent_fii_nets: list[int] | None, lean: str, todays_net: int
) -> tuple[str | None, int | None, int | None]:
    """Classify the recent FII-net trend against today's lean. Returns
    (trend, net_change_over_window, window_days). 'confirming' = FII building the
    leaned-into position; 'weakening' = FII covering it; 'flat' = neutral lean or
    a change inside the deadband. None when <2 data points."""
    if recent_fii_nets is None or len(recent_fii_nets) < 2:
        return None, None, None
    window_days = len(recent_fii_nets)
    net_change = recent_fii_nets[-1] - recent_fii_nets[0]
    slope = _least_squares_slope(recent_fii_nets)
    modeled_change = slope * (window_days - 1)
    # Deadband: <10% of today's net magnitude, or a neutral lean → flat.
    deadband = 0.10 * abs(todays_net) if todays_net else 0.0
    if lean == "neutral" or abs(modeled_change) < deadband:
        return "flat", net_change, window_days
    # Rising net (slope>0) = building long / covering short; falling = building
    # short / reducing long. "Confirming" = trend deepens the leaned-into side.
    if lean == "bearish":
        trend = "confirming" if slope < 0 else "weakening"
    else:  # bullish
        trend = "confirming" if slope > 0 else "weakening"
    return trend, net_change, window_days


def _directional_lean(fii_index_futures_net: int, ratio: float | None) -> str:
    # A modest deadband so tiny nets read as neutral rather than flipping.
    if fii_index_futures_net > 0 and (ratio is None or ratio >= 1.1):
        return "bullish"
    if fii_index_futures_net < 0 and (ratio is None or ratio <= 0.9):
        return "bearish"
    return "neutral"


def _fii_index_futures_activity(
    volume_snapshot: ParticipantPositioningSnapshot | None,
    fii_open_interest_contracts: int,
) -> tuple[int | None, float | None, float | None]:
    """From the volume report, return FII index-futures (volume, churn, share):
    churn = FII futures volume ÷ FII futures OI; share = FII futures volume ÷
    total futures volume. All None when no volume report is supplied."""
    if volume_snapshot is None:
        return None, None, None
    fii_volume_row = volume_snapshot.row_for(ParticipantCategory.FII)
    total_volume_row = volume_snapshot.row_for(ParticipantCategory.TOTAL)
    if fii_volume_row is None:
        return None, None, None
    fii_volume = fii_volume_row.future_index_long + fii_volume_row.future_index_short
    churn = (
        round(fii_volume / fii_open_interest_contracts, 3)
        if fii_open_interest_contracts > 0
        else None
    )
    share = None
    if total_volume_row is not None:
        total_volume = (
            total_volume_row.future_index_long + total_volume_row.future_index_short
        )
        if total_volume > 0:
            share = round(fii_volume / total_volume, 3)
    return fii_volume, churn, share


def read_opponent_ledger(
    snapshot: ParticipantPositioningSnapshot,
    volume_snapshot: ParticipantPositioningSnapshot | None = None,
    recent_fii_index_futures_nets: list[int] | None = None,
) -> OpponentLedgerReading | None:
    """Compute the opponent-ledger reading, or None if the FII/Client rows are
    absent (a malformed report). When `volume_snapshot` is supplied, derive the
    participation-conviction qualifier (slice 2). When
    `recent_fii_index_futures_nets` (the FII index-futures net over the recent
    window, oldest→newest with today last) is supplied, derive the multi-day
    net-trend qualifier (slice 3)."""
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

    fii_open_interest = fii.future_index_long + fii.future_index_short
    fii_volume, fii_churn, fii_share = _fii_index_futures_activity(
        volume_snapshot, fii_open_interest
    )
    conviction = _participation_conviction(fii_churn)
    trend, net_change, window_days = _fii_net_trend_vs_lean(
        recent_fii_index_futures_nets, lean, fii_futures_net
    )

    ratio_text = f"{ratio:.2f}" if ratio is not None else "n/a"
    divergence_text = (
        " — retail leaning the OTHER way (reversal-trap watch)"
        if retail_other_side
        else ""
    )
    conviction_text = (
        f" [{conviction}-conviction, churn {fii_churn:.2f}]"
        if conviction is not None
        else ""
    )
    trend_text = (
        f" {window_days}-day trend {trend} ({net_change:+,})"
        if trend is not None
        else ""
    )
    headline = (
        f"FII index-futures {lean} (net {fii_futures_net:+,}, L/S {ratio_text}); "
        f"Client net {client_futures_net:+,}{divergence_text}{conviction_text}"
        f"{trend_text}."
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
        fii_index_futures_volume=fii_volume,
        fii_index_futures_churn=fii_churn,
        fii_volume_share=fii_share,
        participation_conviction=conviction,
        fii_net_trend=trend,
        fii_net_change_over_window=net_change,
        fii_net_window_days=window_days,
    )
