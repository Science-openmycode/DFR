"""Create a fixed-slot neighbouring trajectory database for a canary audit."""

from __future__ import annotations

import argparse
import hashlib
import json
import pickle
import sys
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
FINAL_DIR = ROOT / "src" / "mtr" / "DP_GSRT" / "final"
sys.path[:0] = [str(ROOT), str(ROOT / "src" / "mtr"), str(FINAL_DIR)]
import graph_voronoi_doptimal_support_probe as support  # noqa: E402


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--remove-index", required=True, type=int)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args()
    raw = pickle.loads(args.source.read_bytes())
    index = int(args.remove_index)
    if not 0 <= index < len(raw):
        raise IndexError("remove index is outside the raw fixed-slot database")
    candidate = raw[index]
    normalized = support.normalize_trajectory_records([candidate])
    if len(normalized) != 1:
        raise RuntimeError("Selected canary is excluded by the frozen production normalizer.")
    neighbour = list(raw)
    del neighbour[index]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(pickle.dumps(neighbour, protocol=pickle.HIGHEST_PROTOCOL))
    payload = {
        "adjacency": "fixed 17,123-slot add/remove with a canonical null slot",
        "source": str(args.source.resolve()),
        "source_sha256": digest(args.source),
        "source_raw_records": len(raw),
        "removed_raw_index": index,
        "canary_points": int(len(normalized[0])),
        "neighbour": str(args.out.resolve()),
        "neighbour_sha256": digest(args.out),
        "neighbour_raw_records": len(neighbour),
        "selection": "pre-registered raw index; validated only for frozen-normalizer inclusion",
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
