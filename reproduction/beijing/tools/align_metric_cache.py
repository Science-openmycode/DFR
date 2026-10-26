"""Align legacy region labels to the current public edge-node namespace.

The public network and an older metric cache may use different node IDs while
sharing stable edge IDs.  This utility joins them through edge IDs, verifies
that the endpoint mapping is one-to-one, and derives current outdegrees from
the current edge cache.  It never copies a legacy node ID into a current route
object without an explicit edge-based mapping.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import pickle
from pathlib import Path


def load(path: Path) -> dict:
    with gzip.open(path, "rb") as handle:
        value = pickle.load(handle)
    if not isinstance(value, dict) or "edge_nodes" not in value:
        raise ValueError(f"invalid edge cache: {path}")
    return value


def _nodes(value: dict) -> dict[int, tuple[int, int]]:
    return {int(k): (int(v[0]), int(v[1])) for k, v in value.items()}


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def align(prepared_path: Path, legacy_path: Path, output_path: Path) -> dict:
    prepared = load(prepared_path)
    legacy = load(legacy_path)
    current_edges = _nodes(prepared["edge_nodes"])
    legacy_edges = _nodes(legacy["edge_nodes"])
    common = sorted(set(current_edges) & set(legacy_edges))
    if not common:
        raise ValueError("no common edge IDs between caches")
    if set(current_edges) != set(legacy_edges):
        missing_current = sorted(set(legacy_edges) - set(current_edges))[:10]
        missing_legacy = sorted(set(current_edges) - set(legacy_edges))[:10]
        raise ValueError(
            "edge ID sets differ; refusing partial namespace alignment: "
            f"missing_current={missing_current}, missing_legacy={missing_legacy}"
        )

    new_to_old: dict[int, int] = {}
    old_to_new: dict[int, int] = {}
    conflicts = 0
    for edge_id in common:
        for new_node, old_node in zip(current_edges[edge_id], legacy_edges[edge_id]):
            prior_old = new_to_old.get(new_node)
            prior_new = old_to_new.get(old_node)
            if (prior_old is not None and prior_old != old_node) or (
                prior_new is not None and prior_new != new_node
            ):
                conflicts += 1
            else:
                new_to_old[new_node] = old_node
                old_to_new[old_node] = new_node
    if conflicts:
        raise ValueError(f"inconsistent node mapping across common edges: {conflicts}")
        
    aligned = dict(prepared)
    aligned["edge_nodes"] = current_edges
    for resolution in (24, 96, 384):
        source = {int(k): int(v) for k, v in legacy.get(f"labels{resolution}", {}).items()}
        aligned[f"labels{resolution}"] = {
            new: source[old] for new, old in new_to_old.items() if old in source
        }
    outdegree: dict[int, int] = {}
    for source, target in current_edges.values():
        outdegree[source] = outdegree.get(source, 0) + 1
        outdegree.setdefault(target, 0)
    aligned["outdegree"] = outdegree
    portals = legacy.get("portals", [])
    aligned["portals"] = [old_to_new[int(node)] for node in portals if int(node) in old_to_new]
    aligned["classification"] = "EDGE_ID_ALIGNED_METRIC_CACHE_V1"
    aligned["alignment"] = {
        "prepared_cache_sha256": _hash(prepared_path),
        "legacy_metric_cache_sha256": _hash(legacy_path),
        "common_edge_count": len(common),
        "mapped_node_count": len(new_to_old),
        "node_conflicts": conflicts,
        "mapping_basis": "common_edge_id_endpoint_pairs",
        "outdegree_source": "current_prepared_edge_nodes",
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(output_path, "wb") as handle:
        pickle.dump(aligned, handle, protocol=pickle.HIGHEST_PROTOCOL)
    return {
        "schema_version": 1,
        "classification": "EDGE_ID_ALIGNED_METRIC_CACHE_V1",
        "prepared_cache": str(prepared_path.resolve()),
        "prepared_cache_sha256": _hash(prepared_path),
        "legacy_metric_cache": str(legacy_path.resolve()),
        "legacy_metric_cache_sha256": _hash(legacy_path),
        "output": str(output_path.resolve()),
        "output_sha256": _hash(output_path),
        "common_edge_count": len(common),
        "mapped_node_count": len(new_to_old),
        "node_conflicts": conflicts,
        "mapping_basis": "common_edge_id_endpoint_pairs",
        "outdegree_source": "current_prepared_edge_nodes",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Align metric labels through common edge IDs.")
    parser.add_argument("--prepared-cache", type=Path, required=True)
    parser.add_argument("--legacy-cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    manifest = align(args.prepared_cache.resolve(), args.legacy_cache.resolve(), args.output.resolve())
    target = args.manifest.resolve() if args.manifest else args.output.with_suffix(args.output.suffix + ".manifest.json")
    target.write_text(__import__("json").dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(__import__("json").dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

