"""Materialize the exact raw member records corresponding to a DPMM release."""

from __future__ import annotations

import argparse
import json
import pickle
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--parent", required=True, type=Path)
    parser.add_argument("--dpmm-manifest", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    parent = pickle.loads(args.parent.read_bytes())
    manifest = json.loads(args.dpmm_manifest.read_text(encoding="utf-8"))
    indices = manifest["released_input_indices"]
    members = [parent[index] for index in indices]
    if len(members) != int(manifest["output_count"]):
        raise RuntimeError("The selected raw member count does not match the DPMM output count.")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(pickle.dumps(members, protocol=pickle.HIGHEST_PROTOCOL))
    print(json.dumps({"members": len(members), "source_indices": len(indices), "out": str(args.out)}, indent=2))


if __name__ == "__main__":
    main()
