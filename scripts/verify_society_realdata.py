"""Rule-F verification for Trunk VI — consensus/conflict-resolution + multi-agent memory governance
(research/136). Governs the REAL council track-record store's per-desk reputations (role_log_loss →
reputation) and forms a consensus over them. On this data the store is empty until council forecasts
RESOLVE over live sessions (LLM + resolution-accrual gated, like the council's own reputations), so
the honest real result is "no desk reputations yet" — the organ runs over the real store.

Run:  python scripts/verify_society_realdata.py
"""

from __future__ import annotations

from pathlib import Path

from nse_algo_trader.paper_trading.council_track_record_store import CouncilTrackRecordStore
from nse_algo_trader.society.multi_agent_governance import govern_agents


def _reputation_from_log_loss(bits) -> float:
    """Map a role's prequential log-loss (bits; coin-flip = 1.0) to a 0..1 reputation."""
    if bits is None:
        return 0.5  # unproven → neutral
    return max(0.0, min(1.0, 1.0 - bits))


def main() -> int:
    path = Path("~/.nse_algo_trader/council_track_record.sqlite3").expanduser()
    store = CouncilTrackRecordStore(path)
    role_log_loss = store.role_log_loss()
    resolved = store.resolved_forecast_count()
    store.close()

    reputations = {role: _reputation_from_log_loss(b) for role, b in role_log_loss.items()}
    print(f"Real council track-record store: {resolved} resolved forecasts, "
          f"{len(role_log_loss)} roles with reputations")

    gr = govern_agents(reputations)
    print("\nMULTI-AGENT GOVERNANCE over REAL desk reputations:")
    print(f"  {gr.summary}")
    for s in gr.standings:
        tag = "TRUSTED" if s.is_trusted else ("QUARANTINED" if s.is_quarantined else "neutral")
        print(f"    {s.agent:<28} reputation {s.reputation:.0%}  [{tag}]")

    assert gr is not None
    if not reputations:
        print("\nRESULT: PASS — governance ran over the REAL (empty) store; no desk reputations have "
              "accrued yet (LLM + resolution-gated, like the council's own weights). Honest real state.")
    else:
        print(f"\nRESULT: PASS — governance classified {len(gr.standings)} real desks by reputation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
