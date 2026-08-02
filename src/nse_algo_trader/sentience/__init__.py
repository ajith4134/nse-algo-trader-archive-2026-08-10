"""Trunk VIII · SENTIENCE & GLOBAL WORKSPACE — the integrator (docs/research/32-36).

The faculty modules (debate panel, prediction council, meta-allocator, causal analyst, opponent
ledger, memory reflection, the VII CONSCIENCE safety organs) each produce advisory signals in
isolation. Trunk VIII binds them into one "mind" via a Global Workspace (Baars; Dehaene; Blum &
Blum's Conscious Turing Machine): specialists compete for a limited-capacity workspace, are scored
by salience, and the winner — once it crosses an ignition threshold — is BROADCAST as the dominant
global context.

Branch VIII keystone (built): `global_workspace` — collect → score → compete → ignite → broadcast.
"""

from __future__ import annotations

from nse_algo_trader.sentience.global_workspace import (
    GlobalWorkspace,
    WorkspaceBroadcast,
    WorkspaceContribution,
    salience_score,
)
from nse_algo_trader.sentience.workspace_attention import (
    AttentionContext,
    apply_attention,
    attention_weight,
)
from nse_algo_trader.sentience.coalition_formation import Coalition, form_coalition
from nse_algo_trader.sentience.self_model import SelfModel, build_self_model
from nse_algo_trader.sentience.attention_schema import (
    AttentionSchema,
    build_attention_schema,
)
from nse_algo_trader.sentience.workspace_rumination import RuminationReport, ruminate
from nse_algo_trader.sentience.cross_modal_binding import (
    BoundPercept,
    ModalitySignal,
    bind_percept,
)
from nse_algo_trader.sentience.workspace_metacognition import (
    MetacognitionReport,
    assess_metacognition,
)
from nse_algo_trader.sentience.indicator_scoreboard import (
    ScoreboardReport,
    build_indicator_scoreboard,
)

__all__ = [
    "AttentionContext",
    "AttentionSchema",
    "BoundPercept",
    "Coalition",
    "MetacognitionReport",
    "ModalitySignal",
    "RuminationReport",
    "ScoreboardReport",
    "SelfModel",
    "assess_metacognition",
    "bind_percept",
    "build_indicator_scoreboard",
    "build_attention_schema",
    "build_self_model",
    "form_coalition",
    "ruminate",
    "GlobalWorkspace",
    "WorkspaceBroadcast",
    "WorkspaceContribution",
    "apply_attention",
    "attention_weight",
    "salience_score",
]
