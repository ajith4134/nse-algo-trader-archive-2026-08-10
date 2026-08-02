"""Rule H.1 — verify the §1 System-Map DIAGRAM is TRUE to the code.

Reconciles the rendered Mermaid diagram in docs/SYSTEM_MAP.md against the §0 extractor ground truth:
every feature package under src/nse_algo_trader/ must appear (by name) as a node in the §1 diagram,
and the header's feature/module counts must match. Exits non-zero (and prints what's missing) when
the diagram has drifted — so a hook can BLOCK a sign-off until the rendered chart is true again.

Run:  python scripts/check_system_map_diagram_fidelity.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "nse_algo_trader"
SYSTEM_MAP = ROOT / "docs" / "SYSTEM_MAP.md"


def feature_packages() -> dict[str, int]:
    """Feature packages (a package = a dir with a module) → module count, from the real tree."""
    counts: dict[str, int] = {}
    for module in SRC.rglob("*.py"):
        rel = module.relative_to(SRC).parts
        if len(rel) > 1:  # inside a package, not a top-level module
            counts[rel[0]] = counts.get(rel[0], 0) + 1
    return counts


def first_mermaid_block(markdown: str) -> str:
    match = re.search(r"```mermaid\n(.*?)\n```", markdown, re.S)
    return match.group(1) if match else ""


def main() -> int:
    packages = feature_packages()
    markdown = SYSTEM_MAP.read_text()
    diagram = first_mermaid_block(markdown)

    problems: list[str] = []

    # 1. Node completeness — every feature package is named in a §1 diagram node.
    missing = sorted(pkg for pkg in packages if pkg not in diagram)
    if missing:
        problems.append(
            "MISSING feature node(s) in the §1 diagram (Rule H.1 node-completeness): "
            + ", ".join(missing)
        )

    # 2. Counts — the header "N modules across M feature packages" matches the extractor.
    total_modules = sum(packages.values())
    feature_count = len(packages)
    header = markdown[:2000]
    if str(feature_count) not in re.findall(r"(\d+)\s+feature packages", header + markdown[:4000]):
        problems.append(
            f"HEADER feature-package count is not {feature_count} "
            f"(the extractor sees {feature_count} packages)."
        )
    if str(total_modules) not in re.findall(r"(\d+)\s+Python modules", markdown[:4000]):
        problems.append(
            f"HEADER module count is not {total_modules} "
            f"(the extractor sees {total_modules} modules)."
        )

    if problems:
        print("SYSTEM-MAP DIAGRAM FIDELITY: FAIL (Rule H.1) —")
        for p in problems:
            print("  ✗", p)
        print(f"\n  extractor: {feature_count} feature packages, {total_modules} modules.")
        return 1

    print(f"SYSTEM-MAP DIAGRAM FIDELITY: OK — all {feature_count} feature packages "
          f"({total_modules} modules) are represented in the §1 diagram.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
