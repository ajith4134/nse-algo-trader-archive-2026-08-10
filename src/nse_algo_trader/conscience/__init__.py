"""Trunk VII · CONSCIENCE — governance / safety / law (the SUPREME trunk of the autonomous-AI
concept tree, docs/research/32-36). A machine-checkable conscience that bounds what the system is
allowed to do, so it can never gain autonomy without inviolable limits.

Branch VII.1 (built): `constitutional_core` — the constitution + an action/posture reviewer.
Queued branches build on it: Referee/audit (enforce at order sites), corrigibility, deceptive-
alignment monitor, wireheading tripwire, incident post-mortem.
"""

from __future__ import annotations

from nse_algo_trader.conscience.constitutional_core import (
    CONSTITUTION,
    ConstitutionalCore,
    ConstitutionalVerdict,
    ProposedTradingAction,
    SystemPosture,
)
from nse_algo_trader.conscience.constitutional_referee import ConstitutionalReferee
from nse_algo_trader.conscience.corrigibility_switch import CorrigibilitySwitch
from nse_algo_trader.conscience.alignment_tripwires import (
    deceptive_alignment_monitor,
    wireheading_tripwire,
)
from nse_algo_trader.conscience.incident_post_mortem import (
    IncidentPostMortem,
    SafetyIncident,
    summarize_incident_post_mortem,
)
from nse_algo_trader.conscience.incident_post_mortem_store import (
    IncidentPostMortemStore,
)
from nse_algo_trader.conscience.goal_integrity_monitor import (
    DeclaredObjective,
    GoalIntegrityVerdict,
    assess_goal_integrity,
)
from nse_algo_trader.conscience.mechanistic_interpretability import (
    InterpretabilityReport,
    explain_decision_mechanisms,
)
from nse_algo_trader.conscience.scalable_oversight import (
    OversightDecision,
    classify_oversight,
    summarize_oversight,
)
from nse_algo_trader.conscience.instrumental_convergence_limiter import (
    ConvergenceLimits,
    ConvergenceVerdict,
    assess_convergence,
)
from nse_algo_trader.conscience.red_team_harness import (
    RedTeamReport,
    red_team_champion,
)
from nse_algo_trader.conscience.ethics_law_reasoner import (
    LawComplianceReport,
    RegulatoryPosture,
    assess_regulatory_compliance,
)
from nse_algo_trader.conscience.power_budget import (
    PowerBudget,
    PowerBudgetVerdict,
    assess_power_budget,
)
from nse_algo_trader.conscience.market_data_integrity_defense import (
    SeriesIntegrityVerdict,
    screen_bar,
    screen_bar_series,
)

__all__ = [
    "CONSTITUTION",
    "ConstitutionalCore",
    "ConstitutionalReferee",
    "ConstitutionalVerdict",
    "CorrigibilitySwitch",
    "DeclaredObjective",
    "GoalIntegrityVerdict",
    "IncidentPostMortem",
    "IncidentPostMortemStore",
    "ConvergenceLimits",
    "ConvergenceVerdict",
    "InterpretabilityReport",
    "LawComplianceReport",
    "OversightDecision",
    "PowerBudget",
    "PowerBudgetVerdict",
    "RedTeamReport",
    "RegulatoryPosture",
    "SeriesIntegrityVerdict",
    "assess_convergence",
    "assess_power_budget",
    "assess_regulatory_compliance",
    "red_team_champion",
    "screen_bar",
    "screen_bar_series",
    "assess_goal_integrity",
    "classify_oversight",
    "explain_decision_mechanisms",
    "summarize_oversight",
    "ProposedTradingAction",
    "SafetyIncident",
    "SystemPosture",
    "deceptive_alignment_monitor",
    "summarize_incident_post_mortem",
    "wireheading_tripwire",
]
