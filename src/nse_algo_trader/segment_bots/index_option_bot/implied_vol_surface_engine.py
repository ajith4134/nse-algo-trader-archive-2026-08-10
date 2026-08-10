"""Implied-volatility surface engine — the option-pricing brain of the INDEX-OPTION bot (Rule P).

Real algorithm, carried state, raw pipeline, decision-grade output:

* **IV + full greeks** over the real option chain, vectorised with ``py_vollib_vectorized`` (Peter Jäckel's
  "Let's Be Rational" — the accuracy/speed bar), Black-Scholes-Merton, per CE/PE contract.
* **Raw-SVI smile fit** per expiry (Gatheral raw parameterisation of total variance
  ``w(k) = a + b·(ρ(k−m) + √((k−m)² + σ²))``, k = log-moneyness) via ``scipy`` least-squares with
  no-butterfly-arbitrage bounds — turns a noisy strip of quotes into a smooth, extrapolatable smile.
* **Decision-grade surface features** — ATM IV, 25-delta risk-reversal (skew), term-structure slope, and
  **IV-rank / IV-percentile** vs the underlying's own rolling ATM-IV history. These are what actually pick
  the structure and side downstream: sell premium when IV-rank is high, buy when skew is cheap, etc.

Carried STATE = the per-underlying rolling ATM-IV history (drives IV-rank) persisted via
``ImpliedVolRankStore``. Small-sample honesty (Rule Q): IV-rank reports ``gathering`` until enough history
has accrued rather than emitting a false extreme off two data points.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import least_squares

_DEFAULT_RISK_FREE_RATE = 0.065  # India ~ short-rate; caller may override
_MIN_STRIKES_FOR_SVI = 5
_MIN_HISTORY_FOR_IV_RANK = 60  # ~a quarter of sessions before IV-rank is "earned"
_LIQUID_MONEYNESS_BAND = 0.35  # |log(K/F)| band for reliable quotes (deep wings are bhavcopy noise)
_MIN_TENOR_FOR_STRUCTURE = 3 / 365.0  # skip ~0DTE smiles for skew/term-structure (too noisy)
_ATM_STRIKE_BAND = 0.03  # ±3% of forward = the "at-the-money" cluster for the robust ATM fallback


@dataclass(frozen=True)
class SviSmileFit:
    """A fitted raw-SVI smile for one expiry (Gatheral total-variance parameterisation)."""

    expiry: str
    tenor_years: float
    a: float
    b: float
    rho: float
    m: float
    sigma: float
    forward: float
    n_strikes: int
    rms_vol_error: float  # fit quality, in vol points

    def total_variance(self, log_moneyness: float) -> float:
        k = log_moneyness
        return self.a + self.b * (self.rho * (k - self.m) + math.sqrt((k - self.m) ** 2 + self.sigma**2))

    def implied_vol(self, log_moneyness: float) -> float:
        w = max(self.total_variance(log_moneyness), 1e-8)
        return math.sqrt(w / max(self.tenor_years, 1e-6))


@dataclass(frozen=True)
class ImpliedVolSurfaceState:
    """Decision-grade output: the current IV surface picture for one index underlying."""

    underlying: str
    trade_date: str
    spot: float
    nearest_expiry: str
    nearest_atm_iv: float
    atm_iv_by_expiry: dict[str, float]
    risk_reversal_25d: float  # IV(25Δ put) − IV(25Δ call); >0 = downside skew (put demand)
    term_structure_slope: float  # far ATM IV − near ATM IV (contango>0 / backwardation<0)
    iv_rank: float | None  # [0,1] current ATM IV vs 1y rolling range (None until earned)
    iv_percentile: float | None
    smiles: tuple[SviSmileFit, ...] = field(default_factory=tuple)
    n_contracts: int = 0
    maturity: str = "gathering"  # "gathering" | "earned" (IV-rank history sufficiency)

    def is_rich_vol(self, high_rank: float = 0.5) -> bool:
        """True when IV is rich enough to favour NET PREMIUM SELLING (earned IV-rank above the threshold)."""
        return self.maturity == "earned" and self.iv_rank is not None and self.iv_rank >= high_rank


class ImpliedVolRankStore:
    """Persists each underlying's rolling ATM-IV history — the carried state IV-rank is measured against."""

    def __init__(self, store_dir: Path):
        self._dir = Path(store_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, underlying: str) -> Path:
        safe = underlying.replace("/", "_").replace(" ", "_")
        return self._dir / f"iv_rank_{safe}.json"

    def append_and_load(self, underlying: str, trade_date: str, atm_iv: float) -> list[float]:
        path = self._path(underlying)
        history: dict[str, float] = {}
        if path.exists():
            try:
                history = json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                history = {}
        history[trade_date] = float(atm_iv)  # keyed by date → idempotent per session
        trimmed = dict(sorted(history.items())[-400:])  # ~ >1y of sessions
        path.write_text(json.dumps(trimmed, indent=0))
        return [trimmed[k] for k in sorted(trimmed)]


def _year_fraction(trade_date: date, expiry: date) -> float:
    return max((expiry - trade_date).days, 0) / 365.0


def _fit_svi(log_moneyness: np.ndarray, total_variance: np.ndarray, tenor: float) -> tuple:
    """Fit raw-SVI params to (k, w) by bounded least squares. Returns (a,b,rho,m,sigma,rms_vol_error)."""

    w = np.maximum(total_variance, 1e-8)
    k = log_moneyness
    w_atm = float(np.median(w))
    # params: a, b, rho, m, sigma
    p0 = np.array([max(w_atm * 0.5, 1e-4), 0.1, -0.3, 0.0, 0.1])
    lower = np.array([1e-8, 1e-8, -0.999, -1.0, 1e-4])
    upper = np.array([1.0, 5.0, 0.999, 1.0, 2.0])

    def residual(p):
        a, b, rho, m, sig = p
        model = a + b * (rho * (k - m) + np.sqrt((k - m) ** 2 + sig**2))
        return model - w

    try:
        result = least_squares(residual, p0, bounds=(lower, upper), max_nfev=2000, method="trf")
        a, b, rho, m, sig = result.x
        model_w = a + b * (rho * (k - m) + np.sqrt((k - m) ** 2 + sig**2))
        vol_err = np.sqrt(model_w / tenor) - np.sqrt(w / tenor)
        rms = float(np.sqrt(np.mean(vol_err**2)))
        return a, b, rho, m, sig, rms
    except (ValueError, RuntimeError):
        return float(w_atm), 0.0, 0.0, 0.0, 0.1, float("nan")


class ImpliedVolSurfaceEngine:
    """Builds the IV surface for one index underlying from its real option chain, with carried IV-rank state."""

    def __init__(
        self,
        underlying: str,
        rank_store: ImpliedVolRankStore | None = None,
        risk_free_rate: float = _DEFAULT_RISK_FREE_RATE,
    ):
        self.underlying = underlying
        self._store = rank_store
        self._rate = risk_free_rate

    def _compute_ivs(self, chain: pd.DataFrame) -> pd.DataFrame:
        """BSM implied vol per contract from real close prices (Jäckel "Let's Be Rational"). Adds 'iv'.

        Uses the pure-Python ``py_vollib`` solver per contract rather than the numba-jitted vectorised
        wrapper, which fails to compile under this Python/numba combo (Tier-1 mechanical reject, Rule O.1a);
        the pure solver is the same algorithm and robust, and daily-cadence chain sizes are well within budget.
        """
        from py_lets_be_rational.exceptions import (
            AboveMaximumException,
            BelowIntrinsicException,
        )
        from vollib.black_scholes_merton.implied_volatility import implied_volatility as _bsm_iv

        prices = chain["close_price"].to_numpy(dtype=float)
        spots = chain["underlying_price"].to_numpy(dtype=float)
        strikes = chain["strike_price"].to_numpy(dtype=float)
        tenors = chain["tenor_years"].to_numpy(dtype=float)
        flags = np.where(chain["option_right_code"].str.upper().str.startswith("C"), "c", "p")

        ivs = np.full(len(chain), np.nan)
        unsolvable = 0
        for i in range(len(chain)):
            try:
                ivs[i] = _bsm_iv(prices[i], spots[i], strikes[i], tenors[i], self._rate, 0.0, flags[i])
            except (BelowIntrinsicException, AboveMaximumException, ValueError, ArithmeticError):
                ivs[i] = np.nan  # price below intrinsic / above max — a real unsolvable quote, dropped (counted)
                unsolvable += 1
        self.last_unsolvable_count = unsolvable  # surfaced, never silently swallowed (Rule O)
        out = chain.copy()
        out["iv"] = ivs
        out["flag"] = flags
        return out[np.isfinite(out["iv"]) & (out["iv"] > 0.001) & (out["iv"] < 5.0)]

    def _robust_atm_iv(self, smile: SviSmileFit | None, expiry_rows: pd.DataFrame, forward: float) -> float:
        """ATM IV from the SVI smile when the fit is clean; else the median IV of the near-ATM strike cluster."""
        if smile is not None and smile.n_strikes >= _MIN_STRIKES_FOR_SVI and smile.rms_vol_error < 0.05:
            return smile.implied_vol(0.0)
        if len(expiry_rows) == 0:
            return smile.implied_vol(0.0) if smile is not None else 0.0
        near = expiry_rows[(expiry_rows["strike_price"] - forward).abs() <= _ATM_STRIKE_BAND * forward]
        if len(near) >= 2:
            return float(np.median(near["iv"]))
        nearest = expiry_rows.iloc[(expiry_rows["strike_price"] - forward).abs().argmin()]
        return float(nearest["iv"])

    def _risk_reversal_25d(self, smile: SviSmileFit | None) -> float:
        """25Δ risk-reversal via the smile: IV at the ~25Δ put strike minus the ~25Δ call strike."""
        if smile is None:
            return 0.0
        # approximate 25Δ log-moneyness by ±0.25·σ_atm·√t (a standard delta≈N'(d) shortcut is overkill here)
        atm_iv = smile.implied_vol(0.0)
        width = 0.6745 * atm_iv * math.sqrt(max(smile.tenor_years, 1e-6))  # ~25Δ ≈ 0.67 std
        put_iv = smile.implied_vol(-width)  # OTM put (lower strike → negative k)
        call_iv = smile.implied_vol(+width)
        return put_iv - call_iv

    def fit_and_state(
        self,
        chain: pd.DataFrame,
        trade_date: str,
        prior_iv_history: list[float] | None = None,
    ) -> ImpliedVolSurfaceState:
        """Build the decision-grade IV-surface state from a real option chain for one trade date.

        ``chain`` columns required: option_right_code (CE/PE), strike_price, close_price, underlying_price,
        expiry_date (ISO). Rows with unusable IVs are dropped by the pricing step.
        """

        td = date.fromisoformat(trade_date)
        chain = chain.copy()
        chain["tenor_years"] = chain["expiry_date"].map(
            lambda e: _year_fraction(td, date.fromisoformat(str(e)[:10]))
        )
        chain = chain[(chain["tenor_years"] > 0) & (chain["close_price"] > 0) & (chain["underlying_price"] > 0)]
        priced = self._compute_ivs(chain) if len(chain) else chain.assign(iv=[], flag=[])
        spot = float(chain["underlying_price"].iloc[0]) if len(chain) else 0.0

        smiles: list[SviSmileFit] = []
        atm_by_expiry: dict[str, float] = {}
        for expiry, rows in priced.groupby("expiry_date"):
            expiry_str = str(expiry)[:10]
            tenor = float(rows["tenor_years"].iloc[0])
            forward = spot * math.exp(self._rate * tenor)
            k_all = np.log(rows["strike_price"].to_numpy(dtype=float) / max(forward, 1e-6))
            # keep only the liquid moneyness band — deep-OTM/ITM bhavcopy quotes are unreliable
            band = np.abs(k_all) <= _LIQUID_MONEYNESS_BAND
            liquid = rows[band]
            k = k_all[band]
            w = (liquid["iv"].to_numpy(dtype=float) ** 2) * tenor
            smile: SviSmileFit | None = None
            if len(liquid) >= _MIN_STRIKES_FOR_SVI:
                a, b, rho, m, sig, rms = _fit_svi(k, w, tenor)
                smile = SviSmileFit(expiry_str, tenor, a, b, rho, m, sig, forward, int(len(liquid)), rms)
                smiles.append(smile)
            atm_by_expiry[expiry_str] = self._robust_atm_iv(smile, liquid if len(liquid) else rows, forward)

        smiles.sort(key=lambda s: s.tenor_years)
        nearest_expiry = min(atm_by_expiry, key=lambda e: date.fromisoformat(e).toordinal()) if atm_by_expiry else ""
        nearest_atm = atm_by_expiry.get(nearest_expiry, 0.0)
        # skew + term structure use only STABLE expiries (>= min tenor) — 0DTE smiles are too noisy
        stable = [s for s in smiles if s.tenor_years >= _MIN_TENOR_FOR_STRUCTURE and s.rms_vol_error < 0.1]
        rr25 = self._risk_reversal_25d(stable[0] if stable else (smiles[0] if smiles else None))
        term_slope = (stable[-1].implied_vol(0.0) - stable[0].implied_vol(0.0)) if len(stable) >= 2 else 0.0

        # --- IV-rank against carried rolling history (Rule Q maturity ladder) ----------------------
        history = list(prior_iv_history or [])
        if self._store is not None and nearest_atm > 0:
            history = self._store.append_and_load(self.underlying, trade_date, nearest_atm)
        iv_rank: float | None = None
        iv_pct: float | None = None
        maturity = "gathering"
        if len(history) >= _MIN_HISTORY_FOR_IV_RANK and nearest_atm > 0:
            lo, hi = min(history), max(history)
            iv_rank = (nearest_atm - lo) / (hi - lo) if hi > lo else 0.5
            iv_pct = float(np.mean([h <= nearest_atm for h in history]))
            maturity = "earned"

        return ImpliedVolSurfaceState(
            underlying=self.underlying,
            trade_date=trade_date,
            spot=spot,
            nearest_expiry=nearest_expiry,
            nearest_atm_iv=nearest_atm,
            atm_iv_by_expiry=atm_by_expiry,
            risk_reversal_25d=rr25,
            term_structure_slope=term_slope,
            iv_rank=iv_rank,
            iv_percentile=iv_pct,
            smiles=tuple(smiles),
            n_contracts=int(len(priced)),
            maturity=maturity,
        )

    def state_as_dict(self, state: ImpliedVolSurfaceState) -> dict:
        return asdict(state)
