"""Option-flow signal engine — per-name positioning from the real chain OI + volume (Rule P).

No free OSS supplies NSE single-stock option flow (Benzinga/Unusual-Whales are US-only), so this is built
in-house from the exchange's own option-chain snapshots (research §3 STOCK-OPT). It computes, per underlying:

* **Put-Call Ratio** by open interest and by volume — the standard positioning gauge.
* **PCR-shift z-score** — today's PCR vs the name's own rolling PCR history (a shift matters more than the
  level, which varies hugely by name); carried state = the per-name PCR history.
* **Unusual activity** — strikes where today's volume exceeds a multiple of open interest (fresh
  positioning, not hedging churn), split into call-side and put-side.
* **Net flow bias** in [-1, 1] — call-buildup minus put-buildup, the directional tilt of the flow.

These are decision-grade inputs to the structure selector: a bearish PCR shift + heavy put buildup argues
against selling put premium; unusual call activity argues for a directional debit tilt.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

_UNUSUAL_VOLUME_TO_OI = 2.0  # today's volume > 2× OI at a strike = fresh positioning
_MIN_HISTORY_FOR_SHIFT = 30  # sessions of PCR history before the shift z-score is trusted


@dataclass(frozen=True)
class OptionFlowState:
    """Decision-grade option-flow picture for one underlying."""

    underlying: str
    trade_date: str
    pcr_open_interest: float
    pcr_volume: float
    pcr_shift_z: float | None  # today's PCR-by-OI vs rolling history (None until earned)
    unusual_call_strikes: tuple[float, ...]
    unusual_put_strikes: tuple[float, ...]
    net_flow_bias: float  # [-1, 1]; >0 = call-side buildup dominates (bullish flow)
    n_contracts: int
    maturity: str = "gathering"  # PCR-shift history sufficiency
    field_notes: dict = field(default_factory=dict)

    def is_bearish_flow(self, z_threshold: float = 1.0) -> bool:
        return self.pcr_shift_z is not None and self.pcr_shift_z >= z_threshold and self.net_flow_bias < 0.0


class PcrHistoryStore:
    """Persists each underlying's rolling PCR-by-OI history — the carried state the shift z-score needs."""

    def __init__(self, store_dir: Path):
        self._dir = Path(store_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, underlying: str) -> Path:
        return self._dir / f"pcr_{underlying.replace('/', '_').replace(' ', '_')}.json"

    def append_and_load(self, underlying: str, trade_date: str, pcr: float) -> list[float]:
        path = self._path(underlying)
        history: dict[str, float] = {}
        if path.exists():
            try:
                history = json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                history = {}
        history[trade_date] = float(pcr)
        trimmed = dict(sorted(history.items())[-250:])
        path.write_text(json.dumps(trimmed, indent=0))
        return [trimmed[k] for k in sorted(trimmed)]


class OptionFlowEngine:
    """Computes the per-name option-flow signals from a real option chain, with carried PCR history."""

    def __init__(self, underlying: str, pcr_store: PcrHistoryStore | None = None):
        self.underlying = underlying
        self._store = pcr_store

    def compute(
        self, chain: pd.DataFrame, trade_date: str, prior_pcr_history: list[float] | None = None
    ) -> OptionFlowState:
        """chain columns: option_right_code (CE/PE), strike_price, open_interest, total_traded_volume."""

        if len(chain) == 0:
            return OptionFlowState(self.underlying, trade_date, 0.0, 0.0, None, (), (), 0.0, 0, "gathering")

        is_call = chain["option_right_code"].str.upper().str.startswith("C")
        oi = pd.to_numeric(chain.get("open_interest"), errors="coerce").fillna(0.0)
        vol = pd.to_numeric(chain.get("total_traded_volume"), errors="coerce").fillna(0.0)

        call_oi, put_oi = float(oi[is_call].sum()), float(oi[~is_call].sum())
        call_vol, put_vol = float(vol[is_call].sum()), float(vol[~is_call].sum())
        pcr_oi = put_oi / call_oi if call_oi > 0 else 0.0
        pcr_vol = put_vol / call_vol if call_vol > 0 else 0.0

        # unusual activity: volume > _UNUSUAL_VOLUME_TO_OI × OI at a strike = fresh positioning
        with np.errstate(divide="ignore", invalid="ignore"):
            ratio = np.where(oi.to_numpy() > 0, vol.to_numpy() / oi.to_numpy(), 0.0)
        unusual = ratio >= _UNUSUAL_VOLUME_TO_OI
        strikes = chain["strike_price"].to_numpy(dtype=float)
        unusual_calls = tuple(sorted(set(strikes[unusual & is_call.to_numpy()].tolist())))
        unusual_puts = tuple(sorted(set(strikes[unusual & (~is_call).to_numpy()].tolist())))

        # net flow bias: call-side fresh volume vs put-side fresh volume, normalised
        fresh_call = float(vol[is_call.to_numpy() & unusual].sum())
        fresh_put = float(vol[(~is_call.to_numpy()) & unusual].sum())
        denom = fresh_call + fresh_put
        net_bias = ((fresh_call - fresh_put) / denom) if denom > 0 else 0.0

        # PCR-shift z-score vs the name's own history (carried state)
        history = list(prior_pcr_history or [])
        if self._store is not None:
            history = self._store.append_and_load(self.underlying, trade_date, pcr_oi)
        shift_z: float | None = None
        maturity = "gathering"
        if len(history) >= _MIN_HISTORY_FOR_SHIFT:
            mean, std = float(np.mean(history)), float(np.std(history))
            shift_z = ((pcr_oi - mean) / std) if std > 1e-9 else 0.0
            maturity = "earned"

        return OptionFlowState(
            underlying=self.underlying,
            trade_date=trade_date,
            pcr_open_interest=pcr_oi,
            pcr_volume=pcr_vol,
            pcr_shift_z=shift_z,
            unusual_call_strikes=unusual_calls,
            unusual_put_strikes=unusual_puts,
            net_flow_bias=float(max(-1.0, min(1.0, net_bias))),
            n_contracts=int(len(chain)),
            maturity=maturity,
            field_notes={"call_oi": call_oi, "put_oi": put_oi, "unusual_count": int(unusual.sum())},
        )
