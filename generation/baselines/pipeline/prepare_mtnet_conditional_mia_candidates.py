"""FMM-match frozen member/non-member candidates for MTNet conditional MIA."""

from __future__ import annotations

import argparse
import csv
import json
import os
import pickle
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import numpy as np
from pyproj import Transformer


def load_selected_geolife_with_time(raw_root: Path, bbox: tuple[float, float, float, float], wanted: set[int]) -> dict[int, np.ndarray]:
    """Preserve public loader ordering while retaining timestamps only for targets."""
    result: dict[int, np.ndarray] = {}
    trajectory_index = 0
    for file_index, path in enumerate(sorted(raw_root.glob("*/Trajectory/*.plt")), start=1):
        rows = []
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            for _ in range(6):
                next(handle, None)
            for line in handle:
                fields = line.strip().split(",")
                if len(fields) < 7:
                    continue
                try:
                    lat, lon = float(fields[0]), float(fields[1])
                    stamp = None
                except ValueError:
                    continue
                if bbox[0] <= lat <= bbox[1] and bbox[2] <= lon <= bbox[3]:
                    rows.append((lat, lon, fields[5], fields[6]))
        if len(rows) >= 2:
            if trajectory_index in wanted:
                timed = [(lat, lon, datetime.strptime(day + " " + clock, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp()) for lat, lon, day, clock in rows]
                result[trajectory_index] = np.asarray(timed, dtype=float)
            trajectory_index += 1
            if len(result) == len(wanted):
                break
        if file_index % 500 == 0:
            print(f"[MTNet MC-MIA] scanned {file_index:,} source files; located {len(result):,}/{len(wanted):,} targets", flush=True)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attack-manifest", required=True, type=Path)
    parser.add_argument("--raw-root", required=True, type=Path)
    parser.add_argument("--network", required=True, type=Path)
    parser.add_argument("--ubodt", required=True, type=Path)
    parser.add_argument("--fmm", required=True, type=Path)
    parser.add_argument("--fmm-bin", required=True, type=Path)
    parser.add_argument("--fmm-work-dir", required=True, type=Path, help="ASCII-only temporary directory for the native FMM executable")
    parser.add_argument("--full-fmm-matches", type=Path,
                        help="existing FMM output from the identical public network and raw-loader order; avoids re-running Windows FMM")
    parser.add_argument("--training-fmm-matches", type=Path,
                        help="FMM output actually used to construct the target MTNet training input")
    parser.add_argument("--training-split-manifest", type=Path,
                        help="split manifest whose train_indices give the row-to-source join for --training-fmm-matches")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--max-per-class", type=int, default=300)
    parser.add_argument("--max-route-edges", type=int, default=100)
    parser.add_argument("--source-index-max", type=int, default=None, help="optional public deterministic prefix restriction for a bounded preparation run")
    parser.add_argument("--max-gps-points", type=int, default=256,
                        help="deterministic per-record cap for the native FMM point reader; endpoints are retained")
    parser.add_argument("--fmm-batch-records", type=int, default=128,
                        help="maximum trajectories per native FMM invocation (Windows FMM reader stability guard)")
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument("--seed", type=int, default=20260717)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    fmm_work_dir = args.fmm_work_dir.resolve()
    fmm_work_dir.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(args.attack_manifest.read_text(encoding="utf-8"))
    bbox = (39.75, 40.15, 116.10, 116.65)
    rng = np.random.default_rng(args.seed)
    selected_ids = []
    for label, role in ((1, "member_candidates"), (0, "nonmember_candidates")):
        ids = np.asarray(manifest["source_indices"][role], dtype=int)
        if args.source_index_max is not None:
            ids = ids[ids < args.source_index_max]
        if len(ids) == 0:
            raise RuntimeError(f"no {role} candidates remain under --source-index-max")
        ids = rng.choice(ids, min(len(ids), args.max_per_class), replace=False)
        selected_ids.extend((int(source_id), int(label)) for source_id in ids)
    print("[MTNet MC-MIA] loading selected timestamped GeoLife source trajectories", flush=True)
    full = load_selected_geolife_with_time(args.raw_root, bbox, {source_id for source_id, _ in selected_ids})
    print(f"[MTNet MC-MIA] recovered {len(full):,}/{len(selected_ids):,} selected source trajectories", flush=True)
    selected = [(source_id, label, full[source_id]) for source_id, label in selected_ids if source_id in full]
    valid_edges = {int(row.id) for row in gpd.read_file(args.network).itertuples()}
    if args.full_fmm_matches is not None:
        # The full public FMM preparation used the same sorted GeoLife loader:
        # its output row number is the source trajectory index.  FMM writes
        # zero for an unmatched record, hence the row number rather than the
        # output ``id`` is the stable join key.
        csv.field_size_limit(2 ** 31 - 1)
        metadata = {source_id: {"source_index": source_id, "label": label, "departure": float(trace[0, 2]),
                                "duration_seconds": max(1.0, float(trace[-1, 2] - trace[0, 2]))}
                    for source_id, label, trace in selected}
        if (args.training_fmm_matches is None) != (args.training_split_manifest is None):
            raise ValueError("--training-fmm-matches and --training-split-manifest must be supplied together")
        # Strict positive join: the target checkpoint trains on the retained
        # rows of this exact FMM output, not merely on a source-level split.
        exact_member_routes: dict[int, list[int]] = {}
        if args.training_fmm_matches is not None:
            train_indices = json.loads(args.training_split_manifest.read_text(encoding="utf-8"))["train_indices"]
            with args.training_fmm_matches.open("r", encoding="utf-8", errors="ignore", newline="") as handle:
                for row_index, row in enumerate(csv.DictReader(handle, delimiter=";")):
                    if row_index >= len(train_indices):
                        break
                    source_id = int(train_indices[row_index])
                    route = [int(edge) for edge in (row.get("cpath") or "").split(",")
                             if edge.strip().isdigit() and int(edge) in valid_edges]
                    if 2 <= len(route) <= args.max_route_edges:
                        exact_member_routes[source_id] = route
        rows = []
        with args.full_fmm_matches.open("r", encoding="utf-8", errors="ignore", newline="") as handle:
            for source_id, row in enumerate(csv.DictReader(handle, delimiter=";")):
                meta = metadata.get(source_id)
                if meta is None:
                    continue
                route = exact_member_routes.get(source_id) if meta["label"] == 1 else None
                if route is None:
                    route = [int(edge) for edge in (row.get("cpath") or "").split(",")
                             if edge.strip().isdigit() and int(edge) in valid_edges]
                if 2 <= len(route) <= args.max_route_edges:
                    rows.append({**meta, "route": route})
        counts = {str(label): sum(int(item["label"]) == label for item in rows) for label in (0, 1)}
        if min(counts.values()) < 20:
            raise RuntimeError(f"too few compatible candidates in --full-fmm-matches: {counts}")
        with (out / "mtnet_conditional_mia_candidates.pkl").open("wb") as handle:
            pickle.dump({"records": rows}, handle, protocol=pickle.HIGHEST_PROTOCOL)
        (out / "manifest.json").write_text(json.dumps({"attack_manifest": str(args.attack_manifest.resolve()), "records": len(rows), "by_label": counts, "max_route_edges": args.max_route_edges, "source": "frozen candidates with exact target-training FMM positives and public full-corpus FMM negatives", "full_fmm_matches": str(args.full_fmm_matches.resolve()), "training_fmm_matches": str(args.training_fmm_matches.resolve()) if args.training_fmm_matches else None, "training_split_manifest": str(args.training_split_manifest.resolve()) if args.training_split_manifest else None, "join": "full FMM output row number equals sorted-loader source index; training FMM row number maps through train_indices"}, indent=2), encoding="utf-8")
        print(json.dumps({"records": len(rows), "by_label": counts, "fmm": "reused full public matching"}, indent=2), flush=True)
        return
    to_utm = Transformer.from_crs("EPSG:4326", "EPSG:32650", always_xy=True)
    records, lookup = [], {}
    gps = fmm_work_dir / "candidates_gps.csv"
    with gps.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(["id", "x", "y", "timestamp"])
        for record_id, (source_id, label, trace) in enumerate(selected, start=1):
            lookup[str(record_id)] = {"source_index": source_id, "label": label, "departure": float(trace[0, 2]),
                                      "duration_seconds": max(1.0, float(trace[-1, 2] - trace[0, 2]))}
            # FMM's Windows point-CSV reader can overflow on a single very
            # dense GeoLife record.  This is deterministic public geometric
            # preprocessing for map matching only: preserve both endpoints
            # and uniformly retain the temporal order.
            if len(trace) > args.max_gps_points:
                positions = np.linspace(0, len(trace) - 1, args.max_gps_points, dtype=int)
                trace = trace[positions]
            for lat, lon, stamp in trace:
                x, y = to_utm.transform(float(lon), float(lat))
                writer.writerow([record_id, f"{x:.3f}", f"{y:.3f}", f"{stamp:.3f}"])
    print(f"[MTNet MC-MIA] wrote {len(selected):,} candidate trajectories for public FMM", flush=True)
    matched = fmm_work_dir / "fmm_matches.csv"
    base_command = [str(args.fmm.resolve()), "--ubodt", str(args.ubodt.resolve()), "--network", str(args.network.resolve()), "--network_id", "id", "--source", "source", "--target", "target", "--gps_point", "--gps_id", "id", "--gps_x", "x", "--gps_y", "y", "--gps_timestamp", "timestamp", "--candidates", "8", "--radius", "300", "--error", "50", "--output_fields", "cpath", "--use_omp"]
    if args.workers:
        base_command.extend(["--omp_num_threads", str(args.workers)])
    environment = os.environ.copy()
    environment["PATH"] = str(args.fmm_bin) + os.pathsep + str(args.fmm.parent) + os.pathsep + environment.get("PATH", "")
    # The upstream Windows FMM executable has a record-batch stability limit.
    # Split only the point CSV; every batch retains the identical public FMM
    # configuration and original record ids, then concatenate its cpaths.
    batches: dict[int, list[dict[str, str]]] = {}
    with gps.open("r", newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle, delimiter=";"):
            batch_id = (int(row["id"]) - 1) // args.fmm_batch_records
            batches.setdefault(batch_id, []).append(row)
    commands = []
    with matched.open("w", newline="", encoding="utf-8") as combined:
        writer = csv.writer(combined, delimiter=";")
        writer.writerow(["id", "cpath"])
        for batch_id, batch_rows in sorted(batches.items()):
            batch_gps = fmm_work_dir / f"candidates_gps_batch_{batch_id:03d}.csv"
            batch_out = fmm_work_dir / f"fmm_matches_batch_{batch_id:03d}.csv"
            with batch_gps.open("w", newline="", encoding="utf-8") as handle:
                batch_writer = csv.DictWriter(handle, fieldnames=["id", "x", "y", "timestamp"], delimiter=";")
                batch_writer.writeheader(); batch_writer.writerows(batch_rows)
            command = base_command + ["--gps", str(batch_gps), "--output", str(batch_out)]
            print(f"[MTNet MC-MIA] FMM batch {batch_id + 1}/{len(batches)} ({len({r['id'] for r in batch_rows})} trajectories)", flush=True)
            subprocess.run(command, check=True, cwd=fmm_work_dir, env=environment)
            commands.append(command)
            with batch_out.open("r", newline="", encoding="utf-8", errors="ignore") as handle:
                for row in csv.DictReader(handle, delimiter=";"):
                    writer.writerow([row.get("id", ""), row.get("cpath", "")])
    rows = []
    with matched.open("r", encoding="utf-8", errors="ignore", newline="") as handle:
        for row in csv.DictReader(handle, delimiter=";"):
            meta = lookup.get(str(row.get("id")))
            route = [int(edge) for edge in (row.get("cpath") or "").split(",") if edge.strip().isdigit() and int(edge) in valid_edges]
            if meta is not None and 2 <= len(route) <= args.max_route_edges:
                rows.append({**meta, "route": route})
    counts = {str(label): sum(int(item["label"]) == label for item in rows) for label in (0, 1)}
    if min(counts.values()) < 20:
        raise RuntimeError(f"too few FMM-matched attack candidates: {counts}")
    with (out / "mtnet_conditional_mia_candidates.pkl").open("wb") as handle:
        pickle.dump({"records": rows}, handle, protocol=pickle.HIGHEST_PROTOCOL)
    (out / "manifest.json").write_text(json.dumps({"attack_manifest": str(args.attack_manifest.resolve()), "records": len(rows), "by_label": counts, "max_route_edges": args.max_route_edges, "max_gps_points": args.max_gps_points, "fmm_batch_records": args.fmm_batch_records, "source": "frozen candidates plus public FMM", "fmm_commands": commands}, indent=2), encoding="utf-8")
    print(json.dumps({"records": len(rows), "by_label": counts}, indent=2), flush=True)


if __name__ == "__main__":
    main()
