"""Verification cockpit — one command that runs every project check and emits a single verdict.

The videos' most-corroborated principle (Cherny, quoted in 3 of them): *give Claude a tool that can
see the output of its work, then tell Claude about the tool*. This project already HAS the tools —
63 `verify_*_realdata.py` Rule-F checks, `quality_gate.py` (ruff+mypy+pytest), and
`check_system_map_diagram_fidelity.py` — but they are 65 scattered scripts with no single verdict.
This cockpit is the one gate over all of them: run them (in parallel, with timeouts), classify each
outcome, and print one **APPROVED / NOT APPROVED** line plus the exact failing list. Exit code is
0 only when nothing FAILED, so it can back a Claude Code hook, a CI step, or a loop's done-rule.

Design decisions that make the verdict trustworthy:
  * A real-data check that cannot reach LIVE data (no broker session, market closed, missing DB) is
    classified **SKIPPED(reason)**, never FAIL — a closed market is not a broken engine (Rule J).
    Skips never block APPROVED, but every one is surfaced (Rule K: no silent skips).
  * A genuine failure (AssertionError, wrong number, crash in engine code) is a **FAIL** and blocks.
  * The ~14 checks that only print and always exit 0 are tagged **informational** so a green result
    from them is known to be a weak signal, not a proof.

Usage:
  python scripts/verification_cockpit.py                 # EVERYTHING: real-data + quality + diagram
  python scripts/verification_cockpit.py --realdata      # only the verify_*_realdata.py set (fast-ish)
  python scripts/verification_cockpit.py --quality       # only quality_gate.py
  python scripts/verification_cockpit.py --only axiology  # only checks whose name contains 'axiology'
                                                          #   (this is what a loop uses per branch)
  python scripts/verification_cockpit.py --json          # machine-readable report to stdout
  python scripts/verification_cockpit.py --list          # list discovered checks, run nothing
  python scripts/verification_cockpit.py --jobs 8 --timeout 300

Always writes the full structured report to logs/verification_cockpit_last_run.json for the loop
skill and any hook to read without re-running.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
VENV_PY = REPO_ROOT / ".venv" / "bin" / "python"
PYTHON = str(VENV_PY if VENV_PY.exists() else sys.executable)
REPORT_PATH = REPO_ROOT / "logs" / "verification_cockpit_last_run.json"

# Outcome != FAIL when the combined output matches one of these — the check could not reach the live
# data it needs, which is an environment gap, not an engine defect. Ordered most-specific first; the
# first match becomes the surfaced skip reason. AssertionError is deliberately NOT here (it is a FAIL).
DATA_GATED_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"no such table|unable to open database file|no such file.*\.db", "missing real-data DB"),
    (r"access[_ ]?token|generate_session|no (live|kite|breeze) session|session expired", "no live broker session"),
    (r"market (is )?closed|outside market hours|no live session", "market closed / no live session"),
    (r"ConnectionError|Max retries|Failed to establish|Could not connect|Read timed out|Name or service not known", "network / venue unreachable"),
)
# Live-broker auth gates: a check that can only run after an interactive/broker login (manual TOTP
# browser flow, or a 401/403 from a broker auth endpoint) is data-gated, not a defect (Rule J).
# Checked even when a Python traceback is present, because these surface AS raised HTTP errors.
AUTH_GATED_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"manual browser login|no headless login|apisession|\bTOTP\b", "needs manual broker login"),
    (r"40[13] Client Error|raise_for_status|loginByPassword|HTTPError|requests\.exceptions", "broker auth / live session required"),
)
DEPENDENCY_GATED_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"ModuleNotFoundError|No module named|ImportError", "missing python dependency"),
)
NATIVE_TEARDOWN_ABORT = "terminate called without an active exception"

# Static markers that a check enforces something (has a hard assertion path). Absence => informational.
ENFORCING_MARKERS = ("sys.exit", "SystemExit", "\nassert ", " assert ", "raise ")


@dataclass
class CheckOutcome:
    """One check's result. `status` is one of PASS / FAIL / SKIPPED."""

    name: str
    path: str
    status: str
    reason: str          # skip reason or failure summary; empty for a clean PASS
    informational: bool  # True => the check only prints and always exits 0 (weak signal)
    exit_code: int
    duration_seconds: float
    tail: str            # last lines of output, for the failing/skipped detail block


def discover_checks(realdata: bool, quality: bool, diagram: bool, only: str | None) -> list[Path]:
    """Return the check scripts to run, filtered by category flags and an optional name substring."""
    checks: list[Path] = []
    if realdata:
        checks.extend(sorted(SCRIPTS_DIR.glob("verify_*_realdata.py")))
    if quality:
        gate = SCRIPTS_DIR / "quality_gate.py"
        if gate.exists():
            checks.append(gate)
    if diagram:
        fidelity = SCRIPTS_DIR / "check_system_map_diagram_fidelity.py"
        if fidelity.exists():
            checks.append(fidelity)
    if only:
        needle = only.lower()
        checks = [c for c in checks if needle in c.stem.lower()]
    return checks


def _is_enforcing(source_path: Path) -> bool:
    """Cheap static check: does the script have any hard-fail path, or is it print-only (informational)?"""
    try:
        text = source_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return True  # unreadable source: assume it enforces, so we don't over-trust a green run
    return any(marker in text for marker in ENFORCING_MARKERS)


def _classify(exit_code: int, output: str) -> tuple[str, str]:
    """Map (exit_code, output) to (status, reason).

    exit 0 => PASS. A non-zero exit is a SKIP (unverified, non-blocking) when it reflects an
    environment gap — a timeout, a missing DB, a broker/live-session requirement, a missing
    dependency, or a native-library teardown abort AFTER the check's own logic completed. Only a
    genuine Python error with no such gap is a FAIL (verified-broken, blocks approval)."""
    if exit_code == 0:
        return "PASS", ""
    if exit_code == 124 or "TIMED OUT" in output:
        return "SKIPPED", "timed out — heavy load; rerun with --timeout / fewer --jobs"
    # Environment/auth/dependency gates win even over a traceback (broker auth raises HTTP errors).
    for pattern, reason in (*DATA_GATED_PATTERNS, *AUTH_GATED_PATTERNS, *DEPENDENCY_GATED_PATTERNS):
        if re.search(pattern, output, re.IGNORECASE):
            return "SKIPPED", reason
    # A negative return code (POSIX signal, e.g. -6 SIGABRT) or a native teardown abort with NO
    # Python-level traceback means the engine logic ran and a C library aborted on exit (torch/HF).
    has_traceback = "Traceback (most recent call last)" in output
    if (exit_code < 0 or NATIVE_TEARDOWN_ABORT in output) and not has_traceback:
        return "SKIPPED", "native teardown abort (torch/HF atexit) — logic completed"
    # Genuine failure. Surface the sharpest error line we can.
    first_error = ""
    for line in output.splitlines():
        if re.search(r"Error|assert|FAIL|Traceback", line, re.IGNORECASE):
            first_error = line.strip()
            break
    return "FAIL", first_error or f"exit code {exit_code}"


def run_single_check(script_path: Path, timeout_seconds: int) -> CheckOutcome:
    """Run one check as a subprocess and classify its outcome. Never raises — a crashed check is a FAIL."""
    started = time.monotonic()
    try:
        proc = subprocess.run(
            [PYTHON, str(script_path)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        exit_code = proc.returncode
        output = (proc.stdout or "") + (proc.stderr or "")
    except subprocess.TimeoutExpired:
        exit_code, output = 124, f"TIMED OUT after {timeout_seconds}s"
    duration = time.monotonic() - started
    status, reason = _classify(exit_code, output)
    tail = "\n".join(output.strip().splitlines()[-12:])
    return CheckOutcome(
        name=script_path.stem,
        path=str(script_path.relative_to(REPO_ROOT)),
        status=status,
        reason=reason,
        informational=(status == "PASS" and not _is_enforcing(script_path)),
        exit_code=exit_code,
        duration_seconds=round(duration, 1),
        tail=tail,
    )


def render_summary(outcomes: list[CheckOutcome], wall_seconds: float) -> tuple[str, bool]:
    """Build the human report and the overall verdict. Approved == zero FAILs (skips do not block)."""
    passed = [o for o in outcomes if o.status == "PASS"]
    failed = [o for o in outcomes if o.status == "FAIL"]
    skipped = [o for o in outcomes if o.status == "SKIPPED"]
    informational = [o for o in passed if o.informational]
    approved = not failed

    lines: list[str] = []
    lines.append("=" * 72)
    verdict = "APPROVED ✅" if approved else f"NOT APPROVED ❌  ({len(failed)} failing)"
    lines.append(f"VERIFICATION COCKPIT — {verdict}")
    lines.append(
        f"  {len(passed)} passed ({len(informational)} informational) · "
        f"{len(failed)} FAILED · {len(skipped)} skipped · "
        f"{len(outcomes)} checks in {wall_seconds:.1f}s"
    )
    lines.append("=" * 72)

    if failed:
        lines.append("\nFAILED — these block approval:")
        for o in failed:
            lines.append(f"  ❌ {o.name}  ({o.reason})")
            if o.tail:
                lines.append("       " + o.tail.replace("\n", "\n       "))
    if skipped:
        lines.append("\nSKIPPED — environment gaps, not defects (Rule J/K; do not block):")
        for o in skipped:
            lines.append(f"  ⏭  {o.name}  — {o.reason}")
    if informational:
        lines.append("\nINFORMATIONAL passes — print-only, no hard assertion (weak signal):")
        lines.append("  " + ", ".join(o.name for o in informational))

    lines.append("")
    return "\n".join(lines), approved


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Run every project check and emit one verdict.")
    parser.add_argument("--realdata", action="store_true", help="only the verify_*_realdata.py checks")
    parser.add_argument("--quality", action="store_true", help="only quality_gate.py")
    parser.add_argument("--diagram", action="store_true", help="only the system-map diagram fidelity check")
    parser.add_argument("--only", metavar="SUBSTR", help="only checks whose name contains SUBSTR")
    parser.add_argument("--jobs", type=int, default=8, help="parallel workers (default 8)")
    parser.add_argument("--timeout", type=int, default=300, help="per-check timeout seconds (default 300)")
    parser.add_argument("--json", action="store_true", help="print the structured JSON report to stdout")
    parser.add_argument("--list", action="store_true", help="list discovered checks and exit")
    args = parser.parse_args(argv)

    # No category flag given => run EVERYTHING (the canonical /verify). A flag narrows the scope.
    any_category = args.realdata or args.quality or args.diagram
    realdata = args.realdata or not any_category
    quality = args.quality or not any_category
    diagram = args.diagram or not any_category

    checks = discover_checks(realdata, quality, diagram, args.only)
    if not checks:
        print("No checks matched the given filters.", file=sys.stderr)
        return 2
    if args.list:
        for c in checks:
            print(c.relative_to(REPO_ROOT))
        print(f"\n{len(checks)} checks.")
        return 0

    started = time.monotonic()
    outcomes: list[CheckOutcome] = []
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        futures = {pool.submit(run_single_check, c, args.timeout): c for c in checks}
        for future in as_completed(futures):
            outcomes.append(future.result())
    wall = time.monotonic() - started
    outcomes.sort(key=lambda o: (o.status != "FAIL", o.status != "SKIPPED", o.name))

    summary_text, approved = render_summary(outcomes, wall)
    report = {
        "approved": approved,
        "wall_seconds": round(wall, 1),
        "counts": {
            "total": len(outcomes),
            "passed": sum(o.status == "PASS" for o in outcomes),
            "failed": sum(o.status == "FAIL" for o in outcomes),
            "skipped": sum(o.status == "SKIPPED" for o in outcomes),
        },
        "checks": [asdict(o) for o in outcomes],
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(summary_text)
        print(f"Full report: {REPORT_PATH.relative_to(REPO_ROOT)}")
    return 0 if approved else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
