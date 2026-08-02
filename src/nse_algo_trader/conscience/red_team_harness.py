"""Red-team harness (Trunk VII; research/118) — CONSCIENCE adversarial self-attack.

A safety-critical autonomous system should attack ITSELF to find failure modes before reality does.
Where the champion-challenger tournament searches for the BEST config, the red-team harness does the
opposite — it adversarially PERTURBS the champion to expose its fragility surface, over the REAL
stored sessions. Two attack vectors:
  - PARAMETER-PERTURBATION: perturb the champion ORB config into an adversarial neighbourhood and
    measure the worst-degrading variant (brittleness to mis-tuning / parameter drift).
  - ADVERSARIAL-DATA: the champion's WORST single real session (worst-case conditions).
A `fragile` verdict fires when the worst perturbation degrades mean return past a threshold OR the
worst single session is catastrophic. Reuses `replay_session_orb_backtester` (Rule I) as the
measurement atom. PURE (no I/O) — the service feeds it the real sessions + live champion config.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from nse_algo_trader.paper_trading.replay_session_orb_backtester import (
    backtest_orb_session_return,
)
from nse_algo_trader.strategy_engine.opening_range_breakout_strategy import (
    OpeningRangeBreakoutConfig,
)


@dataclass(frozen=True)
class RedTeamConfig:
    fragility_degradation_threshold: float = 0.004  # worst attack degrades mean return by ≥ this
    catastrophic_session_floor: float = -0.05       # a single session ≤ this = catastrophic tail


@dataclass(frozen=True)
class AttackResult:
    attack_name: str
    mean_return: float
    trades: int
    degradation: float  # baseline mean return − this attack's mean return (higher = worse)


@dataclass(frozen=True)
class RedTeamReport:
    baseline_return: float
    baseline_trades: int
    worst_session_return: float
    worst_attack: AttackResult | None
    fragile: bool
    attacks: tuple[AttackResult, ...] = field(default_factory=tuple)
    summary: str = ""


def _mean_return_over_sessions(sessions, config) -> tuple[float, int, float]:
    """Mean signed return, trade count, and worst single-session return under `config`."""
    returns = []
    for bars, instrument in sessions:
        r = backtest_orb_session_return(bars, instrument, config)
        if r is not None:
            returns.append(r)
    if not returns:
        return 0.0, 0, 0.0
    return sum(returns) / len(returns), len(returns), min(returns)


def _adversarial_perturbations(champion: OpeningRangeBreakoutConfig):
    """An adversarial neighbourhood of the champion config — perturbed opening-range window and
    target risk-reward, the parameters most likely to break the strategy if mis-tuned."""
    variants = []
    for minutes in (max(5, champion.opening_range_minutes - 10), champion.opening_range_minutes + 15):
        variants.append((f"opening_range_minutes={minutes}",
                         replace(champion, opening_range_minutes=minutes)))
    for rr in (max(0.5, champion.target_risk_reward_ratio - 1.0),
               champion.target_risk_reward_ratio + 1.5):
        variants.append((f"target_risk_reward_ratio={rr:g}",
                         replace(champion, target_risk_reward_ratio=rr)))
    return variants


def red_team_champion(
    sessions,
    champion_config: OpeningRangeBreakoutConfig = OpeningRangeBreakoutConfig(),
    config: RedTeamConfig = RedTeamConfig(),
) -> RedTeamReport:
    """Adversarially attack the champion over the real sessions and report its fragility surface.
    `sessions` = [(session_bars, instrument), …]."""
    baseline_mean, baseline_trades, worst_session = _mean_return_over_sessions(
        sessions, champion_config
    )
    if baseline_trades == 0:
        return RedTeamReport(
            baseline_return=0.0, baseline_trades=0, worst_session_return=0.0,
            worst_attack=None, fragile=False, attacks=(),
            summary="no champion trades over the sessions — nothing to red-team",
        )

    attacks: list[AttackResult] = []
    for name, variant in _adversarial_perturbations(champion_config):
        mean_r, trades, _ = _mean_return_over_sessions(sessions, variant)
        attacks.append(AttackResult(name, mean_r, trades, baseline_mean - mean_r))
    attacks.sort(key=lambda a: a.degradation, reverse=True)
    worst_attack = attacks[0] if attacks else None

    fragile = (
        (worst_attack is not None
         and worst_attack.degradation >= config.fragility_degradation_threshold)
        or worst_session <= config.catastrophic_session_floor
    )
    summary = (
        f"baseline {baseline_mean:+.2%}/trade ({baseline_trades} trades) · worst session "
        f"{worst_session:+.2%}"
        + (f" · worst attack '{worst_attack.attack_name}' degrades to {worst_attack.mean_return:+.2%} "
           f"(−{worst_attack.degradation:.2%})" if worst_attack else "")
        + (" · FRAGILE" if fragile else " · robust")
    )
    return RedTeamReport(
        baseline_return=baseline_mean, baseline_trades=baseline_trades,
        worst_session_return=worst_session, worst_attack=worst_attack,
        fragile=fragile, attacks=tuple(attacks), summary=summary,
    )
