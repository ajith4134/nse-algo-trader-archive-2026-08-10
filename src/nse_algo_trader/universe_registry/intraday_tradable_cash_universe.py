"""Which NSE cash scrips may an INTRADAY-only bot actually trade?

Kite's instrument dump marks NSE-listed **bonds and NCDs** with `instrument_type == "EQ"`, so they
arrive classified as cash equity (`kite_instrument_master_loader.py`). The result: the live scanner's
"cash equity universe" is 9,292 instruments of which roughly three quarters are debt paper that
barely trades and returns no intraday bars.

The authoritative answer is the exchange's own **bhavcopy `series` column**, which this project
already ingests daily into `cash_bhavcopy_delivery`. Measured on the 2026-07-24 report:

    EQ 2389 | BE 300 | SM 292 | ST 143 | GS 45 | GB 44 | BZ 26 | IV/RR/E1/SZ/MF 20

Only **EQ** (rolling settlement, normal market) may be traded intraday. Excluding **BE/BZ** is a
CORRECTNESS requirement, not an optimisation: trade-for-trade and surveillance scrips settle on
compulsory delivery with no intraday netting, so a position opened in one **cannot be squared off
before close** — which would violate this project's hardest non-negotiable (intraday only, every
position auto-squared-off before close).

See `docs/research/b1_intraday_tradable_cash_universe_design_2026-07-27.md`.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from collections.abc import Mapping, Sequence

from nse_algo_trader.universe_registry.instrument_types import (
    Instrument,
    InstrumentKind,
)

#: The ONLY NSE series an intraday bot may trade. Every exclusion below is deliberate:
#:   BE / BZ  — trade-for-trade & surveillance: compulsory delivery, NO intraday netting.
#:   SM / ST  — SME platform (and SME trade-for-trade): separate platform, thin, lot-based.
#:   GS / GB  — government securities & bonds: debt, not equity.
#:   IV/RR/E1/SZ/MF — institutional, rights, mutual-fund and other special series.
INTRADAY_TRADABLE_NSE_SERIES: frozenset[str] = frozenset({"EQ"})

#: Bucket label for instruments the exchange report did not mention at all.
UNREPORTED_SERIES_LABEL = "(not in bhavcopy)"


@dataclass(frozen=True)
class IntradayTradableCashUniverseSelection:
    """The kept instruments plus WHY everything else was dropped.

    The excluded counts exist so a 9,292 → 2,389 reduction is visible on the dashboard rather than a
    silent shrink (Rule O.3) — and so a stale or partial bhavcopy shows up as a large
    `(not in bhavcopy)` bucket instead of quietly starving the scanner.
    """

    tradable_instruments: tuple[Instrument, ...]
    excluded_count_by_series: Mapping[str, int] = field(default_factory=dict)

    @property
    def tradable_count(self) -> int:
        return len(self.tradable_instruments)

    @property
    def excluded_count(self) -> int:
        return sum(self.excluded_count_by_series.values())

    def summary_line(self) -> str:
        """One human-readable line for the log and the dashboard surface."""
        if not self.excluded_count_by_series:
            return f"{self.tradable_count} intraday-tradable cash names (nothing excluded)"
        worst_first = sorted(
            self.excluded_count_by_series.items(), key=lambda kv: -kv[1]
        )
        breakdown = " · ".join(f"{series} {count}" for series, count in worst_first)
        return (
            f"{self.tradable_count} intraday-tradable (series "
            f"{'/'.join(sorted(INTRADAY_TRADABLE_NSE_SERIES))}) — "
            f"excluded {self.excluded_count}: {breakdown}"
        )


def select_intraday_tradable_cash_equities(
    cash_instruments: Sequence[Instrument],
    series_by_trading_symbol: Mapping[str, str],
) -> IntradayTradableCashUniverseSelection:
    """Keep only the cash instruments the exchange reports in an intraday-tradable series.

    Pure — no I/O, so it is fully testable. `series_by_trading_symbol` comes from the latest stored
    NSE cash bhavcopy.

    An instrument absent from the report is EXCLUDED and counted under `UNREPORTED_SERIES_LABEL`:
    absence means the exchange did not report it trading on the last session, which is the safe
    reading for an intraday bot. Counting it separately keeps a stale/partial bhavcopy visible.

    Structurally narrowing-only: the result is always a subsequence of the input, so this can never
    invent an instrument or widen the universe.
    """
    tradable: list[Instrument] = []
    excluded: Counter[str] = Counter()

    for instrument in cash_instruments:
        if instrument.kind is not InstrumentKind.CASH_EQUITY:
            excluded[f"(not cash equity: {instrument.kind.value})"] += 1
            continue
        series = series_by_trading_symbol.get(instrument.trading_symbol)
        if series is None:
            excluded[UNREPORTED_SERIES_LABEL] += 1
            continue
        if series not in INTRADAY_TRADABLE_NSE_SERIES:
            excluded[series] += 1
            continue
        tradable.append(instrument)

    return IntradayTradableCashUniverseSelection(
        tradable_instruments=tuple(tradable),
        excluded_count_by_series=dict(excluded),
    )
