"""Real AST import-graph resolver for the Feature Catalogue (Rule R hardening).

Replaces the note-text heuristic with the same ground truth the SYSTEM_MAP extractor uses: the actual
``ast`` import graph of ``src/nse_algo_trader``. It answers three questions the heuristic could not:

* **Does the code exist?** — resolve a catalogue row to a real module by explicit path, then module-stem
  token, then feature-name tokens.
* **Is it wired, or an orphan?** — BFS reachability from the real runnable entry points (Rule G). A module
  the entry points can never reach is an ``orphan``, and that is a measured status, not a guess.
* **What code is undocumented?** — any real module referenced by NO catalogue row, so new code auto-appears
  on the board and the catalogue can never silently fall behind the server (freshness).
"""

from __future__ import annotations

import ast
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_PACKAGE_NAME = "nse_algo_trader"

# The real runnable roots — where execution actually begins. Reachability is measured from here (Rule G).
_ENTRY_POINT_STEMS = frozenset(
    {
        "dashboard_server",
        "live_universe_paper_loop",
        "live_paper_trading_service",
        "config_enforced_paper_run",
        "daily_nse_reports_ingestion_job",
        "fo_bhavcopy_backfill_job",
        "delisted_securities_ingestion_job",
        "refresh_kite_access_token",
        "kite_totp_auto_login",
        "autopoiesis_orchestrator",
        "feature_catalogue_status_prober",
    }
)

# modules that are never "features" for undocumented-discovery purposes
_NON_FEATURE_STEMS = frozenset({"__init__", "__main__"})

_TOKEN = re.compile(r"[a-z][a-z0-9]+")


@dataclass(frozen=True)
class ModuleResolution:
    """The measured code facts for one catalogue row."""

    module_relpath: str | None  # e.g. "market_data/vpin_order_flow_toxicity.py"
    code_present: bool
    is_wired: bool  # reachable from a runnable entry point (Rule G)


@dataclass(frozen=True)
class ImportGraph:
    """The real AST import graph of the package plus its reachable set."""

    stems_to_relpath: dict[str, str]
    relpath_to_stem: dict[str, str]
    edges: dict[str, set[str]]  # stem -> set of imported internal stems
    reachable_stems: frozenset[str]
    stems_longest_first: tuple[str, ...]  # for greedy substring resolution (most specific stem wins)


def _package_root(package_root: Path | None = None) -> Path:
    if package_root is not None:
        return package_root
    # …/src/nse_algo_trader/dashboard/this_file  ->  …/src/nse_algo_trader
    return Path(__file__).resolve().parent.parent


def _internal_imported_stems(tree: ast.AST) -> set[str]:
    """Return the set of internal (``nse_algo_trader.*``) module stems imported by a parsed module."""

    stems: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module.startswith(_PACKAGE_NAME):
                # the final component is the module (or the package, whose __init__ re-exports)
                stems.add(module.rsplit(".", 1)[-1])
            for alias in node.names:  # from pkg import submodule
                stems.add(alias.name.rsplit(".", 1)[-1])
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith(_PACKAGE_NAME):
                    stems.add(alias.name.rsplit(".", 1)[-1])
    return stems


@lru_cache(maxsize=8)
def build_import_graph(package_root_str: str | None = None) -> ImportGraph:
    """Parse every module's AST once and build the import graph + entry-reachable set."""

    root = _package_root(Path(package_root_str) if package_root_str else None)
    stems_to_relpath: dict[str, str] = {}
    relpath_to_stem: dict[str, str] = {}
    edges: dict[str, set[str]] = {}

    for dirpath, _dirnames, filenames in os.walk(root):
        for filename in filenames:
            if not filename.endswith(".py"):
                continue
            stem = filename[:-3]
            relpath = os.path.relpath(os.path.join(dirpath, filename), root).replace(os.sep, "/")
            stems_to_relpath.setdefault(stem, relpath)
            relpath_to_stem[relpath] = stem
            try:
                tree = ast.parse(Path(dirpath, filename).read_text(encoding="utf-8"))
            except (SyntaxError, OSError):
                edges[stem] = set()
                continue
            edges[stem] = _internal_imported_stems(tree)

    # BFS reachability from entry points over the import edges
    known = set(stems_to_relpath)
    frontier = [s for s in _ENTRY_POINT_STEMS if s in known]
    reachable: set[str] = set(frontier)
    while frontier:
        current = frontier.pop()
        for imported in edges.get(current, ()):  # follow imports
            if imported in known and imported not in reachable:
                reachable.add(imported)
                frontier.append(imported)

    return ImportGraph(
        stems_to_relpath=stems_to_relpath,
        relpath_to_stem=relpath_to_stem,
        edges=edges,
        reachable_stems=frozenset(reachable),
        stems_longest_first=tuple(sorted(stems_to_relpath, key=len, reverse=True)),
    )


_EXPLICIT_PATH = re.compile(r"([a-z_][a-z_0-9]*/[a-z_][a-z_0-9]*)(?:\.py)?")


def resolve_row(
    feature: str, note: str, sources: tuple[str, ...], graph: ImportGraph
) -> ModuleResolution:
    """Resolve a catalogue row to a real module by explicit path → stem token → feature-name tokens."""

    text = " ".join([note, *sources])
    stem: str | None = None

    # (a) explicit pkg/module path present in the text
    for match in _EXPLICIT_PATH.finditer(text):
        candidate = match.group(1) + ".py"
        if candidate in graph.relpath_to_stem:
            stem = graph.relpath_to_stem[candidate]
            break
        tail = match.group(1).rsplit("/", 1)[-1]
        if tail in graph.stems_to_relpath:
            stem = tail
            break

    # (b) a real multi-word module stem appears verbatim as a substring (e.g. "global_workspace" cited in
    #     prose without a slash path). Longest stem first so the most specific module wins.
    if stem is None:
        lowered = text.lower()
        for candidate_stem in graph.stems_longest_first:
            if candidate_stem in _NON_FEATURE_STEMS:
                continue
            if "_" in candidate_stem and len(candidate_stem) >= 8 and candidate_stem in lowered:
                stem = candidate_stem
                break

    # (c) a bare single-word module-stem token appears verbatim in the text
    if stem is None:
        for token in _TOKEN.findall(text.lower()):
            if token in graph.stems_to_relpath and token not in _NON_FEATURE_STEMS:
                stem = token
                break

    # (c) feature-name tokens vote for the best-overlapping module stem
    if stem is None:
        feature_tokens = {t for t in _TOKEN.findall(feature.lower()) if len(t) > 3}
        if feature_tokens:
            best_stem, best_overlap = None, 0
            for candidate_stem in graph.stems_to_relpath:
                if candidate_stem in _NON_FEATURE_STEMS:
                    continue
                overlap = len(feature_tokens & set(candidate_stem.split("_")))
                if overlap > best_overlap:
                    best_stem, best_overlap = candidate_stem, overlap
            if best_overlap >= 2:  # need a real match, not a single common word
                stem = best_stem

    if stem is None:
        return ModuleResolution(module_relpath=None, code_present=False, is_wired=False)
    return ModuleResolution(
        module_relpath=graph.stems_to_relpath[stem],
        code_present=True,
        is_wired=stem in graph.reachable_stems,
    )


def undocumented_module_relpaths(
    referenced_stems: set[str], graph: ImportGraph
) -> list[str]:
    """Real feature modules referenced by NO catalogue row — the freshness signal (auto-discovery)."""

    out: list[str] = []
    for stem, relpath in sorted(graph.stems_to_relpath.items()):
        if stem in _NON_FEATURE_STEMS or stem in referenced_stems:
            continue
        if "/tests/" in relpath or relpath.startswith("tests/"):
            continue
        out.append(relpath)
    return out


if __name__ == "__main__":  # pragma: no cover
    g = build_import_graph()
    print("modules:", len(g.stems_to_relpath))
    print("reachable (wired):", len(g.reachable_stems))
    print("orphans:", len(set(g.stems_to_relpath) - set(g.reachable_stems) - _NON_FEATURE_STEMS))
