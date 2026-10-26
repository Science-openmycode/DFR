"""Freeze the parent Beijing subset used by the PUTS/DPMM/MTR appendix audit.

PUTS has an FMM-based input eligibility prerequisite.  This utility creates
the parent corpus *before* that prerequisite is evaluated, so MTR and DPMM
remain population-release experiments on all requested trajectories while
PUTS is reported on its separately documented eligible branch.
"""
from __future__ import annotations

import argparse
import json
import pickle
import sys
from pathlib import Path

import numpy as np

PUBLIC_RELEASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PUBLIC_RELEASE))
from public_utils import load_trajectories  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", default="geolife", help="named corpus or serialized trajectory file")
    parser.add_argument("--n", type=int, default=3000, help="fixed parent-corpus size")
    parser.add_argument("--bbox", nargs=4, type=float, default=None,
                        metavar=("LAT_MIN", "LAT_MAX", "LON_MIN", "LON_MAX"))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    # When no geographic filter is requested, asking the loader for exactly N
    # records avoids parsing the whole GeoLife archive merely to retain its
    # deterministic prefix. A bbox may require scanning the entire source.
    raw = load_trajectories(args.data, limit=args.n if args.bbox is None else None)
    indices: list[int] = []
    kept: list[np.ndarray] = []
    lo = hi = None
    if args.bbox is not None:
        lo = np.asarray([args.bbox[0], args.bbox[2]], dtype=float)
        hi = np.asarray([args.bbox[1], args.bbox[3]], dtype=float)
    for source_index, trajectory in enumerate(raw):
        traj = np.asarray(trajectory, dtype=float)
        if len(traj) < 2:
            continue
        if lo is not None and not np.all((traj >= lo) & (traj <= hi)):
            continue
        indices.append(source_index)
        kept.append(traj)
        if len(kept) == args.n:
            break
    if len(kept) != args.n:
        raise RuntimeError(f"only found {len(kept)} valid trajectories; requested {args.n}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("wb") as handle:
        pickle.dump(kept, handle, pickle.HIGHEST_PROTOCOL)
    args.out.with_name(args.out.stem + "_source_indices.json").write_text(
        json.dumps(indices, indent=2), encoding="utf-8"
    )
    manifest = {
        "status": "frozen_parent_subset",
        "data": str(args.data),
        "parent_size": len(kept),
        "selection": "input-order prefix after declared validity and optional bbox filter",
        "bbox": args.bbox,
        "source_indices_file": str(args.out.with_name(args.out.stem + "_source_indices.json")),
        "protocol_note": (
            "This parent corpus is the common input to MTR and DPMM. PUTS FMM "
            "eligibility is evaluated only after this file has been frozen."
        ),
    }
    args.out.with_suffix(".json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"froze parent subset: {len(kept)} trajectories -> {args.out}", flush=True)


if __name__ == "__main__":
    main()
