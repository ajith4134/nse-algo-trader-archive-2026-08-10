"""Market-positioning-bias tests (opponent ledger → entry decisions).

HERMETIC (Rule J): the pure opposition rule on injected readings.
REAL DATA (Rule F): the real 23-Jul-2026 reading (FII bearish + retail long)
opposes a LONG entry.
"""

from dataclasses import replace
from datetime import date

from nse_algo_trader.participant_positioning import (
    institutional_positioning_opposes_entry,
    read_opponent_ledger,
)
from nse_algo_trader.participant_positioning.nse_participant_positioning_source import (
    parse_participant_report_csv,
)
from nse_algo_trader.participant_positioning.opponent_ledger import (
    OpponentLedgerReading,
)

from pathlib import Path

_REAL_SAMPLE = Path(__file__).parent / "real_nse_participant_oi_23072026.csv"


def _reading(lean: str, retail_on_other_side: bool) -> OpponentLedgerReading:
    return OpponentLedgerReading(
        report_date_iso="2026-07-23",
        fii_index_futures_net=-1000 if lean == "bearish" else 1000,
        fii_index_futures_long_short_ratio=0.5 if lean == "bearish" else 2.0,
        client_index_futures_net=1000 if lean == "bearish" else -1000,
        fii_vs_client_futures_divergence=retail_on_other_side,
        fii_index_options_net_call_bias=0,
        client_index_options_net_call_bias=0,
        fii_vs_client_options_divergence=False,
        directional_lean=lean,
        retail_on_other_side=retail_on_other_side,
        headline="",
    )


class TestPositioningOppositionRule:
    def test_bearish_fii_with_divergence_opposes_a_long(self):
        r = _reading("bearish", retail_on_other_side=True)
        assert institutional_positioning_opposes_entry(r, entry_is_bullish=True)
        # but does NOT oppose a short (institutions agree with the short)
        assert not institutional_positioning_opposes_entry(r, entry_is_bullish=False)

    def test_bullish_fii_with_divergence_opposes_a_short(self):
        r = _reading("bullish", retail_on_other_side=True)
        assert institutional_positioning_opposes_entry(r, entry_is_bullish=False)
        assert not institutional_positioning_opposes_entry(r, entry_is_bullish=True)

    def test_no_divergence_never_opposes(self):
        r = _reading("bearish", retail_on_other_side=False)
        assert not institutional_positioning_opposes_entry(r, entry_is_bullish=True)
        assert not institutional_positioning_opposes_entry(r, entry_is_bullish=False)

    def test_neutral_lean_never_opposes(self):
        r = _reading("neutral", retail_on_other_side=True)
        assert not institutional_positioning_opposes_entry(r, entry_is_bullish=True)
        assert not institutional_positioning_opposes_entry(r, entry_is_bullish=False)

    def test_no_reading_permits_everything(self):
        assert not institutional_positioning_opposes_entry(None, entry_is_bullish=True)
        assert not institutional_positioning_opposes_entry(None, entry_is_bullish=False)


class TestPositioningBiasOnRealNseReading:
    def test_real_bearish_divergence_opposes_a_long_not_a_short(self):
        if not _REAL_SAMPLE.exists():
            import pytest

            pytest.skip("real NSE sample absent")
        reading = read_opponent_ledger(
            parse_participant_report_csv(_REAL_SAMPLE.read_text(), date(2026, 7, 23))
        )
        # real reading: FII bearish, Client long -> retail on the other side
        assert reading.directional_lean == "bearish"
        assert reading.retail_on_other_side is True
        assert institutional_positioning_opposes_entry(reading, entry_is_bullish=True)
        assert not institutional_positioning_opposes_entry(
            reading, entry_is_bullish=False
        )


class TestConvictionGatesTheDefer:
    def test_low_conviction_divergence_does_not_oppose(self):
        # inject low conviction -> the thin divergence no longer defers
        r = replace(_reading("bearish", retail_on_other_side=True),
                    participation_conviction="low")
        assert not institutional_positioning_opposes_entry(r, entry_is_bullish=True)

    def test_normal_conviction_divergence_still_opposes(self):
        r = replace(_reading("bearish", retail_on_other_side=True),
                    participation_conviction="normal")
        assert institutional_positioning_opposes_entry(r, entry_is_bullish=True)


class TestTrendGatesTheDefer:
    def test_weakening_trend_suppresses_the_defer(self):
        r = replace(_reading("bearish", retail_on_other_side=True),
                    participation_conviction="normal", fii_net_trend="weakening")
        assert not institutional_positioning_opposes_entry(r, entry_is_bullish=True)

    def test_confirming_trend_keeps_the_defer(self):
        r = replace(_reading("bearish", retail_on_other_side=True),
                    participation_conviction="normal", fii_net_trend="confirming")
        assert institutional_positioning_opposes_entry(r, entry_is_bullish=True)
