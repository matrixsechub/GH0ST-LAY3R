"""
Ghost Layer Studio — Import DAG Guard

# ADVANCEMENT: Pass 2 diagnostics
Static, stdlib-only check (ast + pathlib) that prevents reintroduction of the
historical circular imports around core.engine. It parses the intra-repo import
edges of core/*.py, agents/*.py, and scripts/*.py and enforces:

  * core.physics / core.oversoul / core.output / agents.constellation
    must NOT import core.engine.
  * core.types (the leaf module) must NOT import any higher-level runtime module.

Run:  python3 -m scripts.check_import_dag
Exits 0 on PASS, nonzero on FAIL.
"""

from __future__ import annotations
import ast
import pathlib
import sys
from typing import Dict, List, Set

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SCAN_DIRS = ("core", "agents", "scripts")
INTRA_PREFIXES = ("core.", "agents.")

# core.engine must never be imported by these modules.
ENGINE_IMPORT_FORBIDDEN_FROM = {
    "core.physics",
    "core.oversoul",
    "core.output",
    "agents.constellation",
}

# core.types is the leaf: it must import none of these higher-level modules.
TYPES_FORBIDDEN_IMPORTS = {
    "core.engine",
    "core.physics",
    "core.oversoul",
    "core.output",
    "agents.constellation",
}


def _module_name(path: pathlib.Path) -> str:
    rel = path.relative_to(REPO_ROOT).with_suffix("")
    return ".".join(rel.parts)


def _intra_repo_imports(path: pathlib.Path) -> Set[str]:
    """Return the set of intra-repo modules imported by ``path`` (any context)."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith(INTRA_PREFIXES):
                    found.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            # Only absolute intra-repo imports (level 0) are relevant here.
            if node.level == 0 and node.module and node.module.startswith(INTRA_PREFIXES):
                found.add(node.module)
    return found


def build_dependency_map() -> Dict[str, Set[str]]:
    dep_map: Dict[str, Set[str]] = {}
    for directory in SCAN_DIRS:
        for path in sorted((REPO_ROOT / directory).glob("*.py")):
            dep_map[_module_name(path)] = _intra_repo_imports(path)
    return dep_map


def check(dep_map: Dict[str, Set[str]]) -> List[str]:
    """Return a list of violation strings (empty means PASS)."""
    violations: List[str] = []

    for module in ENGINE_IMPORT_FORBIDDEN_FROM:
        imports = dep_map.get(module)
        if imports is None:
            continue  # module not present; nothing to check
        if "core.engine" in imports:
            violations.append(
                f"{module} imports core.engine (would reintroduce a cycle)"
            )

    type_imports = dep_map.get("core.types", set())
    for forbidden in sorted(TYPES_FORBIDDEN_IMPORTS):
        if forbidden in type_imports:
            violations.append(
                f"core.types imports {forbidden} (leaf module must stay dependency-free)"
            )

    return violations


def main() -> int:
    dep_map = build_dependency_map()

    print("Ghost Layer Studio — Import DAG Guard")
    print("=" * 52)
    for module in sorted(dep_map):
        deps = ", ".join(sorted(dep_map[module])) or "(no intra-repo imports)"
        print(f"  {module} -> {deps}")
    print("-" * 52)

    violations = check(dep_map)
    if violations:
        for v in violations:
            print(f"FAIL: {v}")
        print("=" * 52)
        print("RESULT: FAIL")
        return 1

    print("RESULT: PASS — no forbidden edges around core.engine / core.types")
    return 0


if __name__ == "__main__":
    sys.exit(main())
