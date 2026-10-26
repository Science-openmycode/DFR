"""Apply the MTNet origin-presence observation to adjacent MTR releases.

This is intentionally a diagnostic, not an empirical epsilon estimator.  The
attacker knows a removed record's first GPS location and observes only released
trajectory start locations.  Unlike the MTNet private-condition interface,
MTR does not serialize a source record's first location, so the script measures
continuous-radius counts rather than an exact forwarded-edge event.
"""
from __future__ import annotations

import argparse
import json
import pickle
from pathlib import Path

import numpy as np

EARTH_M = 6_371_008.8


def load(path: Path):
    with path.open("rb") as handle:
        payload = pickle.load(handle)
    if isinstance(payload, dict):
        for key in ("dp_gsrt_portal_qrsp", "trajectories", "routes", "data"):
            if key in payload:
                payload = payload[key]
                break
    return [np.asarray(x, dtype=float)[:, :2] for x in payload if np.asarray(x).ndim == 2 and len(x) >= 2]


def distance_m(points: np.ndarray, target: np.ndarray) -> np.ndarray:
    lat0, lon0 = np.radians(target)
    lat, lon = np.radians(points[:, 0]), np.radians(points[:, 1])
    h = np.sin((lat - lat0) / 2) ** 2 + np.cos(lat0) * np.cos(lat) * np.sin((lon - lon0) / 2) ** 2
    return 2 * EARTH_M * np.arcsin(np.minimum(1, np.sqrt(h)))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-data", type=Path, required=True)
    p.add_argument("--target-index", type=int, action="append", required=True)
    p.add_argument("--source-release", type=Path, required=True)
    p.add_argument("--neighbor-release", type=Path, action="append", required=True)
    p.add_argument("--radii-m", type=float, nargs="+", default=[50, 100, 250, 500])
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    with a.source_data.open("rb") as handle:
        raw = pickle.load(handle)
    source_starts = np.asarray([route[0][:2] for route in load(a.source_release)], dtype=float)
    neighbor_starts = [np.asarray([route[0][:2] for route in load(path)], dtype=float) for path in a.neighbor_release]
    rows = []
    for idx in a.target_index:
        target = np.asarray(raw[idx], dtype=float)[0, :2]
        source_dist = distance_m(source_starts, target)
        neighbor_dist = [distance_m(starts, target) for starts in neighbor_starts]
        for radius in a.radii_m:
            rows.append({
                "target_index": int(idx), "target_lat": float(target[0]), "target_lon": float(target[1]), "radius_m": float(radius),
                "source_count": int((source_dist <= radius).sum()),
                "source_presence": bool((source_dist <= radius).any()),
                "neighbor_counts": [int((values <= radius).sum()) for values in neighbor_dist],
                "neighbor_presence": [bool((values <= radius).any()) for values in neighbor_dist],
                "source_nearest_m": float(source_dist.min()),
                "neighbor_nearest_m": [float(values.min()) for values in neighbor_dist],
            })
    result = {
        "attack": "target_origin_presence_observation",
        "threat_model": "black-box released start locations plus a target record's first GPS location",
        "scope": "three independently randomized neighbouring MTR releases; descriptive only, not an empirical epsilon estimate or independent-path ROC",
        "source_release": str(a.source_release.resolve()),
        "neighbor_releases": [str(path.resolve()) for path in a.neighbor_release],
        "rows": rows,
        "interpretation": "MTR does not carry a deterministic source-origin field. Any observed radius count is an aggregate, randomized release statistic and must be interpreted using the formal DP proof rather than as a per-record correspondence.",
    }
    out = a.out.resolve(); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
