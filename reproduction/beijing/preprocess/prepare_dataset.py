from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path

from canonical_schema import bbox, load_rows, rows_to_arrays, sha256_file, write_pickle


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert a trajectory dataset to the canonical DFR input schema.")
    parser.add_argument("--dataset", required=True, choices=("beijing", "oldenburg", "porto", "san_francisco"))
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260713)
    parser.add_argument("--train-fraction", type=float, default=0.8)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--network", type=Path)
    parser.add_argument(
        "--bbox",
        nargs=4,
        type=float,
        metavar=("LAT_MIN", "LAT_MAX", "LON_MIN", "LON_MAX"),
        help="keep trajectories having at least one point inside this public geographic window",
    )
    parser.add_argument(
        "--clip-to-bbox",
        action="store_true",
        help="after selecting intersecting trajectories, retain only points inside --bbox;"
        " this is explicit because it changes the point sequence",
    )
    args = parser.parse_args()
    if not 0 < args.train_fraction < 1:
        parser.error("--train-fraction must lie in (0,1)")
    source = args.source.resolve()
    if not source.exists():
        parser.error(f"source does not exist: {source}")
    output = args.out_dir.resolve()
    if output.exists() and any(output.iterdir()):
        parser.error(f"refusing to overwrite non-empty output: {output}")
    output.mkdir(parents=True, exist_ok=True)
    loaded_rows = [trajectory for trajectory in load_rows(source, args.limit) if len(trajectory) >= 2]
    selection = None
    rows = loaded_rows
    if args.bbox:
        lat_min, lat_max, lon_min, lon_max = args.bbox
        if not (lat_min < lat_max and lon_min < lon_max):
            parser.error("--bbox must satisfy LAT_MIN<LAT_MAX and LON_MIN<LON_MAX")
        rows = [
            trajectory
            for trajectory in loaded_rows
            if any(
                lat_min <= point["latitude"] <= lat_max
                and lon_min <= point["longitude"] <= lon_max
                for point in trajectory
            )
        ]
        if args.clip_to_bbox:
            rows = [
                [
                    point
                    for point in trajectory
                    if lat_min <= point["latitude"] <= lat_max
                    and lon_min <= point["longitude"] <= lon_max
                ]
                for trajectory in rows
            ]
            rows = [trajectory for trajectory in rows if len(trajectory) >= 2]
        selection = {
            "rule": "trajectory intersects public bbox"
            + ("; points clipped to bbox" if args.clip_to_bbox else ""),
            "bbox": [lat_min, lat_max, lon_min, lon_max],
            "prefilter_count": len(loaded_rows),
            "selected_count": len(rows),
            "clip_to_bbox": bool(args.clip_to_bbox),
        }
    if len(rows) < 2:
        parser.error("at least two trajectories with two points are required")
    arrays = rows_to_arrays(rows)
    # Keep the compressed canonical copy and an uncompressed compatibility copy
    # because the published baseline loader accepts .pkl but not .pkl.gz.
    write_pickle(output / "trajectories.pkl.gz", arrays)
    write_pickle(output / "trajectories.pkl", arrays)
    with (output / "canonical_records.jsonl.gz").open("wb") as raw:
        import gzip
        with gzip.GzipFile(fileobj=raw, mode="wb") as handle:
            for trajectory in rows:
                handle.write((json.dumps(trajectory, ensure_ascii=False) + "\n").encode("utf-8"))
    rng = random.Random(args.seed)
    order = list(range(len(rows)))
    rng.shuffle(order)
    n_train = max(1, min(len(rows) - 1, round(len(rows) * args.train_fraction)))
    (output / "train_split.json").write_text(json.dumps({"indices": order[:n_train]}, indent=2), encoding="utf-8")
    (output / "test_split.json").write_text(json.dumps({"indices": order[n_train:]}, indent=2), encoding="utf-8")
    (output / "bbox.json").write_text(json.dumps({"bbox": bbox(rows)}, indent=2), encoding="utf-8")
    road = {"status": "unbound", "network": None}
    if args.network:
        network = args.network.resolve()
        road = {"status": "bound", "network": str(network), "sha256": sha256_file(network)}
    (output / "road_reference.json").write_text(json.dumps(road, indent=2), encoding="utf-8")
    if source.is_dir():
        digest = hashlib.sha256()
        for child in sorted(path for path in source.rglob("*") if path.is_file()):
            digest.update(str(child.relative_to(source)).replace("\\", "/").encode("utf-8"))
            digest.update(hashlib.sha256(child.read_bytes()).digest())
        source_hash = digest.hexdigest()
    else:
        source_hash = sha256_file(source)
    manifest = {
        "schema_version": 1,
        "dataset": args.dataset,
        "source": str(source),
        "source_sha256": source_hash,
        "trajectory_count": len(arrays),
        "train_count": n_train,
        "test_count": len(arrays) - n_train,
        "seed": args.seed,
        "schema": "trajectory_id,timestamp,latitude,longitude,sequence_index",
        "road_reference": road,
    }
    if selection is not None:
        manifest["selection"] = selection
    (output / "canonical_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    hashes = {path.name: sha256_file(path) for path in output.iterdir() if path.is_file()}
    (output / "hashes.json").write_text(json.dumps(hashes, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
