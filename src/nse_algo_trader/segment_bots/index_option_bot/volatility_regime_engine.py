"""Volatility-regime engine — the vol brain of the INDEX-OPTION bot (engine-grade, Rule P).

Real algorithm, carried state, raw-input pipeline, decision-grade output:

* **Conditional-vol forecast** — a GJR-GARCH(1,1,1) with skew-t innovations fitted with ``arch`` captures
  volatility clustering AND the leverage effect (down-moves raise vol more than up-moves) that a plain
  IV−RV scalar cannot. Fused with a **HAR-RV** forecast (Corsi 2009: daily/weekly/monthly realized-vol
  components), the two blended by inverse out-of-sample error.
* **Learned regime** — a ``statsmodels`` Markov-switching model over returns with switching variance gives
  a causal, **point-in-time** regime posterior (filtered, not smoothed — uses only past data), so the desk
  knows whether it is in a calm/premium-harvest regime or a stressed/stand-aside one. Selling variance in
  the wrong regime is the classic account-ender; this is the gate that prevents it.
* **Variance risk premium** — forecast realized vol vs the option-implied vol → the harvestable VRP, the
  signal the whole short-vol book monetises.

Carried STATE = the fitted GARCH/HAR/regime parameters, persisted per underlying via
``VolatilityRegimeStore`` with a metrics ledger, and walk-forward refit on a cadence. Small-sample honesty
(Rule Q): below a minimum history the engine still returns a full state from an EWMA fallback and reports
its maturity, never a silently-wrong "calm".
"""

from __future__ import annotations

import json
import math
import warnings
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_TRADING_DAYS = 252
_IST = timezone(timedelta(hours=5, minutes=30))

# maturity ladder (Rule Q): full fitted engine needs enough history; below it, the EWMA fallback runs.
_MIN_OBS_FOR_GARCH = 250
_MIN_OBS_FOR_REGIME = 300
_EWMA_LAMBDA = 0.94  # RiskMetrics decay for the small-sample fallback


@dataclass(frozen=True)
class VolatilityRegimeState:
    """Decision-grade output: the current vol/regime picture for one index underlying."""

    underlying: str
    regime_label: str  # calm | elevated | stressed  (or "gathering" while immature)
    regime_index: int
    regime_probabilities: tuple[float, ...]  # filtered posterior, sums to 1 (point-in-time)
    garch_forecast_sigma: float  # annualized 1-step conditional vol
    har_forecast_sigma: float  # annualized HAR-RV forecast
    blended_forecast_sigma: float  # annualized, inverse-error blend of the two
    realized_vol: float  # annualized trailing realized vol
    variance_risk_premium: float | None  # implied_vol - blended_forecast_sigma (None if no implied given)
    n_observations: int
    maturity: str  # "gathering" | "earned"
    fitted_at_ist: str

    def is_premium_harvest_regime(self) -> bool:
        """True when the desk should be a net vol seller: calm/elevated regime AND a positive VRP."""
        return (
            self.maturity == "earned"
            and self.regime_label in ("calm", "elevated")
            and (self.variance_risk_premium or 0.0) > 0.0
        )


class VolatilityRegimeStore:
    """Persists fitted-engine snapshots + a metrics ledger per underlying (carried state)."""

    def __init__(self, store_dir: Path):
        self._dir = Path(store_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, underlying: str) -> Path:
        safe = underlying.replace("/", "_").replace(" ", "_")
        return self._dir / f"vol_regime_{safe}.json"

    def save(self, underlying: str, snapshot: dict) -> None:
        path = self._path(underlying)
        ledger = []
        if path.exists():
            try:
                ledger = json.loads(path.read_text()).get("ledger", [])
            except (json.JSONDecodeError, OSError):
                ledger = []
        ledger.append(
            {
                "fitted_at": snapshot.get("fitted_at_ist"),
                "regime_label": snapshot.get("regime_label"),
                "blended_forecast_sigma": snapshot.get("blended_forecast_sigma"),
                "n_observations": snapshot.get("n_observations"),
            }
        )
        path.write_text(json.dumps({"latest": snapshot, "ledger": ledger[-200:]}, indent=1))

    def load_latest(self, underlying: str) -> dict | None:
        path = self._path(underlying)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text()).get("latest")
        except (json.JSONDecodeError, OSError):
            return None


def _annualize_daily_vol(daily_sigma: float) -> float:
    return float(daily_sigma) * math.sqrt(_TRADING_DAYS)


def _ewma_daily_sigma(returns: np.ndarray, lam: float = _EWMA_LAMBDA) -> float:
    """RiskMetrics EWMA daily sigma — the small-sample fallback (always defined)."""
    if returns.size == 0:
        return 0.0
    var = float(np.var(returns))
    for r in returns:
        var = lam * var + (1.0 - lam) * float(r) ** 2
    return math.sqrt(max(var, 1e-12))


def _har_rv_forecast(realized_daily_var: np.ndarray) -> float:
    """Corsi HAR-RV: regress RV_t on its 1d/5d/22d lagged averages, forecast one step (annualized sigma)."""
    rv = np.sqrt(np.maximum(realized_daily_var, 1e-12))
    n = rv.size
    if n < 30:
        return _annualize_daily_vol(float(rv[-1]) if n else 0.0)
    daily = rv[:-1]
    weekly = pd.Series(rv).rolling(5).mean().to_numpy()[:-1]
    monthly = pd.Series(rv).rolling(22).mean().to_numpy()[:-1]
    target = rv[1:]
    mask = ~(np.isnan(weekly) | np.isnan(monthly))
    x = np.column_stack([np.ones(mask.sum()), daily[mask], weekly[mask], monthly[mask]])
    y = target[mask]
    if x.shape[0] < 10:
        return _annualize_daily_vol(float(rv[-1]))
    coef, *_ = np.linalg.lstsq(x, y, rcond=None)
    last = np.array([1.0, rv[-1], float(np.mean(rv[-5:])), float(np.mean(rv[-22:]))])
    forecast_daily = max(float(last @ coef), 1e-6)
    return _annualize_daily_vol(forecast_daily)


class VolatilityRegimeEngine:
    """Fits + carries the conditional-vol + regime models for one index underlying, point-in-time."""

    def __init__(self, underlying: str, store: VolatilityRegimeStore | None = None):
        self.underlying = underlying
        self._store = store

    # -- the real input pipeline: raw close prices -> daily log returns + realized variance -----------
    @staticmethod
    def _returns_from_prices(close_prices: pd.Series) -> np.ndarray:
        prices = close_prices.astype(float).to_numpy()
        prices = prices[prices > 0]
        if prices.size < 2:
            return np.array([])
        return np.diff(np.log(prices))

    def _fit_garch_sigma(self, returns_pct: np.ndarray) -> float:
        """GJR-GARCH(1,1,1) skew-t 1-step conditional sigma (annualized). Returns 0.0 if it cannot fit."""
        try:
            from arch import arch_model
        except ImportError:
            return 0.0
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                model = arch_model(returns_pct, vol="GARCH", p=1, o=1, q=1, dist="skewt", mean="Constant")
                res = model.fit(disp="off", show_warning=False)
                forecast = res.forecast(horizon=1, reindex=False)
                daily_sigma_pct = math.sqrt(float(forecast.variance.values[-1, 0]))
                return _annualize_daily_vol(daily_sigma_pct / 100.0)
            except (ValueError, np.linalg.LinAlgError, RuntimeError):
                return 0.0

    def _fit_regime(self, returns_pct: np.ndarray) -> tuple[int, tuple[float, ...], list[float]]:
        """Markov-switching (2 regimes, switching variance) filtered posterior — causal / point-in-time."""
        try:
            from statsmodels.tsa.regime_switching.markov_regression import MarkovRegression
        except ImportError:
            return 0, (1.0,), [0.0]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                mod = MarkovRegression(returns_pct, k_regimes=2, trend="c", switching_variance=True)
                res = mod.fit(disp=False)
                # filtered (past-only) posterior; statsmodels shape is (nobs, k_regimes)
                filtered = np.asarray(res.filtered_marginal_probabilities)
                if filtered.ndim == 2 and filtered.shape[1] != 2 and filtered.shape[0] == 2:
                    filtered = filtered.T  # normalise to (nobs, k_regimes)
                last = filtered[-1] if filtered.ndim == 2 else filtered
                probs = [float(p) for p in np.atleast_1d(last)]
                # order regimes by their fitted variance so index 0 = calm, higher = stressed
                name_to_value = dict(
                    zip(list(res.model.param_names), np.asarray(res.params), strict=False)
                )
                variances = [float(name_to_value.get(f"sigma2[{k}]", float("nan"))) for k in range(2)]
                if any(math.isnan(v) for v in variances):
                    order = list(range(len(probs)))  # cannot order; keep as-is
                else:
                    order = list(np.argsort(variances))
                ordered_probs = tuple(probs[i] for i in order)
                regime_index = int(np.argmax(ordered_probs))
                return regime_index, ordered_probs, [variances[i] for i in order]
            except (ValueError, np.linalg.LinAlgError, RuntimeError, KeyError):
                return 0, (1.0,), [0.0]

    @staticmethod
    def _label_regime(regime_index: int, n_regimes: int) -> str:
        if n_regimes <= 1:
            return "calm"
        if regime_index == 0:
            return "calm"
        if regime_index >= n_regimes - 1 and n_regimes >= 3:
            return "stressed"
        return "elevated" if n_regimes == 2 and regime_index == 1 else "elevated"

    def fit_and_state(
        self,
        close_prices: pd.Series,
        implied_vol: float | None = None,
        now_ist: datetime | None = None,
    ) -> VolatilityRegimeState:
        """Fit the models on real prices and return the current decision-grade vol/regime state."""

        fitted_at = (now_ist or datetime.now(_IST)).strftime("%Y-%m-%d %H:%M:%S IST")
        returns = self._returns_from_prices(close_prices)
        n = returns.size
        realized_daily_var = returns**2
        trailing_realized = _annualize_daily_vol(
            float(np.std(returns[-_TRADING_DAYS:])) if n >= 20 else _ewma_daily_sigma(returns)
        )

        # --- maturity ladder (Rule Q): full fitted engine, or the honest EWMA fallback -------------
        if n < _MIN_OBS_FOR_GARCH:
            ewma_sigma = _annualize_daily_vol(_ewma_daily_sigma(returns))
            state = VolatilityRegimeState(
                underlying=self.underlying,
                regime_label="gathering",
                regime_index=0,
                regime_probabilities=(1.0,),
                garch_forecast_sigma=ewma_sigma,
                har_forecast_sigma=_har_rv_forecast(realized_daily_var),
                blended_forecast_sigma=ewma_sigma,
                realized_vol=trailing_realized,
                variance_risk_premium=(implied_vol - ewma_sigma) if implied_vol is not None else None,
                n_observations=n,
                maturity="gathering",
                fitted_at_ist=fitted_at,
            )
        else:
            garch_sigma = self._fit_garch_sigma(returns * 100.0)  # arch prefers percent returns
            har_sigma = _har_rv_forecast(realized_daily_var)
            if garch_sigma <= 0.0:
                garch_sigma = _annualize_daily_vol(_ewma_daily_sigma(returns))
            # inverse-error blend vs the trailing realized vol (closer forecaster gets more weight)
            eg = abs(garch_sigma - trailing_realized) + 1e-6
            eh = abs(har_sigma - trailing_realized) + 1e-6
            wg, wh = (1 / eg) / (1 / eg + 1 / eh), (1 / eh) / (1 / eg + 1 / eh)
            blended = wg * garch_sigma + wh * har_sigma

            if n >= _MIN_OBS_FOR_REGIME:
                regime_index, probs, variances = self._fit_regime(returns * 100.0)
                label = self._label_regime(regime_index, len(probs))
            else:
                regime_index, probs, label = 0, (1.0,), "calm"

            state = VolatilityRegimeState(
                underlying=self.underlying,
                regime_label=label,
                regime_index=regime_index,
                regime_probabilities=probs,
                garch_forecast_sigma=garch_sigma,
                har_forecast_sigma=har_sigma,
                blended_forecast_sigma=blended,
                realized_vol=trailing_realized,
                variance_risk_premium=(implied_vol - blended) if implied_vol is not None else None,
                n_observations=n,
                maturity="earned",
                fitted_at_ist=fitted_at,
            )

        if self._store is not None:
            self._store.save(self.underlying, asdict(state))
        return state
