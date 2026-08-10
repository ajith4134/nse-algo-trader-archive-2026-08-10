"""Rule-R generator for the project-wide Feature Catalogue.

The *plan* (what was ever built / partial / planned / discussed / idea / forgotten / blocked) is authored in
``feature_catalogue_authored.json`` — that is intent, and it is allowed to be hand-written. The *build
status*, however, must be MEASURED from the real server state, never trusted from the authored label
(Rule R). This module is that measurement: it drives the real ``ast`` import graph
(``feature_catalogue_ast_resolver``) to decide, per row, whether the code exists and whether it is wired
into a runnable entry point (Rule G) — plus a generation timestamp, so a stale board is visibly stale.

Nothing here defaults an unmeasurable row to "done": a row that claims ``built`` but whose module cannot be
resolved on disk is reported as ``unverified`` and surfaced; a resolved-but-unreachable module is
reported ``built`` but flagged ``orphan``; and any real module referenced by NO row is auto-discovered so
the catalogue can never silently fall behind the code.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from nse_algo_trader.dashboard.feature_catalogue_ast_resolver import (
    build_import_graph,
    resolve_row,
    undocumented_module_relpaths,
)

_THIS_DIR = Path(__file__).resolve().parent
_PACKAGE_ROOT = _THIS_DIR.parent  # …/src/nse_algo_trader
_AUTHORED_CATALOGUE_PATH = _THIS_DIR / "feature_catalogue_authored.json"

_IST = timezone(timedelta(hours=5, minutes=30))

# status vocabulary, strongest → weakest (server-truth ordering for reconciliation)
_MEASURED_ORDER = [
    "built",
    "partial",
    "unverified",
    "blocked",
    "planned",
    "researched",
    "discussed",
    "not-built",
    "idea",
]

# how a status is displayed (label + palette role — never colour alone, Rule R / dataviz)
STATUS_DISPLAY = {
    "built": ("BUILT", "good"),
    "partial": ("PARTIAL", "warning"),
    "unverified": ("UNVERIFIED", "serious"),
    "blocked": ("BLOCKED", "serious"),
    "not-built": ("NOT BUILT", "neutral"),
    "planned": ("PLANNED", "info"),
    "researched": ("RESEARCHED", "info"),
    "discussed": ("DISCUSSED", "info"),
    "idea": ("IDEA", "muted"),
}


@dataclass(frozen=True)
class MeasuredFeatureRow:
    """One catalogue row after its status has been measured against the real code + import graph."""

    section: str
    feature: str
    authored_status: str
    measured_status: str
    phase: str
    forgotten: bool
    note: str
    sources: tuple[str, ...]
    origins: tuple[str, ...]
    is_atlas_branch: bool
    code_present: bool
    code_reference: str | None
    is_wired: bool
    is_orphan: bool


@dataclass(frozen=True)
class FeatureCatalogueMeasurement:
    """The whole measured catalogue plus summary counts and provenance."""

    rows: tuple[MeasuredFeatureRow, ...]
    generated_at_ist: str
    real_module_count: int
    status_counts: dict[str, int]
    phase_counts: dict[str, int]
    section_counts: dict[str, int]
    forgotten_count: int
    feature_row_count: int
    atlas_branch_count: int
    atlas_built_count: int
    built_with_code_count: int
    unverified_claim_count: int
    orphan_count: int
    undocumented_count: int
    wired_module_count: int


def _reconcile_status(authored_status: str, code_present: bool) -> str:
    """Rule R: the authored label is a claim; the measured presence of code decides the reported status."""

    if authored_status in ("built", "partial"):
        return authored_status if code_present else "unverified"
    # an item that was only "planned/idea/…" but for which code actually exists is really partial
    return "partial" if code_present else authored_status


def _normalise_phase(phase: str | None) -> str:
    if phase in (None, "", "-", "—") or (phase and phase.startswith("<")):
        return "—"
    return phase


def _undocumented_rows(
    referenced_stems: set[str], graph, package_root: Path
) -> list[MeasuredFeatureRow]:
    """Auto-discovered rows for real feature modules referenced by NO authored row (freshness)."""

    rows: list[MeasuredFeatureRow] = []
    for relpath in undocumented_module_relpaths(referenced_stems, graph):
        stem = graph.relpath_to_stem[relpath]
        wired = stem in graph.reachable_stems
        rows.append(
            MeasuredFeatureRow(
                section="Undocumented modules (auto-discovered)",
                feature=stem.replace("_", " "),
                authored_status="",
                measured_status="built" if wired else "partial",
                phase="—",
                forgotten=True,  # undocumented code is exactly the "forgotten" surface this board exists for
                note=f"real module not referenced by any authored catalogue row — {'wired' if wired else 'ORPHAN (not reached from any entry point)'}",
                sources=(relpath,),
                origins=("auto-discovered",),
                is_atlas_branch=False,
                code_present=True,
                code_reference=relpath,
                is_wired=wired,
                is_orphan=not wired,
            )
        )
    return rows


def measure_feature_catalogue(
    authored_catalogue_path: Path | None = None,
    package_root: Path | None = None,
    now_ist: datetime | None = None,
) -> FeatureCatalogueMeasurement:
    """Load the authored plan and measure every row against the live code + import graph (Rule R)."""

    authored_catalogue_path = authored_catalogue_path or _AUTHORED_CATALOGUE_PATH
    package_root = package_root or _PACKAGE_ROOT
    generated_at = (now_ist or datetime.now(_IST)).strftime("%Y-%m-%d %H:%M:%S IST")

    authored_rows = json.loads(Path(authored_catalogue_path).read_text(encoding="utf-8"))
    graph = build_import_graph(str(package_root))

    measured_rows: list[MeasuredFeatureRow] = []
    referenced_stems: set[str] = set()
    for row in authored_rows:
        section = str(row.get("section", "")).strip()
        if section.startswith("<"):  # schema-placeholder junk row, never render it
            continue
        sources = tuple(s for s in row.get("sources", []) if s)
        feature = str(row.get("feature", "")).strip()
        note = str(row.get("note", ""))
        resolution = resolve_row(feature, note, sources, graph)
        if resolution.module_relpath is not None:
            referenced_stems.add(graph.relpath_to_stem[resolution.module_relpath])
        authored_status = str(row.get("status", "idea"))
        measured_status = _reconcile_status(authored_status, resolution.code_present)
        is_atlas = bool(row.get("atlas"))
        is_orphan = resolution.code_present and not resolution.is_wired and not is_atlas
        measured_rows.append(
            MeasuredFeatureRow(
                section=section,
                feature=feature,
                authored_status=authored_status,
                measured_status=measured_status,
                phase=_normalise_phase(row.get("phase")),
                forgotten=bool(row.get("forgotten")),
                note=note,
                sources=sources,
                origins=tuple(row.get("origins", [])),
                is_atlas_branch=is_atlas,
                code_present=resolution.code_present,
                code_reference=resolution.module_relpath,
                is_wired=resolution.is_wired,
                is_orphan=is_orphan,
            )
        )

    undocumented = _undocumented_rows(referenced_stems, graph, package_root)
    measured_rows.extend(undocumented)

    def _count(predicate) -> int:
        return sum(1 for r in measured_rows if predicate(r))

    status_counts: dict[str, int] = {}
    phase_counts: dict[str, int] = {}
    section_counts: dict[str, int] = {}
    for measured in measured_rows:
        status_counts[measured.measured_status] = status_counts.get(measured.measured_status, 0) + 1
        phase_counts[measured.phase] = phase_counts.get(measured.phase, 0) + 1
        section_counts[measured.section] = section_counts.get(measured.section, 0) + 1
    status_counts = {k: status_counts[k] for k in _MEASURED_ORDER if k in status_counts}

    return FeatureCatalogueMeasurement(
        rows=tuple(measured_rows),
        generated_at_ist=generated_at,
        real_module_count=len(graph.stems_to_relpath),
        status_counts=status_counts,
        phase_counts=phase_counts,
        section_counts=section_counts,
        forgotten_count=_count(lambda r: r.forgotten and not r.is_atlas_branch),
        feature_row_count=_count(lambda r: not r.is_atlas_branch),
        atlas_branch_count=_count(lambda r: r.is_atlas_branch),
        atlas_built_count=_count(lambda r: r.is_atlas_branch and r.measured_status == "built"),
        built_with_code_count=_count(lambda r: r.measured_status == "built" and r.code_present),
        unverified_claim_count=_count(lambda r: r.measured_status == "unverified"),
        orphan_count=_count(lambda r: r.is_orphan),
        undocumented_count=len(undocumented),
        wired_module_count=len(graph.reachable_stems),
    )


if __name__ == "__main__":  # pragma: no cover — quick real-data smoke check (Rule F)
    result = measure_feature_catalogue()
    print(f"generated_at:        {result.generated_at_ist}")
    print(f"real modules on disk:{result.real_module_count} ({result.wired_module_count} wired)")
    print(f"feature rows:        {result.feature_row_count}")
    print(f"atlas branches:      {result.atlas_branch_count} ({result.atlas_built_count} built)")
    print(f"forgotten-flagged:   {result.forgotten_count}")
    print(f"built (code-backed): {result.built_with_code_count}")
    print(f"unverified claims:   {result.unverified_claim_count}")
    print(f"orphans:             {result.orphan_count}")
    print(f"undocumented modules:{result.undocumented_count}")
    print(f"status counts:       {result.status_counts}")
