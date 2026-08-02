"""Mechanical OSS-candidate probe — sourcing triage from FACTS, not README prose.

Why this exists (research/171). The `sourcing-oss-parts` skill triaged candidates by reading their
README first. READMEs are marketing: they overstate maturity, headline experimental paths, and are
silent on the things that actually decide fitness (does it install on THIS aarch64 box? does its test
suite cover the edge case I need? is it quietly known-wrong?). Worse, the README pass made the
IRREVERSIBLE decision (elimination) on the least reliable evidence, while the expensive deep-scan only
confirmed an already-chosen winner. This tool replaces that triage with machine-readable facts.

What it gathers per candidate (all network calls concurrent, every failure surfaced — Rule O.3):
  · PyPI      — latest version, release age, 12-month release cadence, requires_python, yanked status,
                and the DISTRIBUTION FILES for the latest release → platform-support classification
                (pure-python / aarch64 wheel / sdist-only / x86_64-only) for THIS machine.
  · GitHub    — stars, last push (age in days), open issues, license, archived flag, forks.
                The repo is auto-derived from PyPI's project_urls; override with owner/name syntax.
  · Defects   — GitHub issue-search count for correctness words ("incorrect", "wrong results", "nan"),
                a defect oracle no README will ever volunteer.
  · Install   — `pip install --dry-run --no-deps` resolves what pip would ACTUALLY pick for this
                interpreter+platform, without mutating the venv. The decisive ARM64 answer.
  · Surface   — optional: import the module and introspect the callables you named, so "does it produce
                my I/O shape" is answered by signatures rather than by prose.
  · Tests     — optional: shallow-clone and grep the TEST SUITE for a capability keyword. Tests are the
                real specification; a capability with no test is not a guarantee.

TRIAGE ONLY. The composite score ranks what to look at first — it never licenses a rejection. Under the
Rule O.1 evidence tiers, dropping a candidate on correctness/depth/quality grounds requires reading the
implementing source, running it, or citing a specific issue. This tool exists to make that cheap.

Usage:
  python scripts/probe_oss_candidates.py lifelines scikit-survival reliability
  python scripts/probe_oss_candidates.py pybreaker tenacity --needs half_open
  python scripts/probe_oss_candidates.py lifelines --surface lifelines:WeibullAFTFitter,CoxPHFitter
  python scripts/probe_oss_candidates.py networkx --repo networkx=networkx/networkx --json out.json

Auth: set GITHUB_TOKEN to lift GitHub's unauthenticated limits (60 req/hr core, 10 req/min search).
Without it the tool still runs and reports rate-limiting explicitly instead of silently degrading.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import importlib
import inspect
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, UTC
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"
PROBE_PYTHON = str(VENV_PYTHON if VENV_PYTHON.exists() else sys.executable)

PYPI_JSON_URL = "https://pypi.org/pypi/{package}/json"
GITHUB_REPO_API_URL = "https://api.github.com/repos/{owner_and_name}"
GITHUB_ISSUE_SEARCH_URL = "https://api.github.com/search/issues?q={query}"
# Google/OpenSSF deps.dev — Scorecard health checks, unauthenticated and unmetered (research/171 §6).
DEPS_DEV_PROJECT_URL = "https://api.deps.dev/v3alpha/projects/{project_key}"
NETWORK_TIMEOUT_SECONDS = 20

# Words that surface "this library computes the wrong answer" issues — the defect oracle.
CORRECTNESS_DEFECT_TERMS = ("incorrect", "wrong")

# The machine this project runs on. Wheel filenames are classified against these tags.
AARCH64_WHEEL_TAGS = ("aarch64", "arm64")
X86_ONLY_WHEEL_TAGS = ("x86_64", "amd64", "i686", "win32", "win_amd64", "macosx")
PURE_PYTHON_WHEEL_TAG = "none-any"

GITHUB_URL_PATTERN = re.compile(r"github\.com/([A-Za-z0-9._-]+)/([A-Za-z0-9._-]+)")


# --------------------------------------------------------------------------------------------------
# Fact records — one dataclass per evidence source, each carrying its own error string so a failed
# probe is VISIBLE in the output rather than silently blank (Rule O.3).
# --------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class PlatformInstallability:
    """How well the latest release's distribution files serve THIS interpreter + CPU architecture."""

    classification: str  # pure-python · aarch64-wheel · sdist-only · x86_64-only · unknown
    distribution_filenames: tuple[str, ...] = ()

    @property
    def is_disqualifying(self) -> bool:
        """x86-only wheels with no sdist cannot be installed on this aarch64 box at all."""
        return self.classification == "x86_64-only"


@dataclass(frozen=True)
class PyPiPackageFacts:
    package_name: str
    latest_version: str = ""
    summary: str = ""
    declared_license: str = ""
    requires_python: str = ""
    latest_release_age_days: int | None = None
    releases_in_last_12_months: int = 0
    is_yanked: bool = False
    installability: PlatformInstallability = field(
        default_factory=lambda: PlatformInstallability("unknown")
    )
    github_owner_and_name: str = ""
    probe_error: str = ""


@dataclass(frozen=True)
class GitHubRepositoryFacts:
    owner_and_name: str = ""
    star_count: int | None = None
    days_since_last_push: int | None = None
    open_issue_count: int | None = None
    fork_count: int | None = None
    spdx_license: str = ""
    is_archived: bool = False
    probe_error: str = ""


@dataclass(frozen=True)
class CorrectnessDefectSignal:
    """Count of issues whose text suggests the library returns wrong answers."""

    matching_issue_count: int | None = None
    probe_error: str = ""


@dataclass(frozen=True)
class OpenSsfScorecardFacts:
    """Google/OpenSSF Scorecard health checks, served by deps.dev (research/171 §6).

    Sourced rather than reimplemented (Rule P.3): Scorecard's `Maintained` check measures SUSTAINED
    commit/issue activity over 90 days, which is strictly better than the last-push-date heuristic —
    a repo can show a recent push and still score 0 for maintenance.
    """

    overall_score: float | None = None
    check_scores: tuple[tuple[str, int], ...] = ()
    probe_error: str = ""

    def score_for_check(self, check_name: str) -> int | None:
        for name, score in self.check_scores:
            if name == check_name:
                return score
        return None


@dataclass(frozen=True)
class PipResolutionEvidence:
    """What pip would ACTUALLY install here — resolved without mutating the environment."""

    resolved_distribution: str = ""
    would_install: bool = False
    probe_error: str = ""


@dataclass(frozen=True)
class ImportSurfaceEvidence:
    """Signatures of the specific callables the caller needs — I/O shape as fact, not prose."""

    inspected_signatures: tuple[tuple[str, str], ...] = ()
    probe_error: str = ""


@dataclass(frozen=True)
class TestSuiteEvidence:
    """Whether the project's own TESTS exercise the capability we need (tests = the real spec)."""

    capability_keyword: str = ""
    matching_test_files: tuple[str, ...] = ()
    total_test_files: int = 0
    probe_error: str = ""


@dataclass(frozen=True)
class CandidateProbeReport:
    package_name: str
    pypi: PyPiPackageFacts
    github: GitHubRepositoryFacts
    defects: CorrectnessDefectSignal
    scorecard: OpenSsfScorecardFacts
    pip_resolution: PipResolutionEvidence
    import_surface: ImportSurfaceEvidence
    test_suite: TestSuiteEvidence
    triage_score: float = 0.0
    disqualifying_reasons: tuple[str, ...] = ()


# --------------------------------------------------------------------------------------------------
# Network probes
# --------------------------------------------------------------------------------------------------


def _fetch_json(url: str) -> tuple[dict, str]:
    """GET a JSON document. Returns (payload, error_message) — never raises, never swallows silently."""
    request = urllib.request.Request(url, headers=_request_headers())
    try:
        with urllib.request.urlopen(request, timeout=NETWORK_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8")), ""
    except urllib.error.HTTPError as error:
        if error.code == 403:
            return {}, "HTTP 403 — GitHub rate limit hit (set GITHUB_TOKEN to lift it)"
        if error.code == 404:
            return {}, "HTTP 404 — not found"
        return {}, f"HTTP {error.code}"
    except urllib.error.URLError as error:
        return {}, f"network error: {error.reason}"
    except (TimeoutError, json.JSONDecodeError, ValueError) as error:
        return {}, f"{type(error).__name__}: {error}"


def _request_headers() -> dict[str, str]:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "nse-algo-trader-oss-probe"}
    github_token = os.environ.get("GITHUB_TOKEN", "").strip()
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"
    return headers


def classify_wheel_platform_support(distribution_filenames: tuple[str, ...]) -> PlatformInstallability:
    """Classify a release's distribution files for THIS aarch64 Linux box.

    pure-python  — a `py3-none-any` wheel: installs anywhere, no compilation.
    aarch64-wheel— a prebuilt wheel for this architecture: installs fast, no toolchain needed.
    sdist-only   — source only: installable, but needs a compiler and can fail on native extensions.
    x86_64-only  — wheels exist but none for this architecture and no sdist: NOT installable here.
    """
    if not distribution_filenames:
        return PlatformInstallability("unknown", distribution_filenames)
    lowered = tuple(name.lower() for name in distribution_filenames)
    if any(PURE_PYTHON_WHEEL_TAG in name for name in lowered):
        return PlatformInstallability("pure-python", distribution_filenames)
    if any(tag in name for name in lowered for tag in AARCH64_WHEEL_TAGS):
        return PlatformInstallability("aarch64-wheel", distribution_filenames)
    has_sdist = any(name.endswith((".tar.gz", ".zip")) for name in lowered)
    has_foreign_wheel = any(tag in name for name in lowered for tag in X86_ONLY_WHEEL_TAGS)
    if has_sdist:
        return PlatformInstallability("sdist-only", distribution_filenames)
    if has_foreign_wheel:
        return PlatformInstallability("x86_64-only", distribution_filenames)
    return PlatformInstallability("unknown", distribution_filenames)


def derive_github_repository_from_project_urls(package_info: dict) -> str:
    """Find the canonical GitHub repo from PyPI metadata, so the caller need not supply it."""
    candidate_urls: list[str] = []
    project_urls = package_info.get("project_urls") or {}
    if isinstance(project_urls, dict):
        candidate_urls.extend(str(value) for value in project_urls.values() if value)
    for key in ("home_page", "download_url", "package_url"):
        value = package_info.get(key)
        if value:
            candidate_urls.append(str(value))
    for url in candidate_urls:
        match = GITHUB_URL_PATTERN.search(url)
        if match:
            owner, name = match.group(1), match.group(2)
            return f"{owner}/{name.removesuffix('.git')}"
    return ""


def _count_releases_in_last_12_months(releases: dict) -> tuple[int, int | None]:
    """Return (releases in the last 365 days, age in days of the newest release)."""
    now = datetime.now(UTC)
    one_year_ago = now - timedelta(days=365)
    recent_release_count = 0
    newest_upload: datetime | None = None
    for distribution_files in releases.values():
        if not isinstance(distribution_files, list) or not distribution_files:
            continue
        stamp_text = str(distribution_files[0].get("upload_time_iso_8601") or "")
        if not stamp_text:
            continue
        try:
            uploaded_at = datetime.fromisoformat(stamp_text.replace("Z", "+00:00"))
        except ValueError:
            continue
        if uploaded_at >= one_year_ago:
            recent_release_count += 1
        if newest_upload is None or uploaded_at > newest_upload:
            newest_upload = uploaded_at
    newest_age_days = (now - newest_upload).days if newest_upload else None
    return recent_release_count, newest_age_days


def fetch_pypi_package_facts(package_name: str) -> PyPiPackageFacts:
    payload, error = _fetch_json(PYPI_JSON_URL.format(package=package_name))
    if error:
        return PyPiPackageFacts(package_name=package_name, probe_error=f"PyPI: {error}")
    info = payload.get("info") or {}
    distribution_filenames = tuple(
        str(entry.get("filename", "")) for entry in (payload.get("urls") or []) if entry.get("filename")
    )
    recent_releases, newest_age_days = _count_releases_in_last_12_months(payload.get("releases") or {})
    return PyPiPackageFacts(
        package_name=package_name,
        latest_version=str(info.get("version") or ""),
        summary=str(info.get("summary") or "").strip(),
        declared_license=str(info.get("license") or "").strip()[:40],
        requires_python=str(info.get("requires_python") or ""),
        latest_release_age_days=newest_age_days,
        releases_in_last_12_months=recent_releases,
        is_yanked=bool(info.get("yanked")),
        installability=classify_wheel_platform_support(distribution_filenames),
        github_owner_and_name=derive_github_repository_from_project_urls(info),
        probe_error="",
    )


def fetch_github_repository_facts(owner_and_name: str) -> GitHubRepositoryFacts:
    if not owner_and_name:
        return GitHubRepositoryFacts(probe_error="no GitHub repo derivable from PyPI metadata")
    payload, error = _fetch_json(GITHUB_REPO_API_URL.format(owner_and_name=owner_and_name))
    if error:
        return GitHubRepositoryFacts(owner_and_name=owner_and_name, probe_error=f"GitHub: {error}")
    pushed_at_text = str(payload.get("pushed_at") or "")
    days_since_push: int | None = None
    if pushed_at_text:
        try:
            pushed_at = datetime.fromisoformat(pushed_at_text.replace("Z", "+00:00"))
            days_since_push = (datetime.now(UTC) - pushed_at).days
        except ValueError:
            days_since_push = None
    license_block = payload.get("license") or {}
    return GitHubRepositoryFacts(
        owner_and_name=owner_and_name,
        star_count=payload.get("stargazers_count"),
        days_since_last_push=days_since_push,
        open_issue_count=payload.get("open_issues_count"),
        fork_count=payload.get("forks_count"),
        spdx_license=str(license_block.get("spdx_id") or "") if isinstance(license_block, dict) else "",
        is_archived=bool(payload.get("archived")),
        probe_error="",
    )


def fetch_openssf_scorecard(owner_and_name: str) -> OpenSsfScorecardFacts:
    """Pull OpenSSF Scorecard health checks for the repo from Google's deps.dev API.

    Unauthenticated and unmetered, unlike the GitHub API — so this is the maintenance signal that
    survives when GitHub rate-limits us. Key checks: Maintained · Code-Review · Vulnerabilities ·
    Dangerous-Workflow · Pinned-Dependencies.
    """
    if not owner_and_name:
        return OpenSsfScorecardFacts(probe_error="no GitHub repo to score")
    project_key = urllib.parse.quote(f"github.com/{owner_and_name}", safe="")
    payload, error = _fetch_json(DEPS_DEV_PROJECT_URL.format(project_key=project_key))
    if error:
        return OpenSsfScorecardFacts(probe_error=f"deps.dev: {error}")
    scorecard = payload.get("scorecard") or {}
    if not scorecard:
        return OpenSsfScorecardFacts(probe_error="deps.dev has no scorecard for this project")
    checks = tuple(
        (str(entry.get("name", "")), int(entry.get("score", -1)))
        for entry in (scorecard.get("checks") or [])
        if entry.get("name")
    )
    overall = scorecard.get("overallScore")
    return OpenSsfScorecardFacts(
        overall_score=float(overall) if overall is not None else None,
        check_scores=checks,
    )


def count_correctness_defect_issues(owner_and_name: str) -> CorrectnessDefectSignal:
    """Search the issue tracker for 'this returns the wrong answer' reports."""
    if not owner_and_name:
        return CorrectnessDefectSignal(probe_error="no GitHub repo to search")
    term_clause = "+OR+".join(CORRECTNESS_DEFECT_TERMS)
    query = f"repo:{owner_and_name}+is:issue+{term_clause}"
    payload, error = _fetch_json(GITHUB_ISSUE_SEARCH_URL.format(query=query))
    if error:
        return CorrectnessDefectSignal(probe_error=f"issue search: {error}")
    return CorrectnessDefectSignal(matching_issue_count=payload.get("total_count"))


# --------------------------------------------------------------------------------------------------
# Local probes — pip resolution, import surface, test-suite evidence
# --------------------------------------------------------------------------------------------------


def probe_pip_resolution(package_name: str) -> PipResolutionEvidence:
    """Ask pip what it would install here, WITHOUT installing. The decisive ARM64/Python-version test."""
    with tempfile.TemporaryDirectory() as report_directory:
        report_path = Path(report_directory) / "pip_resolution_report.json"
        command = [
            PROBE_PYTHON, "-m", "pip", "install", "--dry-run", "--no-deps",
            "--quiet", "--report", str(report_path), package_name,
        ]
        try:
            completed = subprocess.run(command, capture_output=True, text=True, timeout=180)
        except subprocess.TimeoutExpired:
            return PipResolutionEvidence(probe_error="pip dry-run timed out (180s)")
        except OSError as error:
            return PipResolutionEvidence(probe_error=f"pip could not be launched: {error}")
        if completed.returncode != 0:
            message = (completed.stderr or completed.stdout or "").strip().splitlines()
            reason = message[-1] if message else f"exit {completed.returncode}"
            return PipResolutionEvidence(probe_error=f"pip refused: {reason[:180]}")
        if not report_path.exists():
            return PipResolutionEvidence(would_install=True, resolved_distribution="(no report emitted)")
        try:
            report = json.loads(report_path.read_text())
        except (OSError, json.JSONDecodeError) as error:
            return PipResolutionEvidence(would_install=True, probe_error=f"report unreadable: {error}")
        installs = report.get("install") or []
        if not installs:
            return PipResolutionEvidence(would_install=True, resolved_distribution="already satisfied")
        download_info = installs[0].get("download_info") or {}
        resolved_url = str(download_info.get("url") or "")
        return PipResolutionEvidence(
            resolved_distribution=resolved_url.rsplit("/", 1)[-1] or "(unnamed)",
            would_install=True,
        )


def probe_import_surface(module_name: str, attribute_names: tuple[str, ...]) -> ImportSurfaceEvidence:
    """Introspect the callables we actually need — signatures answer 'does it fit my I/O shape'."""
    try:
        module = importlib.import_module(module_name)
    except Exception as error:  # noqa: BLE001 — any import failure is real evidence, and is reported
        return ImportSurfaceEvidence(probe_error=f"import {module_name} failed: {type(error).__name__}: {error}")
    signatures: list[tuple[str, str]] = []
    for attribute_name in attribute_names:
        target = getattr(module, attribute_name, None)
        if target is None:
            signatures.append((attribute_name, "ABSENT — not exported by this module"))
            continue
        try:
            signatures.append((attribute_name, f"{attribute_name}{inspect.signature(target)}"))
        except (TypeError, ValueError):
            signatures.append((attribute_name, f"{attribute_name} (present; signature not introspectable)"))
    return ImportSurfaceEvidence(inspected_signatures=tuple(signatures))


def probe_test_suite_for_capability(owner_and_name: str, capability_keyword: str) -> TestSuiteEvidence:
    """Shallow-clone the repo and grep its TEST files for the capability we depend on.

    A feature the project does not test is a feature it does not guarantee — this is the single
    highest-value signal a README cannot provide.
    """
    if not owner_and_name or not capability_keyword:
        return TestSuiteEvidence(capability_keyword=capability_keyword, probe_error="skipped (no repo/keyword)")
    if shutil.which("git") is None:
        return TestSuiteEvidence(capability_keyword=capability_keyword, probe_error="git not available")
    with tempfile.TemporaryDirectory() as clone_directory:
        clone_command = [
            "git", "clone", "--depth", "1", "--quiet",
            f"https://github.com/{owner_and_name}.git", clone_directory,
        ]
        try:
            completed = subprocess.run(clone_command, capture_output=True, text=True, timeout=300)
        except subprocess.TimeoutExpired:
            return TestSuiteEvidence(capability_keyword=capability_keyword, probe_error="clone timed out")
        if completed.returncode != 0:
            reason = (completed.stderr or "").strip().splitlines()
            return TestSuiteEvidence(
                capability_keyword=capability_keyword,
                probe_error=f"clone failed: {reason[-1][:140] if reason else 'unknown'}",
            )
        clone_root = Path(clone_directory)
        test_files = [
            path for path in clone_root.rglob("*.py")
            if "test" in path.name.lower() or "test" in {part.lower() for part in path.parts}
        ]
        matching: list[str] = []
        lowered_keyword = capability_keyword.lower()
        for path in test_files:
            try:
                if lowered_keyword in path.read_text(errors="ignore").lower():
                    matching.append(str(path.relative_to(clone_root)))
            except OSError:
                continue
        return TestSuiteEvidence(
            capability_keyword=capability_keyword,
            matching_test_files=tuple(sorted(matching)[:12]),
            total_test_files=len(test_files),
        )


# --------------------------------------------------------------------------------------------------
# Triage scoring — ranks what to LOOK AT first. Never a rejection warrant (Rule O.1 evidence tiers).
# --------------------------------------------------------------------------------------------------


def score_candidate_triage(
    pypi: PyPiPackageFacts,
    github: GitHubRepositoryFacts,
    defects: CorrectnessDefectSignal,
    scorecard: OpenSsfScorecardFacts,
) -> tuple[float, tuple[str, ...]]:
    """Composite triage score + any DISQUALIFYING facts (hard, objective, README-visible-tier)."""
    disqualifying: list[str] = []
    if pypi.probe_error and not pypi.latest_version:
        disqualifying.append("not resolvable on PyPI")
    if pypi.installability.is_disqualifying:
        disqualifying.append("no aarch64 wheel and no sdist — cannot install on this box")
    if pypi.is_yanked:
        disqualifying.append("latest release is YANKED")
    if github.is_archived:
        disqualifying.append("repository is ARCHIVED upstream")

    score = 0.0
    installability_points = {"pure-python": 2.0, "aarch64-wheel": 2.0, "sdist-only": 0.75, "unknown": 0.25}
    score += installability_points.get(pypi.installability.classification, 0.0)

    if github.days_since_last_push is not None:
        if github.days_since_last_push <= 90:
            score += 2.0
        elif github.days_since_last_push <= 365:
            score += 1.0
        elif github.days_since_last_push <= 730:
            score += 0.25

    if pypi.releases_in_last_12_months >= 3:
        score += 1.5
    elif pypi.releases_in_last_12_months >= 1:
        score += 1.0

    if github.star_count:
        # Log-scaled so a 20k-star project does not simply outrank a well-fitted 800-star one.
        score += min(2.0, max(0.0, (len(str(int(github.star_count))) - 1) * 0.5))

    # Defect pressure: correctness issues relative to overall open-issue volume.
    if defects.matching_issue_count is not None and github.open_issue_count:
        defect_ratio = defects.matching_issue_count / max(1, github.open_issue_count)
        if defect_ratio > 0.5:
            score -= 1.0
        elif defect_ratio > 0.25:
            score -= 0.5

    # OpenSSF Scorecard: a sustained-activity + practices signal that outranks last-push-date.
    if scorecard.overall_score is not None:
        score += min(2.0, scorecard.overall_score / 5.0)
    maintained_score = scorecard.score_for_check("Maintained")
    if maintained_score == 0 and (github.days_since_last_push or 0) < 180:
        # Recent push but no sustained activity — the exact case a last-push heuristic misreads.
        score -= 0.75

    return round(score, 2), tuple(disqualifying)


# --------------------------------------------------------------------------------------------------
# Orchestration + rendering
# --------------------------------------------------------------------------------------------------


def probe_single_candidate(
    package_name: str,
    repository_override: str,
    capability_keyword: str,
    surface_request: tuple[str, tuple[str, ...]] | None,
    include_test_clone: bool,
) -> CandidateProbeReport:
    pypi = fetch_pypi_package_facts(package_name)
    owner_and_name = repository_override or pypi.github_owner_and_name
    github = fetch_github_repository_facts(owner_and_name)
    defects = count_correctness_defect_issues(owner_and_name)
    scorecard = fetch_openssf_scorecard(owner_and_name)
    pip_resolution = probe_pip_resolution(package_name)
    import_surface = (
        probe_import_surface(surface_request[0], surface_request[1])
        if surface_request
        else ImportSurfaceEvidence(probe_error="not requested")
    )
    test_suite = (
        probe_test_suite_for_capability(owner_and_name, capability_keyword)
        if include_test_clone and capability_keyword
        else TestSuiteEvidence(capability_keyword=capability_keyword, probe_error="not requested")
    )
    score, disqualifying = score_candidate_triage(pypi, github, defects, scorecard)
    return CandidateProbeReport(
        package_name=package_name,
        pypi=pypi,
        github=github,
        defects=defects,
        scorecard=scorecard,
        pip_resolution=pip_resolution,
        import_surface=import_surface,
        test_suite=test_suite,
        triage_score=score,
        disqualifying_reasons=disqualifying,
    )


def render_comparison_table(reports: list[CandidateProbeReport]) -> str:
    header = (
        f"{'CANDIDATE':<22}{'SCORE':>6}  {'VERSION':<12}{'PLATFORM':<15}"
        f"{'PUSHED':>8}{'STARS':>8}{'REL/YR':>7}{'DEFECT?':>9}{'OSSF':>6}  LICENSE"
    )
    lines = [header, "-" * len(header)]
    for report in sorted(reports, key=lambda item: item.triage_score, reverse=True):
        pushed = (
            f"{report.github.days_since_last_push}d"
            if report.github.days_since_last_push is not None
            else "?"
        )
        stars = str(report.github.star_count) if report.github.star_count is not None else "?"
        defect_count = (
            str(report.defects.matching_issue_count)
            if report.defects.matching_issue_count is not None
            else "?"
        )
        license_text = report.github.spdx_license or report.pypi.declared_license or "?"
        ossf_text = (
            f"{report.scorecard.overall_score:.1f}" if report.scorecard.overall_score is not None else "?"
        )
        lines.append(
            f"{report.package_name:<22}{report.triage_score:>6.2f}  "
            f"{(report.pypi.latest_version or '?'):<12}"
            f"{report.pypi.installability.classification:<15}"
            f"{pushed:>8}{stars:>8}{report.pypi.releases_in_last_12_months:>7}{defect_count:>9}"
            f"{ossf_text:>6}  {license_text}"
        )
    return "\n".join(lines)


def render_candidate_detail(report: CandidateProbeReport) -> str:
    lines = [f"\n### {report.package_name}  (triage score {report.triage_score})"]
    if report.pypi.summary:
        lines.append(f"    summary      : {report.pypi.summary[:150]}")
    if report.github.owner_and_name:
        lines.append(f"    repo         : github.com/{report.github.owner_and_name}")
    lines.append(
        f"    python       : requires {report.pypi.requires_python or '?'} · "
        f"latest release {report.pypi.latest_release_age_days if report.pypi.latest_release_age_days is not None else '?'}d old"
    )
    lines.append(
        f"    platform     : {report.pypi.installability.classification} "
        f"({len(report.pypi.installability.distribution_filenames)} dist files for latest release)"
    )
    if report.scorecard.overall_score is not None:
        notable = [
            f"{name} {score}/10"
            for name, score in report.scorecard.check_scores
            if name in ("Maintained", "Code-Review", "Vulnerabilities", "Dangerous-Workflow")
        ]
        lines.append(
            f"    OpenSSF      : {report.scorecard.overall_score:.1f}/10  ({' · '.join(notable)})"
        )
    if report.pip_resolution.resolved_distribution:
        lines.append(f"    pip resolves : {report.pip_resolution.resolved_distribution}")
    if report.pip_resolution.probe_error:
        lines.append(f"    pip ERROR    : {report.pip_resolution.probe_error}")
    if report.import_surface.inspected_signatures:
        lines.append("    api surface  :")
        for attribute_name, signature_text in report.import_surface.inspected_signatures:
            lines.append(f"        · {signature_text}")
    elif report.import_surface.probe_error and report.import_surface.probe_error != "not requested":
        lines.append(f"    surface ERROR: {report.import_surface.probe_error}")
    if report.test_suite.matching_test_files:
        lines.append(
            f"    tests        : {len(report.test_suite.matching_test_files)} of "
            f"{report.test_suite.total_test_files} test files mention "
            f"'{report.test_suite.capability_keyword}'"
        )
        for path in report.test_suite.matching_test_files[:5]:
            lines.append(f"        · {path}")
    elif report.test_suite.probe_error and report.test_suite.probe_error != "not requested":
        lines.append(f"    tests        : {report.test_suite.probe_error}")
    elif report.test_suite.capability_keyword and report.test_suite.total_test_files:
        lines.append(
            f"    tests        : ⚠ NO test file mentions '{report.test_suite.capability_keyword}' "
            f"(scanned {report.test_suite.total_test_files}) — untested capability"
        )
    for error_text in (report.pypi.probe_error, report.github.probe_error, report.defects.probe_error):
        if error_text and error_text != "not requested":
            lines.append(f"    ⚠ probe error: {error_text}")
    for reason in report.disqualifying_reasons:
        lines.append(f"    ⛔ DISQUALIFYING: {reason}")
    return "\n".join(lines)


def parse_repository_overrides(raw_values: list[str]) -> dict[str, str]:
    """`--repo pkg=owner/name` for packages whose PyPI metadata omits the repository link."""
    overrides: dict[str, str] = {}
    for raw in raw_values:
        if "=" not in raw:
            raise SystemExit(f"--repo expects package=owner/name, got: {raw}")
        package_name, owner_and_name = raw.split("=", 1)
        overrides[package_name.strip()] = owner_and_name.strip()
    return overrides


def parse_surface_request(raw_value: str) -> tuple[str, tuple[str, ...]] | None:
    """`--surface module:Attr1,Attr2` — introspect exactly the callables the feature needs."""
    if not raw_value:
        return None
    if ":" not in raw_value:
        return (raw_value.strip(), ())
    module_name, attribute_text = raw_value.split(":", 1)
    attributes = tuple(name.strip() for name in attribute_text.split(",") if name.strip())
    return (module_name.strip(), attributes)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Mechanical OSS-candidate triage — facts over README prose (research/171).",
    )
    parser.add_argument("packages", nargs="+", help="PyPI package names to probe")
    parser.add_argument("--repo", action="append", default=[], metavar="PKG=OWNER/NAME",
                        help="override the GitHub repo when PyPI metadata omits it")
    parser.add_argument("--needs", default="", metavar="KEYWORD",
                        help="capability keyword to grep the candidates' TEST suites for")
    parser.add_argument("--surface", default="", metavar="MODULE:ATTR,ATTR",
                        help="import a module and print signatures of the named callables")
    parser.add_argument("--no-clone", action="store_true",
                        help="skip the shallow clone used by --needs (faster, less evidence)")
    parser.add_argument("--json", default="", metavar="PATH", help="also write the full report as JSON")
    arguments = parser.parse_args(argv)

    repository_overrides = parse_repository_overrides(arguments.repo)
    surface_request = parse_surface_request(arguments.surface)
    include_test_clone = bool(arguments.needs) and not arguments.no_clone

    print(f"Probing {len(arguments.packages)} candidate(s) on {sys.platform}/{os.uname().machine} "
          f"with {PROBE_PYTHON}")
    if not os.environ.get("GITHUB_TOKEN"):
        print("  note: GITHUB_TOKEN unset — GitHub limits apply (60/hr core, 10/min search); "
              "rate-limit hits are reported, not hidden.")

    started_at = time.monotonic()
    reports: list[CandidateProbeReport] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(
                probe_single_candidate,
                package_name,
                repository_overrides.get(package_name, ""),
                arguments.needs,
                surface_request,
                include_test_clone,
            ): package_name
            for package_name in arguments.packages
        }
        for future in concurrent.futures.as_completed(futures):
            package_name = futures[future]
            try:
                reports.append(future.result())
            except Exception as error:  # noqa: BLE001 — a probe crash is reported, never swallowed
                print(f"  ⚠ probe crashed for {package_name}: {type(error).__name__}: {error}")

    print(f"\n{render_comparison_table(reports)}")
    for report in sorted(reports, key=lambda item: item.triage_score, reverse=True):
        print(render_candidate_detail(report))

    print(
        "\nTRIAGE ONLY — this ranks what to examine first. Under the Rule O.1 evidence tiers a candidate "
        "may be dropped on these facts alone ONLY for an objective disqualifier (won't install, archived, "
        "yanked, wrong I/O shape). Any rejection on correctness/depth/quality grounds still requires "
        "reading the implementing source, running it, or citing a specific issue."
    )
    print(f"Probed {len(reports)} candidate(s) in {time.monotonic() - started_at:.1f}s.")

    if arguments.json:
        payload = [
            {
                "package_name": report.package_name,
                "triage_score": report.triage_score,
                "disqualifying_reasons": list(report.disqualifying_reasons),
                "pypi": report.pypi.__dict__ | {"installability": report.pypi.installability.__dict__},
                "github": report.github.__dict__,
                "defects": report.defects.__dict__,
                "openssf_scorecard": report.scorecard.__dict__,
                "pip_resolution": report.pip_resolution.__dict__,
                "import_surface": report.import_surface.__dict__,
                "test_suite": report.test_suite.__dict__,
            }
            for report in sorted(reports, key=lambda item: item.triage_score, reverse=True)
        ]
        Path(arguments.json).write_text(json.dumps(payload, indent=2, default=str))
        print(f"Wrote JSON report → {arguments.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
