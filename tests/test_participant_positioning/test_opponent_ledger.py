"""Opponent-ledger tests.

Two gates:
- HERMETIC (Rule J): the read model on injected snapshots through the DI-seam
  fake — divergence detection, directional lean, ratio, holiday None.
- REAL DATA (Rule F): parse a real archived NSE participant-OI CSV
  (fao_participant_oi_23072026.csv, EOD file fetchable market-closed) and assert
  the derivations match values hand-computed from the real bytes.
"""

from datetime import date
from pathlib import Path

import pytest

from nse_algo_trader.participant_positioning import (
    ParticipantCategory,
    ParticipantOpenInterestRow,
    ParticipantPositioningSnapshot,
    read_opponent_ledger,
)
from nse_algo_trader.participant_positioning.nse_participant_positioning_source import (
    parse_participant_report_csv,
)

from .in_memory_participant_positioning_source import (
    InMemoryParticipantPositioningSource,
)

_REAL_SAMPLE = Path(__file__).parent / "real_nse_participant_oi_23072026.csv"


def _row(client_type: str, fut_long: int, fut_short: int, **options) -> (
    ParticipantOpenInterestRow
):
    return ParticipantOpenInterestRow(
        client_type=client_type,
        future_index_long=fut_long,
        future_index_short=fut_short,
        future_stock_long=0,
        future_stock_short=0,
        option_index_call_long=options.get("call_long", 0),
        option_index_put_long=options.get("put_long", 0),
        option_index_call_short=options.get("call_short", 0),
        option_index_put_short=options.get("put_short", 0),
        option_stock_call_long=0,
        option_stock_put_long=0,
        option_stock_call_short=0,
        option_stock_put_short=0,
        total_long_contracts=fut_long,
        total_short_contracts=fut_short,
    )


def _snapshot(fii, client, pro=None, dii=None) -> ParticipantPositioningSnapshot:
    rows = {ParticipantCategory.FII: fii, ParticipantCategory.CLIENT: client}
    if pro is not None:
        rows[ParticipantCategory.PRO] = pro
    if dii is not None:
        rows[ParticipantCategory.DII] = dii
    return ParticipantPositioningSnapshot(date(2026, 7, 23), rows)


class TestOpponentLedgerHermetic:
    def test_fii_net_long_reads_bullish_with_ratio(self):
        reading = read_opponent_ledger(
            _snapshot(_row("FII", 300, 100), _row("Client", 100, 300))
        )
        assert reading.fii_index_futures_net == 200
        assert reading.fii_index_futures_long_short_ratio == 3.0
        assert reading.directional_lean == "bullish"

    def test_retail_on_other_side_when_client_opposes_fii(self):
        # FII net short, Client net long -> divergence, retail on the other side
        reading = read_opponent_ledger(
            _snapshot(_row("FII", 100, 400), _row("Client", 350, 120))
        )
        assert reading.directional_lean == "bearish"
        assert reading.fii_vs_client_futures_divergence is True
        assert reading.retail_on_other_side is True
        assert "reversal-trap" in reading.headline

    def test_same_side_is_not_a_divergence(self):
        reading = read_opponent_ledger(
            _snapshot(_row("FII", 300, 100), _row("Client", 300, 100))
        )
        assert reading.fii_vs_client_futures_divergence is False
        assert reading.retail_on_other_side is False

    def test_options_call_bias_divergence(self):
        # FII bullish via options (long calls), Client bearish (long puts)
        fii = _row("FII", 100, 100, call_long=500, put_long=50)
        client = _row("Client", 100, 100, call_long=50, put_long=500)
        reading = read_opponent_ledger(_snapshot(fii, client))
        assert reading.fii_index_options_net_call_bias > 0
        assert reading.client_index_options_net_call_bias < 0
        assert reading.fii_vs_client_options_divergence is True

    def test_thin_net_reads_neutral(self):
        reading = read_opponent_ledger(
            _snapshot(_row("FII", 1000, 1000), _row("Client", 1000, 1000))
        )
        assert reading.directional_lean == "neutral"

    def test_missing_fii_row_returns_none(self):
        snapshot = ParticipantPositioningSnapshot(
            date(2026, 7, 23),
            {ParticipantCategory.CLIENT: _row("Client", 100, 100)},
        )
        assert read_opponent_ledger(snapshot) is None

    def test_source_seam_returns_none_on_holiday(self):
        source = InMemoryParticipantPositioningSource(
            {date(2026, 7, 23): _snapshot(_row("FII", 300, 100),
                                          _row("Client", 100, 300))}
        )
        assert source.positioning_on(date(2026, 7, 23)) is not None
        assert source.positioning_on(date(2026, 7, 26)) is None  # a Sunday


@pytest.mark.skipif(not _REAL_SAMPLE.exists(), reason="real NSE sample absent")
class TestOpponentLedgerOnRealNseData:
    def test_parses_real_nse_file_and_derives_expected_signals(self):
        snapshot = parse_participant_report_csv(
            _REAL_SAMPLE.read_text(), date(2026, 7, 23)
        )
        # all five NSE rows present
        for category in ("Client", "DII", "FII", "Pro", "TOTAL"):
            assert snapshot.row_for(category) is not None
        # market-clearing checksum on the real TOTAL row
        total = snapshot.row_for("TOTAL")
        assert total.total_long_contracts == total.total_short_contracts

        reading = read_opponent_ledger(snapshot)
        # values hand-computed from the real bytes (research/47):
        # FII fut idx 24274 long / 287356 short; Client 232911 / 65424
        assert reading.fii_index_futures_net == -263082
        assert reading.client_index_futures_net == 167487
        assert reading.fii_index_futures_long_short_ratio == 0.084
        assert reading.directional_lean == "bearish"
        # FII net short while Client net long -> the retail-on-other-side tell
        assert reading.retail_on_other_side is True


_REAL_VOL = Path(__file__).parent / "real_nse_participant_vol_23072026.csv"


class TestParticipationConviction:
    def test_no_volume_snapshot_leaves_conviction_none(self):
        reading = read_opponent_ledger(
            _snapshot(_row("FII", 300, 100), _row("Client", 100, 300))
        )
        assert reading.participation_conviction is None
        assert reading.fii_index_futures_churn is None

    def test_high_churn_reads_high_conviction(self):
        # FII OI 100+100=200; volume 150+150=300 -> churn 1.5 -> high
        oi = _snapshot(_row("FII", 100, 100), _row("Client", 100, 100))
        vol = _snapshot(_row("FII", 150, 150), _row("Client", 100, 100))
        reading = read_opponent_ledger(oi, vol)
        assert reading.fii_index_futures_churn == 1.5
        assert reading.participation_conviction == "high"

    def test_low_churn_reads_low_conviction(self):
        # FII OI 1000+1000=2000; volume 100+100=200 -> churn 0.1 -> low
        oi = _snapshot(_row("FII", 1000, 1000), _row("Client", 100, 900))
        vol = _snapshot(_row("FII", 100, 100), _row("Client", 100, 100))
        reading = read_opponent_ledger(oi, vol)
        assert reading.fii_index_futures_churn == 0.1
        assert reading.participation_conviction == "low"

    @pytest.mark.skipif(not _REAL_VOL.exists(), reason="real vol sample absent")
    def test_real_volume_gives_normal_conviction(self):
        oi = parse_participant_report_csv(_REAL_SAMPLE.read_text(), date(2026, 7, 23))
        vol = parse_participant_report_csv(_REAL_VOL.read_text(), date(2026, 7, 23))
        reading = read_opponent_ledger(oi, vol)
        # real 23-Jul: FII index-fut churn 0.35 -> normal; backed divergence
        assert reading.fii_index_futures_churn == 0.354
        assert reading.participation_conviction == "normal"
        assert reading.fii_volume_share is not None


class TestFiiNetTrend:
    def _bearish_oi(self):
        # FII net short, Client net long -> bearish lean + divergence
        return _snapshot(_row("FII", 100, 400), _row("Client", 350, 120))

    def test_building_short_confirms_bearish_lean(self):
        # FII net falling (more short) over the window -> confirming
        reading = read_opponent_ledger(
            self._bearish_oi(),
            recent_fii_index_futures_nets=[-200, -240, -270, -300, -340],
        )
        assert reading.directional_lean == "bearish"
        assert reading.fii_net_trend == "confirming"
        assert reading.fii_net_change_over_window == -140
        assert reading.fii_net_window_days == 5

    def test_covering_short_weakens_bearish_lean(self):
        # FII net rising (covering the short) -> weakening
        reading = read_opponent_ledger(
            self._bearish_oi(),
            recent_fii_index_futures_nets=[-340, -300, -270, -240, -200],
        )
        assert reading.fii_net_trend == "weakening"
        assert reading.fii_net_change_over_window == 140

    def test_flat_within_deadband(self):
        reading = read_opponent_ledger(
            self._bearish_oi(),
            recent_fii_index_futures_nets=[-300, -301, -299, -300, -300],
        )
        assert reading.fii_net_trend == "flat"

    def test_no_history_leaves_trend_none(self):
        reading = read_opponent_ledger(self._bearish_oi())
        assert reading.fii_net_trend is None

    @pytest.mark.skipif(not _REAL_SAMPLE.exists(), reason="real sample absent")
    def test_real_recent_series_confirms_the_bearish_lean(self):
        oi = parse_participant_report_csv(_REAL_SAMPLE.read_text(), date(2026, 7, 23))
        # real FII index-fut nets 17->23 Jul (oldest->newest), building short
        real_series = [-216528, -219823, -228847, -251704, -263082]
        reading = read_opponent_ledger(oi, recent_fii_index_futures_nets=real_series)
        assert reading.directional_lean == "bearish"
        assert reading.fii_net_trend == "confirming"
        assert reading.fii_net_change_over_window == -46554
