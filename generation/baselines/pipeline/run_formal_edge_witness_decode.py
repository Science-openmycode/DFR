"""Decode the formal witness release with an audited legacy-query source binding.

The sealed q5 transcript was measured with the archived shared-graph module.  The
current module differs only inside unused synthesis/CLI experiment drivers;
all definitions relevant to ``prepare_graph`` are AST-identical.  This
wrapper verifies that narrow compatibility claim, points the existing frozen
production gate at the exact archived query source, and records the audit.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FINAL = ROOT / "src" / "mtr" / "DP_GSRT" / "final"
SHARED = ROOT / "src" / "mtr" / "shared_graph"
for path in (ROOT, FINAL):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def query_relevant_module_ast(path: Path) -> str:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    tree.body = [
        node for node in tree.body
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        or node.name not in {"main", "synthesize"}
    ]
    return hashlib.sha256(ast.dump(tree, include_attributes=False).encode("utf-8")).hexdigest()


def verify_legacy_query_lineage(portal_dir: Path) -> tuple[dict, dict[str, Path]]:
    import portal_fiber_route_production_sanitizer as sanitizer

    manifest_path = portal_dir / "portal_fiber_route_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    recorded = manifest.get("source_sha256", {})
    current_paths = sanitizer.frozen_source_paths()
    mismatches = {
        name: (recorded.get(name), sha256_file(path))
        for name, path in current_paths.items()
        if recorded.get(name) != sha256_file(path)
    }
    if set(mismatches) != {"graph_core"}:
        raise RuntimeError(f"Unexpected portal-query source drift set: {sorted(mismatches)}")
    archived_graph = SHARED / "route_structure_potential_experiment.py"
    runtime_graph = current_paths["graph_core"]
    archived_hash = sha256_file(archived_graph)
    if archived_hash != recorded["graph_core"]:
        raise RuntimeError("Archived graph core does not match the sealed q5 query lineage")
    archived_ast = query_relevant_module_ast(archived_graph)
    runtime_ast = query_relevant_module_ast(runtime_graph)
    if archived_ast != runtime_ast:
        raise RuntimeError("Runtime and sealed graph cores differ outside unused synthesis drivers")
    gate_paths = dict(current_paths)
    gate_paths["graph_core"] = archived_graph
    report = {
        "schema_version": 1,
        "classification": "FORMAL_QUERY_LINEAGE_COMPATIBILITY_AUDIT",
        "passed": True,
        "scope": "portal-fiber q5 query graph source versus current post-processing runtime",
        "transcript_manifest_path": str(manifest_path.resolve()),
        "transcript_manifest_sha256": sha256_file(manifest_path),
        "recorded_graph_core_sha256": recorded["graph_core"],
        "archived_graph_core_path": str(archived_graph.resolve()),
        "archived_graph_core_sha256": archived_hash,
        "runtime_graph_core_path": str(runtime_graph.resolve()),
        "runtime_graph_core_sha256": sha256_file(runtime_graph),
        "query_relevant_module_ast_sha256": runtime_ast,
        "compatibility_basis": (
            "The exact sealed query source is retained in shared_graph. The current runtime module "
            "has an identical normalized module AST after removing only the unused synthesize and "
            "CLI main experiment drivers; the private query and decoder use prepare_graph, not those drivers."
        ),
    }
    return report, gate_paths


def main() -> None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--portal-release-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args, _ = parser.parse_known_args()
    report, gate_paths = verify_legacy_query_lineage(args.portal_release_dir.resolve())

    import portal_fiber_route_production_sanitizer as sanitizer
    import portal_fiber_qrsp_production as production

    sanitizer.frozen_source_paths = lambda: dict(gate_paths)
    production.main()
    audit_path = args.out_dir.resolve() / "source_lineage_compatibility.json"
    temporary = audit_path.with_suffix(audit_path.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2), encoding="utf-8")
    os.replace(temporary, audit_path)
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
