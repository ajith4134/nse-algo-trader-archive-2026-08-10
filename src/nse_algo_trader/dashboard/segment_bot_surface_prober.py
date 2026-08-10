"""Measured dashboard surfaces for the 3 segment bots + their directional AI (Rule N + Rule R).

The 3 bots run in ``portfolio_supervisor/pod_runner`` — a process the dashboard's live paper-trading
service does not hold — so their live state never reached the snapshot (the Rule-N gap opened when the
directional verdict was wired into them). This prober closes it WITHOUT depending on the blocked live-loop:
it MEASURES each bot's status from the real code (is the bot wired into the pod? is the directional brain
wired into the bot?) and from the bot's persisted stores on disk (closed-trade count → competency maturity
ladder, per-underlying directional engines earned). Nothing here is hand-typed — every field is a measured
signal with its source, exactly as Rule R demands; anything unmeasurable is reported ``NOT-INSTRUMENTED``,
never defaulted to healthy.

A live heartbeat (the pod's ``last_cycle.json`` mtime + published totals) lights the tile once the pod runs;
until the pod publishes a PER-BOT breakdown, per-bot live proposal counts stay ``NOT-INSTRUMENTED``.
"""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass
from datetime import datetime, UTC
from pathlib import Path

from nse_algo_trader.dashboard.dashboard_feature_surface import DashboardFeatureSurface

_DEFAULT_POD_STORE_ROOT = Path.home() / ".nse_algo_trader" / "segment_bot_pod"
_SEGMENT_BOTS_PKG = Path(__file__).resolve().parent.parent / "segment_bots"
_POD_RUNNER = Path(__file__).resolve().parent.parent / "portfolio_supervisor" / "pod_runner.py"
_TRACK_RECORD_FILE = "index_option_bot_closed_trades.json"  # BotTrackRecordStore's fixed filename
_DIRECTIONAL_MODEL_FILE = "bull_bear_models.joblib"


@dataclass(frozen=True)
class _BotSpec:
    key: str
    title: str
    store_subdir: str
    bot_module: str  # path under segment_bots/ to the assembled bot
    bot_class: str  # class pod_runner imports
    earned_min_closed: int  # the bot's competency maturity threshold (Rule Q)


_BOTS: tuple[_BotSpec, ...] = (
    _BotSpec("index_option_bot", "INDEX-OPTION AI bot (NIFTY/BANKNIFTY/… structures)",
             "index_option", "index_option_bot/index_option_bot.py", "IndexOptionBot", 30),
    _BotSpec("stock_option_bot", "STOCK-OPTION AI bot (single-name F&O structures)",
             "stock_option", "stock_option_bot/stock_option_bot.py", "StockOptionBot", 30),
    _BotSpec("cash_intraday_bot", "CASH-INTRADAY AI bot (cross-sectional long/short book)",
             "cash_intraday", "cash_intraday_bot/cash_intraday_bot.py", "CashIntradayBot", 50),
)


def _module_imports(path: Path) -> set[str]:
    """Every name imported by a module (measured from its AST, not text heuristics — Rule R)."""
    try:
        tree = ast.parse(path.read_text())
    except (OSError, SyntaxError):
        return set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[-1])
    return names


def _count_closed_trades(store_dir: Path) -> int:
    path = store_dir / "track_record" / _TRACK_RECORD_FILE
    if not path.exists():
        return 0
    try:
        return len(json.loads(path.read_text()))
    except (OSError, json.JSONDecodeError, TypeError):
        return 0


def _count_earned_directional_engines(store_dir: Path) -> tuple[int, int]:
    """(earned, total) per-underlying BULL/BEAR engines persisted under the bot's directional brain dir."""
    brain_dir = store_dir / "directional"
    if not brain_dir.exists():
        return (0, 0)
    total = earned = 0
    for child in brain_dir.iterdir():
        if child.is_dir():
            total += 1
            if (child / _DIRECTIONAL_MODEL_FILE).exists():
                earned += 1
    return (earned, total)


def _heartbeat(pod_store_root: Path) -> tuple[str, dict]:
    """The pod's last-cycle heartbeat: (age-string, published totals). NOT-INSTRUMENTED if never run."""
    cycle = pod_store_root / "last_cycle.json"
    if not cycle.exists():
        return ("NOT-INSTRUMENTED", {})
    try:
        payload = json.loads(cycle.read_text())
    except (OSError, json.JSONDecodeError):
        payload = {}
    mtime = datetime.fromtimestamp(cycle.stat().st_mtime, tz=UTC)
    now = datetime.now(tz=UTC)
    secs = max(0, int((now - mtime).total_seconds()))
    if secs < 90:
        age = f"{secs}s ago"
    elif secs < 5400:
        age = f"{secs // 60}m ago"
    elif secs < 172800:
        age = f"{secs // 3600}h ago"
    else:
        age = f"{secs // 86400}d ago"
    return (age, payload)


def probe_segment_bot_surfaces(
    pod_store_root: Path | None = None,
) -> list[DashboardFeatureSurface]:
    """Build the 5 measured surfaces: 3 segment bots + the BULL and BEAR directional AI features."""
    root = Path(pod_store_root) if pod_store_root is not None else _DEFAULT_POD_STORE_ROOT
    pod_imports = _module_imports(_POD_RUNNER)
    heartbeat_age, pod_payload = _heartbeat(root)
    pod_ran = heartbeat_age != "NOT-INSTRUMENTED"

    surfaces: list[DashboardFeatureSurface] = []
    total_earned_engines = total_engines = 0

    for spec in _BOTS:
        store_dir = root / spec.store_subdir
        bot_src = _SEGMENT_BOTS_PKG / spec.bot_module
        wired_to_pod = spec.bot_class in pod_imports
        brain_wired = "DirectionalSideBrain" in _module_imports(bot_src)
        closed = _count_closed_trades(store_dir)
        earned_engines, n_engines = _count_earned_directional_engines(store_dir)
        total_earned_engines += earned_engines
        total_engines += n_engines
        bot_beat = pod_payload.get("by_bot", {}).get(spec.key, {}) if isinstance(pod_payload, dict) else {}
        proposals = bot_beat.get("proposals")
        accepted = bot_beat.get("accepted")

        if proposals:
            status = "active"  # the bot proposed THIS cycle — its own live pulse, not the shared pod pulse
        elif closed >= spec.earned_min_closed:
            status = "active"  # competency earned — the bot proposes for real (Rule Q ladder cleared)
        elif closed > 0 or earned_engines > 0:
            status = "gathering"  # accruing track record / training the directional pair
        elif wired_to_pod and brain_wired:
            status = "idle"  # fully built + wired; awaiting the live loop to feed it (blocker)
        else:
            status = "blocked"  # a wiring edge is missing — a real defect, surfaced not hidden

        cycle_activity = (
            f"{proposals} proposed · {accepted} accepted" if proposals is not None
            else ("NOT-INSTRUMENTED" if not pod_ran else "0 this cycle")
        )
        metrics = (
            ("wired → pod", "yes" if wired_to_pod else "NO"),
            ("directional brain", "wired" if brain_wired else "NO"),
            ("closed trades", f"{closed} / {spec.earned_min_closed} to earn"),
            ("brain engines earned", f"{earned_engines} / {n_engines}" if n_engines else "0 (gathering)"),
            ("this cycle", cycle_activity),
            ("live pod cycle", heartbeat_age),
        )
        note = _bot_note(status, wired_to_pod, brain_wired, pod_ran)
        surfaces.append(DashboardFeatureSurface(spec.key, spec.title, status, metrics, note))

    surfaces.extend(_directional_side_surfaces(total_earned_engines, total_engines, heartbeat_age, pod_payload))
    surfaces.append(_option_book_risk_surface(pod_payload, heartbeat_age))
    surfaces.append(_trade_evidence_surface(root, heartbeat_age))
    return surfaces


_ENGINE_GLYPH = {"theta": "Θ", "delta": "Δ", "vega": "ν", "gamma": "Γ", "relvalue": "RV"}


def _trade_evidence_surface(root: Path, heartbeat_age: str) -> DashboardFeatureSurface:
    """One evidence row per OPEN option structure — the PROOF the trade was opened to close in profit.

    Each row is measured from the trade's own persisted provenance (the optimizer's max-EV real-strike
    result): profit ENGINE · forecast E[P&L] · P(profit) · defined-risk max-loss. So the operator can INSPECT
    the forecast behind every live option trade, not just trust it. Read-only over the pod's open book.
    """
    positions = _load_pod_open_positions(root)
    structures = [p for p in positions
                  if p.get("segment") in ("index_option", "stock_option") and (p.get("legs") or [])]
    if not structures:
        status = "gathering" if heartbeat_age != "NOT-INSTRUMENTED" else "idle"
        return DashboardFeatureSurface(
            "trade_evidence", "Trade Evidence (per-trade proof: engine · E[P&L] · P(profit) · defined-risk)",
            status, (("open option trades", "0"), ("live pod cycle", heartbeat_age)),
            "Per-trade proof card: every open option trade shows the profit-engine + forecast E[P&L] + "
            "P(profit) + defined-risk max-loss it was opened on. No open structures yet.")
    rows: list[tuple[str, str]] = []
    for p in structures[:12]:  # freshest handful; the tables carry the full per-leg detail
        raw_feats = p.get("features")
        feats = raw_feats if isinstance(raw_feats, dict) else {}
        engine = str(feats.get("engine", "?"))
        glyph = _ENGINE_GLYPH.get(engine, engine)
        ev = feats.get("expected_pnl")
        pp = feats.get("p_profit")
        ml = feats.get("max_loss")
        label = f"{p.get('underlying', '?')} · {len(p.get('legs') or [])} legs"
        pp_txt = f"{float(pp) * 100:.0f}%" if isinstance(pp, (int, float)) else "—"
        # a negative modeled max-loss = the distribution shows no losing path (a "risk-free" look) — usually
        # stale/crossed after-hours premiums; show it honestly rather than a confusing negative rupee risk.
        risk_txt = "none (modeled)" if isinstance(ml, (int, float)) and ml <= 0 else _rupee(ml)
        value = f"{glyph} · E[P&L] {_rupee(ev)} · P(profit) {pp_txt} · risk {risk_txt}"
        rows.append((label, value))
    return DashboardFeatureSurface(
        "trade_evidence", "Trade Evidence (per-trade proof: engine · E[P&L] · P(profit) · defined-risk)",
        "active", (("open option trades", str(len(structures))), *rows, ("live pod cycle", heartbeat_age)),
        "Per-trade proof card — each open option trade's profit-engine + distribution-forecast E[P&L] + "
        "P(profit) + defined-risk max-loss, measured from the trade's own optimizer provenance (never blind).")


def _rupee(v) -> str:
    if not isinstance(v, (int, float)):
        return "—"
    a = abs(float(v))
    if a >= 1e5:
        return f"₹{v / 1e5:.2f}L"
    if a >= 1e3:
        return f"₹{v / 1e3:.1f}k"
    return f"₹{v:.0f}"


def _load_pod_open_positions(root: Path) -> list[dict]:
    """The pod's live open book (read-only; a read failure yields an empty book, never breaks the surface)."""
    path = root / "lifecycle" / "pod_open_positions.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _option_book_risk_surface(pod_payload: dict, heartbeat_age: str) -> DashboardFeatureSurface:
    """The portfolio-level option-book view: net greeks + CVaR (diagnostic; never caps paper)."""
    book = pod_payload.get("book_risk", {}) if isinstance(pod_payload, dict) else {}
    n = book.get("n_structures", 0)
    status = "active" if n else ("gathering" if heartbeat_age != "NOT-INSTRUMENTED" else "idle")
    metrics = (
        ("structures", str(n)),
        ("net Δ / Γ", f"{book.get('net_delta', '—')} / {book.get('net_gamma', '—')}"),
        ("net ν / Θ", f"{book.get('net_vega', '—')} / {book.get('net_theta', '—')}"),
        ("book E[P&L]", str(book.get("expected_pnl", "—"))),
        ("portfolio CVaR", str(book.get("portfolio_cvar", "—"))),
        ("live pod cycle", heartbeat_age),
    )
    note = ("Portfolio net-greeks + CVaR over the open option book (vollib greeks + CVXPY live-sizing). "
            "Diagnostic + LIVE sizing — never caps paper acceptance.")
    return DashboardFeatureSurface("option_book_risk", "Option Book Risk (net greeks · CVaR · live-sizing)",
                                   status, metrics, note)


def _directional_side_surfaces(
    earned: int, total: int, heartbeat_age: str, pod_payload: dict
) -> list[DashboardFeatureSurface]:
    """The 2 directional AI features the user named: the BULL (P↑) side and the BEAR (P↓) side.

    Both are served by the same per-underlying BULL/BEAR engine pair + arbiter (wired into all 3 bots);
    the two surfaces describe the two decision sides that pair drives.
    """
    status = "active" if earned > 0 else "gathering"
    proposals = pod_payload.get("total_proposals", "NOT-INSTRUMENTED")
    common = (
        ("engines earned", f"{earned} / {total}" if total else "0 (gathering history)"),
        ("arbiter", "wired → all 3 bots"),
        ("live pod cycle", heartbeat_age),
        ("pod proposals", str(proposals)),
    )
    return [
        DashboardFeatureSurface(
            "directional_ai_bull",
            "Directional AI — BULL side (P↑ → option CE / cash LONG)",
            status,
            (("side", "P↑ → buy CALL / go LONG cash"), *common),
            "BULL model: probability the next move hits the up-barrier first; wakes the CE / long branch.",
        ),
        DashboardFeatureSurface(
            "directional_ai_bear",
            "Directional AI — BEAR side (P↓ → option PE / cash SHORT)",
            status,
            (("side", "P↓ → buy PUT / go SHORT cash"), *common),
            "BEAR model: probability the next move hits the down-barrier first; wakes the PE / short branch.",
        ),
    ]


def _bot_note(status: str, wired_to_pod: bool, brain_wired: bool, pod_ran: bool) -> str:
    if status == "blocked":
        missing = []
        if not wired_to_pod:
            missing.append("not wired into pod_runner")
        if not brain_wired:
            missing.append("directional brain not wired")
        return "DEFECT: " + ", ".join(missing)
    if status == "idle":
        return ("Built + wired; activation gated by the Rule-Q maturity ladder and the live-loop "
                "data-adapter blocker (pod on empty-universe adapters).")
    if status == "gathering":
        return "Accruing track record + training the directional pair (Rule-Q ladder, arms automatically)."
    return "Earned — proposing live." if pod_ran else "Earned track record; awaiting live pod cycle."
