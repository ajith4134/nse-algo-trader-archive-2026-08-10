"""Execution-grounded quality gate (research/159) — the proven depth levers, in one runnable check.

Runs, in order, on the TARGET paths (default: the engine packages most likely to be under active build;
pass explicit paths, or --full for the whole src tree):
  1. ruff   — lint + real bug patterns (pyflakes/bugbear/comprehensions/simplify/pyupgrade)
  2. mypy   — static type checking (pragmatic config; real errors in typed code)
  3. pytest — the test suite (targeted or full)
Prints a consolidated PASS/FAIL with per-tool findings and exits non-zero on failure — so it can back a
Claude Code hook (deterministic enforcement) and a CI step. Errors are surfaced, never swallowed (Rule O.3).

Usage:
  python scripts/quality_gate.py                       # default engine paths + full test suite
  python scripts/quality_gate.py src/nse_algo_trader/predictive_core   # a specific target
  python scripts/quality_gate.py --full                # ruff+mypy over all of src/
  python scripts/quality_gate.py --no-tests <paths>    # static analysis only (fast inner loop)
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VENV_PY = REPO_ROOT / ".venv" / "bin" / "python"
PYTHON = str(VENV_PY if VENV_PY.exists() else sys.executable)

# Default lint/type targets: the newer engine packages where rigor matters most (research/159 — scoped,
# not the whole 233-module repo, so new engines stay clean without boiling the ocean of legacy debt).
DEFAULT_TARGETS = (
    "src/nse_algo_trader/predictive_core",
    "src/nse_algo_trader/axiology",
    "src/nse_algo_trader/will",
    "src/nse_algo_trader/news_sentiment",
    "src/nse_algo_trader/capital_allocation",
    "src/nse_algo_trader/intrinsic_motivation",
    "src/nse_algo_trader/autopoiesis",
)


def _run(label: str, cmd: list) -> tuple[bool, str]:
    """Run a tool; return (passed, captured_output). Never raises — a missing tool is a FAIL, surfaced."""
    try:
        proc = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, timeout=1200)
    except FileNotFoundError as exc:
        return False, f"{label}: tool not found ({exc})"
    except subprocess.TimeoutExpired:
        return False, f"{label}: TIMED OUT"
    output = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode == 0, output.strip()


def main(argv: list) -> int:
    full = "--full" in argv
    run_tests = "--no-tests" not in argv
    paths = [a for a in argv if not a.startswith("--")]
    if full:
        targets = ["src/nse_algo_trader"]
    else:
        targets = paths or list(DEFAULT_TARGETS)

    results: list[tuple[str, bool, str]] = []

    ok, out = _run("ruff", [PYTHON, "-m", "ruff", "check", *targets])
    results.append(("ruff (lint)", ok, out))

    ok, out = _run("mypy", [PYTHON, "-m", "mypy", *targets])
    results.append(("mypy (types)", ok, out))

    if run_tests:
        test_target = paths if (paths and not full) else []
        # Map a src path to its tests dir when a single package was targeted; else run the whole suite.
        pytest_args = ["-q"]
        ok, out = _run("pytest", [PYTHON, "-m", "pytest", *pytest_args])
        results.append(("pytest (suite)", ok, out))

    print("=" * 72)
    print(f"QUALITY GATE — targets: {', '.join(targets)}")
    print("=" * 72)
    all_ok = True
    for label, ok, out in results:
        status = "PASS" if ok else "FAIL"
        all_ok = all_ok and ok
        print(f"\n[{status}] {label}")
        tail = "\n".join(out.splitlines()[-25:]) if out else "(no output)"
        print(tail)
    print("\n" + "=" * 72)
    print("QUALITY GATE: " + ("PASS ✅" if all_ok else "FAIL ❌"))
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
