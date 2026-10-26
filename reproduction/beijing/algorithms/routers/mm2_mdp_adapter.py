"""MM2-MDP public-router adapter.

Consumes one already published M coordinate output plus a prepared public
network. It never reads the private/reference trajectory file and never fills
an aborted, unknown, or disconnected route.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import pickle
import subprocess
import os
from pathlib import Path
from typing import Iterable

import numpy as np


ROUTER = "MM2-MDP"
MM2_FIELDS = ("id", "aborted", "duration", "match", "edge_ids")


def _mm2_srs(value: str) -> str:
    """MM2 accepts the numeric EPSG token rather than ``EPSG:xxxx``."""
    text = str(value).strip()
    if text.upper().startswith("EPSG:"):
        text = text.split(":", 1)[1]
    if not text.isdigit():
        raise ValueError(f"MM2 requires a numeric EPSG code, got {value!r}")
    return text


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_pickle(path: Path):
    opener = gzip.open if path.suffix.lower() == ".gz" else open
    with opener(path, "rb") as handle:
        return pickle.load(handle)


def sample_points(points: np.ndarray, maximum: int) -> np.ndarray:
    if maximum < 2:
        raise ValueError("--max-points must be at least 2")
    array = np.asarray(points, dtype=float)
    if array.ndim != 2 or array.shape[1] < 2:
        raise ValueError(f"trajectory must be an N x 2 array, got {array.shape}")
    array = array[:, :2]
    if len(array) <= maximum:
        return array
    indices = np.unique(np.linspace(0, len(array) - 1, maximum).round().astype(int))
    return array[indices]


def _transformer(input_srs: str, output_srs: str):
    if str(input_srs).lower() == str(output_srs).lower():
        return lambda x, y: (float(x), float(y))
    try:
        from pyproj import Transformer
    except ImportError as exc:
        raise RuntimeError("pyproj is required when --input-srs differs from --tracks-srs") from exc
    return Transformer.from_crs(input_srs, output_srs, always_xy=True).transform


def _as_lat_lon(point: Iterable[float]) -> tuple[float, float]:
    # Canonical M outputs use [latitude, longitude].
    lat, lon = float(point[0]), float(point[1])
    if not math.isfinite(lat) or not math.isfinite(lon):
        raise ValueError("measurement contains a non-finite coordinate")
    return lat, lon


def write_tracks_csv(measurement: Path, destination: Path, *, input_srs: str = "EPSG:4326", tracks_srs: str = "EPSG:32650", maximum: int = 32) -> dict:
    """Export M coordinates to MM2's WKT input format."""
    raw = load_pickle(measurement)
    if not isinstance(raw, (list, tuple)):
        raise ValueError(f"measurement must be a list/tuple of trajectories: {measurement}")
    transform = _transformer(input_srs, tracks_srs)
    destination.parent.mkdir(parents=True, exist_ok=True)
    skipped: list[int] = []
    point_count = 0
    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=("id", "geometry"))
        writer.writeheader()
        for index, track in enumerate(raw):
            try:
                sampled = sample_points(np.asarray(track), maximum)
                coords = []
                for point in sampled:
                    lat, lon = _as_lat_lon(point)
                    x, y = transform(lon, lat)
                    coords.append((float(x), float(y)))
                if len(coords) < 2:
                    raise ValueError("fewer than two points")
                geometry = "LINESTRING(" + ",".join(f"{x:.6f} {y:.6f}" for x, y in coords) + ")"
                writer.writerow({"id": index, "geometry": geometry})
                point_count += len(coords)
            except (TypeError, ValueError, IndexError, OverflowError):
                skipped.append(index)
    return {"records": len(raw), "exported_records": len(raw) - len(skipped), "exported_points": point_count, "skipped_slots": skipped, "max_points": maximum, "input_srs": input_srs, "tracks_srs": tracks_srs, "measurement_sha256": sha256(measurement), "tracks_sha256": sha256(destination)}


def mm2_command(executable: Path, network: Path, tracks: Path, output: Path, *, tracks_srs: str, network_srs: str, threads: int = 1) -> list[str]:
    if threads != 1:
        raise ValueError("MM2 is run single-threaded for reproducible bounded memory")
    args = ["--match", "--input", str(network), "--tracks", str(tracks), "--output", str(output), "--tracks-srs", _mm2_srs(tracks_srs), "--network-srs", _mm2_srs(network_srs), "--wkt", "--geometry", "geometry", "--threads", "1", "--model", "value-iteration", "--columns", ",".join(MM2_FIELDS), "--join-merges", "on", "--concatenate-skips", "off", "--within-edge-turns", "off"]
    # The official MM2 distribution is an AppImage.  On Windows it is run
    # through WSL; all filesystem arguments must be converted to the mounted
    # POSIX path so the binary reads the same public files and writes its CSV
    # into the requested output directory.  Native Linux callers keep the
    # original command unchanged.
    if executable.suffix.lower() == ".appimage" and os.name == "nt":
        def wsl_path(path: str) -> str:
            p = os.path.abspath(path)
            drive, tail = os.path.splitdrive(p)
            if drive:
                return "/mnt/" + drive[0].lower() + tail.replace("\\", "/")
            return p.replace("\\", "/")
        translated = []
        for value in args:
            if value.startswith("--") or value in {"on", "off", "wkt", "geometry", "1", "value-iteration", ",".join(MM2_FIELDS), _mm2_srs(tracks_srs), _mm2_srs(network_srs)}:
                translated.append(value)
            else:
                translated.append(wsl_path(value))
        return ["wsl.exe", "--", wsl_path(str(executable)), *translated]
    return [str(executable), *args]


def _read_mm2_rows(path: Path) -> list[dict]:
    # MM2 stores the matched geometry in the ``match`` field.  A single
    # long route can exceed Python csv's conservative 128 KiB default even
    # though the output is valid.  Raise the parser limit before reading; do
    # not truncate or silently discard the row.
    csv.field_size_limit(max(csv.field_size_limit(), 64 * 1024 * 1024))
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != MM2_FIELDS:
            raise ValueError(f"unexpected MM2 output columns: {reader.fieldnames}")
        rows = list(reader)
    seen = set()
    for row in rows:
        if any(value is None for value in row.values()):
            raise ValueError("MM2 output contains a truncated row")
        index = int(row["id"])
        if index in seen:
            raise ValueError(f"duplicate MM2 output id: {index}")
        seen.add(index)
        if row["aborted"] not in {"yes", "no"}:
            raise ValueError(f"invalid aborted value for id {index}: {row['aborted']}")
        duration = float(row["duration"])
        if not math.isfinite(duration) or duration < 0:
            raise ValueError(f"invalid duration for id {index}: {row['duration']}")
    return rows


def _edge_cache(path: Path) -> dict[int, tuple[int, int]]:
    value = load_pickle(path)
    if not isinstance(value, dict) or "edge_nodes" not in value:
        raise ValueError("edge cache must contain an edge_nodes mapping")
    return {int(key): tuple(map(int, pair)) for key, pair in value["edge_nodes"].items()}


def decode_edge_ids(raw_ids: str, edge_nodes: dict[int, tuple[int, int]]) -> tuple[list[int], str]:
    """Convert MM2 way ids (edge_id + 1) to canonical public edge ids."""
    values = [int(value) - 1 for value in raw_ids.split(",") if value.strip()]
    if not values:
        return [], "empty"
    if any(value not in edge_nodes for value in values):
        return [], "unknown_edge"
    deduped: list[int] = []
    for value in values:
        if not deduped or deduped[-1] != value:
            deduped.append(value)
    pairs = [edge_nodes[value] for value in deduped]
    if any(left[1] != right[0] for left, right in zip(pairs, pairs[1:])):
        return [], "disconnected"
    return deduped, "accepted"


def convert_rows(rows: list[dict], edge_nodes: dict[int, tuple[int, int]], expected: int,
                 public_edge_nodes: dict[int, tuple[int, int]] | None = None) -> tuple[list[dict], dict[str, int]]:
    by_id = {int(row["id"]): row for row in rows}
    if set(by_id) != set(range(expected)):
        missing = sorted(set(range(expected)).difference(by_id))[:10]
        extra = sorted(set(by_id).difference(range(expected)))[:10]
        raise ValueError(f"MM2 output IDs do not cover M slots; missing={missing}, extra={extra}")
    routes: list[dict] = []
    reasons: dict[str, int] = {}
    for index in range(expected):
        row = by_id[index]
        if row["aborted"] == "yes":
            cpath, reason = [], "aborted"
        elif row["match"].startswith('MULTILINESTRING'):
            cpath, reason = [], 'gapped_geometry'
        else:
            _, original_reason = decode_edge_ids(row['edge_ids'], public_edge_nodes or edge_nodes)
            if original_reason != 'accepted':
                cpath, reason = [], original_reason
            else:
                cpath, reason = decode_edge_ids(row["edge_ids"], edge_nodes)
        reasons[reason] = reasons.get(reason, 0) + 1
        routes.append({"source_index": index, "accepted": reason == "accepted", "cpath": cpath, "reason": reason, "duration": float(row["duration"]), "match_wkt": row["match"]})
    return routes, reasons


def run_mm2(measurement: Path, out_dir: Path, *, executable: Path, network: Path, edge_cache: Path, input_srs: str = "EPSG:4326", tracks_srs: str = "EPSG:32650", network_srs: str = "EPSG:32650", max_points: int = 32, seed: int | None = None) -> dict:
    """Run MM2 and write the stable road-route output for one M cell."""
    for path, label in ((measurement, "measurement"), (executable, "MM2 executable"), (network, "MM2 network"), (edge_cache, "edge cache")):
        if not path.exists():
            raise FileNotFoundError(f"{label} not found: {path}")
    if out_dir.exists():
        raise FileExistsError(f"refusing to overwrite MM2 output: {out_dir}")
    out_dir.mkdir(parents=True)
    tracks = out_dir / "mm2_tracks.csv"
    export = write_tracks_csv(measurement, tracks, input_srs=input_srs, tracks_srs=tracks_srs, maximum=max_points)
    run_dir = out_dir / "mm2_run"
    command = mm2_command(executable, network, tracks, run_dir, tracks_srs=tracks_srs, network_srs=network_srs)
    (out_dir / "mm2_command.json").write_text(json.dumps(command, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result_csv = run_dir / "matches.csv"
    if export['exported_records']:
        completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
        (out_dir / "mm2_stdout.log").write_text(completed.stdout or "", encoding="utf-8")
        (out_dir / "mm2_stderr.log").write_text(completed.stderr or "", encoding="utf-8")
        if completed.returncode != 0:
            (out_dir / "route_manifest.json").write_text(json.dumps({"schema_version": 1, "kind": "route_cell", "router": ROUTER, "status": "INVALID", "returncode": completed.returncode, "command": command, "export": export}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            raise RuntimeError(f"MM2 failed with exit code {completed.returncode}; see {out_dir / 'mm2_stderr.log'}")
    else:
        run_dir.mkdir()
        with result_csv.open('w',newline='',encoding='utf-8') as handle:
            csv.writer(handle).writerow(MM2_FIELDS)
        (out_dir/'mm2_stdout.log').write_text('NOT_EXECUTED: no eligible M coordinate slots\n',encoding='utf-8')
    if not result_csv.is_file():
        raise FileNotFoundError(f"MM2 completed without matches.csv: {result_csv}")
    rows = _read_mm2_rows(result_csv)
    raw = load_pickle(measurement)
    expected_ids = set(range(len(raw))) - set(export['skipped_slots'])
    if {int(row['id']) for row in rows} != expected_ids:
        raise ValueError('MM2 output does not cover exactly the exported M slots')
    rows += [dict(id=str(i), aborted='yes', duration='0', match='', edge_ids='') for i in export['skipped_slots']]
    public_map_path = network.parent/'public_graph/inputs/public_edge_nodes.json'
    public_nodes = None
    if public_map_path.is_file():
        public_nodes = {int(k): tuple(v) for k,v in json.loads(public_map_path.read_text(encoding='utf-8')).items()}
    routes, reasons = convert_rows(rows, _edge_cache(edge_cache), len(raw), public_nodes)
    if export['skipped_slots']:
        reasons['aborted'] -= len(export['skipped_slots'])
        reasons['invalid_input_coordinate'] = len(export['skipped_slots'])
        for i in export['skipped_slots']:
            routes[i]['reason'] = 'invalid_input_coordinate'
    output = out_dir / "synthetic_routes.pkl.gz"
    with gzip.open(output, "wb") as handle:
        pickle.dump(routes, handle, protocol=pickle.HIGHEST_PROTOCOL)
    manifest = {"schema_version": 1, "kind": "route_cell", "router": ROUTER, "status": "VALID", "route_generation": "executed_public_mm2_value_iteration", "raw_source_used": False, "measurement": str(measurement.resolve()), "measurement_sha256": sha256(measurement), "public_mm2_executable": str(executable.resolve()), "public_mm2_executable_sha256": sha256(executable), "public_mm2_network": str(network.resolve()), "public_edge_cache": str(edge_cache.resolve()), "public_edge_cache_sha256": sha256(edge_cache), "input_srs": input_srs, "tracks_srs": tracks_srs, "network_srs": network_srs, "max_points": max_points, "seed": seed, "records": len(routes), "reasons": reasons, "output": str(output), "output_sha256": sha256(output), "command": command}
    manifest.update(export=export, public_raw_node_connectivity_checked=public_nodes is not None,
                    public_edge_nodes_sha256=sha256(public_map_path) if public_nodes is not None else None,
                    mm2_executed=bool(export['exported_records']))
    if not export['exported_records']:
        manifest['route_generation'] = 'no_eligible_M_coordinates_native_not_executed'
    (out_dir / "route_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run MM2-MDP on one already-published M coordinate output")
    parser.add_argument("--measurement", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--executable", type=Path, required=True, help="official MM2 executable")
    parser.add_argument("--network", type=Path, required=True, help="prepared public MM2 network directory")
    parser.add_argument("--edge-cache", type=Path, required=True, help="public evaluator edge_nodes cache")
    parser.add_argument("--input-srs", default="EPSG:4326")
    parser.add_argument("--tracks-srs", default="EPSG:32650")
    parser.add_argument("--network-srs", default="EPSG:32650")
    parser.add_argument("--max-points", type=int, default=32)
    parser.add_argument("--seed", type=int)
    return parser


if __name__ == "__main__":
    options = build_parser().parse_args()
    print(json.dumps(run_mm2(**vars(options)), ensure_ascii=False, indent=2))
