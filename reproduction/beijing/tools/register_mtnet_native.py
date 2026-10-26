"""Register a frozen MTNet native edge release for the current input batch.

This adapter performs only a representation conversion from the frozen
MTNet edge-id tuples to the current public ``(source, target)`` edge schema.
It never reads raw trajectories and never performs FMM/STMatch or any other
route selection.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import pickle
from pathlib import Path


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_pickle(path: Path):
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rb") as f:
        return pickle.load(f)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--native-dir", type=Path, required=True)
    ap.add_argument("--edge-cache", type=Path, required=True)
    ap.add_argument("--input-reference-sha256", required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    native = args.native_dir.resolve()
    edge_cache = load_pickle(args.edge_cache.resolve())
    edge_nodes = {int(k): (int(v[0]), int(v[1])) for k, v in edge_cache["edge_nodes"].items()}
    edge_file = native / "native_edge_ids.pkl.gz"
    if not edge_file.is_file():
        raise FileNotFoundError(edge_file)
    routes = load_pickle(edge_file)
    if not isinstance(routes, list):
        raise ValueError("native_edge_ids must be a list of per-slot tuples")

    converted: list[list[tuple[int, int]]] = []
    unknown: list[int] = []
    disconnected = 0
    for slot, seq in enumerate(routes):
        if not isinstance(seq, (list, tuple)):
            raise ValueError(f"slot {slot} is not an edge-id sequence")
        out: list[tuple[int, int]] = []
        previous_target = None
        for value in seq:
            edge_id = int(value)
            edge = edge_nodes.get(edge_id)
            if edge is None:
                unknown.append(edge_id)
                continue
            if previous_target is not None and edge[0] != previous_target:
                disconnected += 1
            out.append(edge)
            previous_target = edge[1]
        converted.append(out)
    if unknown:
        raise ValueError(f"{len(unknown)} MTNet edge ids are absent from the current public edge cache")

    out = args.out.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(out, "wb") as f:
        pickle.dump(converted, f, protocol=pickle.HIGHEST_PROTOCOL)
    manifest = {
        "schema_version": 1,
        "kind": "native_route_representation",
        "method": "MTNet",
        "native_original_route": True,
        "rematched": False,
        "raw_source_used": False,
        "public_slot_count": len(converted),
        "nonempty_slot_count": sum(bool(x) for x in converted),
        "unknown_edge_id_count": 0,
        "disconnected_transition_count": disconnected,
        "source_native_edge_ids": {"path": str(edge_file), "sha256": sha256(edge_file)},
        "edge_cache": {"path": str(args.edge_cache.resolve()), "sha256": sha256(args.edge_cache.resolve())},
        "input_reference_sha256": args.input_reference_sha256,
        "output": {"path": str(out), "sha256": sha256(out)},
        "conversion": "MTNet native public-edge tuple -> current (source,target) pairs; no matching",
    }
    out.with_suffix(out.suffix + ".manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
