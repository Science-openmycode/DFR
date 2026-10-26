"""Prepare coordinate-paired releases for the official RAoPT implementation.

RAoPT (Buchholz et al., ACSAC 2022) evaluates a recordwise protection
mechanism: each protected trajectory has the same identifier as its raw
counterpart.  This adapter only converts existing ``(lat, lon)`` numpy arrays
to RAoPT's documented CSV schema.  It never modifies coordinates, map-matches,
resamples, reroutes, or otherwise repairs a release.

The synthetic timestamps are an identifier-independent CSV requirement of the
official code.  They are identical for raw and protected copies of a record,
so the attack observes coordinates only; no private time values are introduced.
"""

from __future__ import annotations

import argparse
import json
import pickle
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert aligned trajectory pickles to RAoPT official CSV inputs."
    )
    parser.add_argument("--original", required=True, help="Raw aligned trajectory pickle.")
    parser.add_argument("--protected", required=True, help="Protected aligned trajectory pickle.")
    parser.add_argument(
        "--protected-manifest",
        required=True,
        help="DPMM manifest with released_input_indices emitted by the official adapter.",
    )
    parser.add_argument("--out-dir", required=True, help="Output directory for originals.csv and protected.csv.")
    parser.add_argument("--name", default="release", help="Protocol label written to manifest.")
    parser.add_argument("--max-length", type=int, default=200, help="Public RAoPT sequence cap.")
    return parser.parse_args()


def load(path: Path) -> list[np.ndarray]:
    with path.open("rb") as handle:
        values = pickle.load(handle)
    if not isinstance(values, list):
        raise TypeError(f"{path} must contain a list of trajectories, got {type(values)!r}")
    result: list[np.ndarray] = []
    for index, trajectory in enumerate(values):
        array = np.asarray(trajectory, dtype=float)
        if array.ndim != 2 or array.shape[1] < 2 or len(array) < 2:
            raise ValueError(f"trajectory {index} in {path} is not an Nx2 trajectory")
        if not np.isfinite(array[:, :2]).all():
            raise ValueError(f"trajectory {index} in {path} contains non-finite coordinates")
        result.append(array[:, :2])
    return result


def to_frame(trajectories: list[np.ndarray], max_length: int) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    epoch = datetime(2000, 1, 1, tzinfo=timezone.utc)
    for tid, trajectory in enumerate(trajectories):
        # RAoPT requires a declared finite sequence cap.  Do not resample: retain
        # the release prefix exactly as emitted and record the cap in the manifest.
        for point_index, (lat, lon) in enumerate(trajectory[:max_length]):
            rows.append(
                {
                    "trajectory_id": str(tid),
                    "uid": 0,
                    "latitude": float(lat),
                    "longitude": float(lon),
                    "timestamp": (epoch + timedelta(seconds=point_index)).isoformat(),
                }
            )
    return pd.DataFrame(rows)


def main() -> None:
    args = parse_args()
    original_path = Path(args.original).resolve()
    protected_path = Path(args.protected).resolve()
    protected_manifest_path = Path(args.protected_manifest).resolve()
    output = Path(args.out_dir).resolve()
    original = load(original_path)
    protected = load(protected_path)
    manifest_payload = json.loads(protected_manifest_path.read_text(encoding="utf-8"))
    source_indices = [int(value) for value in manifest_payload.get("released_input_indices", [])]
    if len(source_indices) != len(protected):
        raise ValueError(
            "DPMM manifest must provide one released_input_indices entry for every protected trajectory; "
            f"got {len(source_indices)} indices and {len(protected)} protected trajectories."
        )
    if any(index < 0 or index >= len(original) for index in source_indices):
        raise ValueError("DPMM manifest contains an input index outside the raw trajectory collection")
    original = [original[index] for index in source_indices]
    output.mkdir(parents=True, exist_ok=True)
    to_frame(original, args.max_length).to_csv(output / "originals.csv", index=False)
    to_frame(protected, args.max_length).to_csv(output / "protected.csv", index=False)
    manifest = {
        "attack": "RAoPT official implementation input adapter",
        "paper": "Buchholz et al., ACSAC 2022, DOI 10.1145/3564625.3564628",
        "release_label": args.name,
        "original": str(original_path),
        "protected": str(protected_path),
        "protected_manifest": str(protected_manifest_path),
        "trajectory_pairs": len(original),
        "coordinate_transform": "none; stored input coordinates are copied exactly",
        "timestamps": "public synthetic point indices, identical per raw/protected pair",
        "max_length": args.max_length,
        "pairing": "released_input_indices ledger emitted by the DPMM official adapter",
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
