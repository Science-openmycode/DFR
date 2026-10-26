"""Test whether release order exposes a private input--output correspondence.

For every evaluated interface, the attacker treats released record ``i`` as a
putative sanitization/continuation of private record ``i``.  It then ranks the
claimed private record among a fixed-size candidate set using (i) the released
origin and (ii) an eight-landmark trajectory fingerprint.  The same attack is
executed even when a population synthesizer promises no correspondence; in
that case the observed retrieval rate should remain at the random reference.

The configuration records how each release is represented.  Coordinate paths
are consumed directly.  MTNet edge-token paths are converted to public road
coordinates with the declared FMM network.  A released-index manifest may be
used for mechanisms that omit failed records while preserving the order of
successful inputs.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import pickle
from pathlib import Path
from typing import Any

import numpy as np


EARTH_RADIUS_M = 6_371_008.8


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def resolve(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (root / path).resolve()


def load_payload(path: Path, key: str | None) -> Any:
    with path.open("rb") as handle:
        value = pickle.load(handle)
    if key:
        if not isinstance(value, dict) or key not in value:
            raise KeyError(f"{path} has no key {key!r}")
        value = value[key]
    elif isinstance(value, dict):
        for candidate in ("trajectories", "synthetic", "routes", "data", "dp_gsrt_portal_qrsp"):
            if candidate in value:
                value = value[candidate]
                break
    return value


def coordinate_paths(value: Any) -> list[np.ndarray]:
    paths: list[np.ndarray] = []
    for item in value:
        array = np.asarray(item, dtype=float)
        if array.ndim == 2 and array.shape[0] >= 2 and array.shape[1] >= 2:
            paths.append(array[:, :2])
    if not paths:
        raise ValueError("No coordinate trajectories were found")
    return paths


def edge_paths(value: Any, network_path: Path) -> list[np.ndarray]:
    import geopandas as gpd

    network = gpd.read_file(network_path).to_crs(4326)
    if "id" not in network:
        raise ValueError(f"Public network {network_path} has no edge id column")
    starts: dict[int, tuple[float, float]] = {}
    for edge_id, geometry in zip(network["id"], network.geometry):
        coordinate = list(geometry.coords)[0]
        starts[int(edge_id)] = (float(coordinate[1]), float(coordinate[0]))
    paths: list[np.ndarray] = []
    for item in value:
        coordinates = [starts[int(edge)] for edge in np.asarray(item).ravel() if int(edge) in starts]
        if coordinates:
            paths.append(np.asarray(coordinates, dtype=float))
        else:
            raise ValueError("An edge-token trajectory cannot be realized on the declared public network")
    return paths


def load_paths(root: Path, spec: dict[str, Any], prefix: str) -> tuple[list[np.ndarray], list[Path]]:
    path = resolve(root, spec[f"{prefix}_path"])
    value = load_payload(path, spec.get(f"{prefix}_key"))
    representation = spec.get(f"{prefix}_representation", "coordinates")
    sources = [path]
    if representation == "coordinates":
        return coordinate_paths(value), sources
    if representation == "edge_ids":
        network_path = resolve(root, spec["public_network"])
        sources.append(network_path)
        return edge_paths(value, network_path), sources
    raise ValueError(f"Unknown representation: {representation}")


def landmarks(paths: list[np.ndarray], count: int) -> np.ndarray:
    rows = []
    for path in paths:
        positions = np.linspace(0.0, len(path) - 1, count)
        lower = np.floor(positions).astype(int)
        upper = np.ceil(positions).astype(int)
        fraction = (positions - lower)[:, None]
        rows.append(path[lower] * (1.0 - fraction) + path[upper] * fraction)
    return np.stack(rows)


def haversine(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    left_lat, left_lon = np.radians(left[..., 0]), np.radians(left[..., 1])
    right_lat, right_lon = np.radians(right[..., 0]), np.radians(right[..., 1])
    value = np.sin((right_lat - left_lat) / 2.0) ** 2
    value += np.cos(left_lat) * np.cos(right_lat) * np.sin((right_lon - left_lon) / 2.0) ** 2
    return 2.0 * EARTH_RADIUS_M * np.arcsin(np.minimum(1.0, np.sqrt(value)))


def rank_groups(real: np.ndarray, released: np.ndarray, group_size: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    order = rng.permutation(len(real))
    ranks = np.empty(len(real), dtype=int)
    for start in range(0, len(order), group_size):
        group = order[start:start + group_size]
        candidate = real[group]
        query = released[group]
        if real.ndim == 2:  # one origin coordinate per record
            distances = haversine(query[:, None, :], candidate[None, :, :])
        else:  # landmark sequences; average pointwise great-circle distance
            distances = haversine(query[:, None, :, :], candidate[None, :, :, :]).mean(axis=-1)
        ordering = np.argsort(distances, axis=1, kind="stable")
        correct = np.arange(len(group))[:, None]
        ranks[group] = np.argmax(ordering == correct, axis=1) + 1
    return ranks


def summarize(ranks: np.ndarray, group_size: int, prefix: str) -> dict[str, float]:
    return {
        f"{prefix}_top1": float(np.mean(ranks == 1)),
        f"{prefix}_top5": float(np.mean(ranks <= 5)),
        f"{prefix}_mrr": float(np.mean(1.0 / ranks)),
        f"{prefix}_random_top1": 1.0 / group_size,
        f"{prefix}_random_top5": min(5.0 / group_size, 1.0),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    config_path = args.config.resolve()
    public_root = config_path.parent.parent
    config = json.loads(config_path.read_text(encoding="utf-8"))
    group_size = int(config.get("candidate_group_size", 100))
    landmark_count = int(config.get("landmarks", 8))
    seed = int(config.get("seed", 20260724))
    rows = []
    source_hashes: dict[str, str] = {}
    for index, spec in enumerate(config["methods"]):
        real, real_sources = load_paths(public_root, spec, "real")
        released, release_sources = load_paths(public_root, spec, "release")
        if spec.get("released_indices_json"):
            index_path = resolve(public_root, spec["released_indices_json"])
            index_payload = json.loads(index_path.read_text(encoding="utf-8"))
            real = [real[int(i)] for i in index_payload[spec.get("released_indices_key", "released_input_indices")]]
            real_sources.append(index_path)
        n = min(len(real), len(released))
        if n < group_size:
            raise ValueError(f"{spec['name']} has only {n} aligned positions")
        real, released = real[:n], released[:n]
        real_landmarks = landmarks(real, landmark_count)
        released_landmarks = landmarks(released, landmark_count)
        origin_ranks = rank_groups(real_landmarks[:, 0], released_landmarks[:, 0], group_size, seed + index * 101)
        fingerprint_ranks = rank_groups(real_landmarks, released_landmarks, group_size, seed + index * 101)
        row = {
            "method": spec["name"],
            "evaluated_positions": n,
            "candidate_group_size": group_size,
            "landmarks": landmark_count,
            **summarize(origin_ranks, group_size, "origin"),
            **summarize(fingerprint_ranks, group_size, "fingerprint"),
        }
        rows.append(row)
        for path in {*real_sources, *release_sources}:
            source_hashes[str(path)] = sha256(path)
        print(
            f"{spec['name']}: origin Top-1={row['origin_top1']:.4f}; "
            f"fingerprint Top-1={row['fingerprint_top1']:.4f}",
            flush=True,
        )

    output = args.out.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "attack": "ordered-interface origin and trajectory-fingerprint linkage",
        "threat_model": "the attacker assumes release position i corresponds to private input position i and ranks that input among a fixed public candidate group",
        "random_reference": {"top1": 1.0 / group_size, "top5": min(5.0 / group_size, 1.0)},
        "seed": seed,
        "configuration": str(config_path),
        "configuration_sha256": sha256(config_path),
        "source_sha256": source_hashes,
        "rows": rows,
    }
    output.with_suffix(".json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    with output.with_suffix(".csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
