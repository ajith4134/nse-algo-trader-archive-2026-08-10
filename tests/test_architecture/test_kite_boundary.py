"""Architecture guard: `kiteconnect` may be imported ONLY inside the broker/data seam.

Enforces the Kite-decoupled rule (idea #10, `feedback_kite_decoupled_architecture`): Kite is a bounded
execution/live-feed adapter, so the dashboard + every analysis/intelligence feature must run with no Kite
dependency. This test FAILS the moment a module outside the allowed seam packages imports `kiteconnect` —
locking the boundary against regression as new features are added.
"""

import ast
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "nse_algo_trader"

# The ONLY packages permitted to touch the Kite SDK: the broker seam (sessions/credentials/OMS) + the
# data-sourcing layer (Kite is one of several historical/live data sources). Everything else — dashboard,
# engines, brain, research, memory — must be Kite-independent.
ALLOWED_SEAM_PACKAGES = {"broker_credentials", "broker_sessions", "broker_oms", "market_data"}


def _imports_kiteconnect(source: str) -> bool:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return "kiteconnect" in source  # unparseable → fall back to text, still catch it
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name.split(".")[0] == "kiteconnect" for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] == "kiteconnect":
                return True
    return False


def _package_of(path: Path) -> str:
    rel = path.relative_to(SRC_ROOT)
    return rel.parts[0] if len(rel.parts) > 1 else "<top-level>"


def test_kiteconnect_imported_only_inside_the_broker_data_seam() -> None:
    leaks = [
        str(py.relative_to(SRC_ROOT))
        for py in SRC_ROOT.rglob("*.py")
        if _package_of(py) not in ALLOWED_SEAM_PACKAGES and _imports_kiteconnect(py.read_text(encoding="utf-8"))
    ]
    assert not leaks, (
        "Kite-decoupled boundary violated — these modules import `kiteconnect` outside the "
        f"broker/data seam {sorted(ALLOWED_SEAM_PACKAGES)}: {leaks}. Route the broker client through "
        "`broker_sessions.build_authenticated_kite_client_if_valid()` instead."
    )
