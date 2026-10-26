from __future__ import annotations

import csv
import gzip
import hashlib
import json
import pickle
from pathlib import Path
from typing import Any, Iterable

import numpy as np


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_pickle(path: Path) -> Any:
    opener = gzip.open if path.name.endswith(".gz") else open
    with opener(path, "rb") as handle:
        return pickle.load(handle)


def _coerce_trajectory(value: Any, index: int) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        if "points" in value:
            value = value["points"]
        elif {"latitude", "longitude"}.issubset(value):
            value = [value]
    rows: list[dict[str, Any]] = []
    for position, item in enumerate(value):
        if isinstance(item, dict):
            lat = item.get("latitude", item.get("lat"))
            lon = item.get("longitude", item.get("lon", item.get("lng")))
            timestamp = item.get("timestamp", item.get("time"))
            trajectory_id = item.get("trajectory_id", str(index))
        else:
            lat, lon = item[0], item[1]
            timestamp = item[2] if len(item) > 2 else None
            trajectory_id = str(index)
        if lat is None or lon is None:
            continue
        rows.append({
            "trajectory_id": str(trajectory_id),
            "timestamp": timestamp,
            "latitude": float(lat),
            "longitude": float(lon),
            "sequence_index": position,
        })
    return rows


def _load_geolife_directory(source: Path, limit: int | None = None) -> list[list[dict[str, Any]]]:
    """Read a Geolife ``Data/<user>/*.plt`` tree into canonical trajectories.

    The parser is deliberately format-only: it does not map-match or consult a
    road network.  A PLT file is one trajectory; the first six header lines are
    skipped and the standard latitude, longitude, date and time columns are
    retained.  This keeps the public preprocessing command usable with the
    original directory distributed by Microsoft Research.
    """
    files = sorted(source.rglob("*.plt"))
    if limit is not None:
        files = files[:limit]
    trajectories: list[list[dict[str, Any]]] = []
    for file_index, path in enumerate(files):
        rows: list[dict[str, Any]] = []
        try:
            lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()[6:]
        except OSError:
            continue
        trajectory_id = f"{path.parent.name}/{path.stem}"
        for sequence_index, line in enumerate(lines):
            fields = [item.strip() for item in line.split(",")]
            if len(fields) < 2:
                continue
            try:
                latitude = float(fields[0])
                longitude = float(fields[1])
            except ValueError:
                continue
            timestamp = None
            if len(fields) >= 7 and fields[5] and fields[6]:
                timestamp = f"{fields[5]} {fields[6]}"
            rows.append({
                "trajectory_id": trajectory_id,
                "timestamp": timestamp,
                "latitude": latitude,
                "longitude": longitude,
                "sequence_index": sequence_index,
            })
        if len(rows) >= 2:
            trajectories.append(rows)
    return trajectories


def load_rows(source: Path, limit: int | None = None) -> list[list[dict[str, Any]]]:
    if source.is_dir():
        if any(source.rglob("*.plt")):
            return _load_geolife_directory(source, limit)
        csv_files = sorted(source.rglob("*.csv"))
        if len(csv_files) == 1:
            return load_rows(csv_files[0], limit)
        if csv_files:
            grouped: dict[str, list[dict[str, Any]]] = {}
            for csv_file in csv_files:
                for trajectory in load_rows(csv_file):
                    if trajectory:
                        grouped.setdefault(trajectory[0]["trajectory_id"], []).extend(trajectory)
            values = list(grouped.values())
            return values[:limit] if limit else values
        raise ValueError(f"unsupported trajectory directory: {source}")
    suffix = source.name.lower()
    if suffix.endswith(".pkl") or suffix.endswith(".pkl.gz"):
        value = load_pickle(source)
        if isinstance(value, dict) and "trajectories" in value:
            value = value["trajectories"]
        return [_coerce_trajectory(item, i) for i, item in enumerate(value[:limit] if limit else value)]
    if suffix.endswith(".json"):
        value = json.loads(source.read_text(encoding="utf-8"))
        if isinstance(value, dict) and "trajectories" in value:
            value = value["trajectories"]
        return [_coerce_trajectory(item, i) for i, item in enumerate(value[:limit] if limit else value)]
    if suffix.endswith(".csv"):
        grouped: dict[str, list[dict[str, Any]]] = {}
        with source.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                key = str(row.get("trajectory_id", row.get("trip_id", row.get("id", "0"))))
                grouped.setdefault(key, []).append({
                    "trajectory_id": key,
                    "timestamp": row.get("timestamp", row.get("time")),
                    "latitude": float(row.get("latitude", row.get("lat"))),
                    "longitude": float(row.get("longitude", row.get("lon", row.get("lng")))),
                    "sequence_index": int(row.get("sequence_index", len(grouped[key]))),
                })
        rows = list(grouped.values())
        return rows[:limit] if limit else rows
    raise ValueError(f"unsupported trajectory source: {source}")


def rows_to_arrays(rows: Iterable[list[dict[str, Any]]]) -> list[np.ndarray]:
    return [np.asarray([[point["latitude"], point["longitude"]] for point in trajectory], dtype=float)
            for trajectory in rows if len(trajectory) >= 2]


def write_pickle(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    opener = gzip.open if path.name.endswith(".gz") else open
    with opener(path, "wb") as handle:
        pickle.dump(value, handle, protocol=pickle.HIGHEST_PROTOCOL)


def bbox(rows: Iterable[list[dict[str, Any]]]) -> list[float]:
    points = [point for trajectory in rows for point in trajectory]
    if not points:
        raise ValueError("no valid coordinates")
    lat = [point["latitude"] for point in points]
    lon = [point["longitude"] for point in points]
    return [min(lat), max(lat), min(lon), max(lon)]
