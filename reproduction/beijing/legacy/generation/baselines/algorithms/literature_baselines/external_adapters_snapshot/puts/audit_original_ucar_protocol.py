"""Paper-protocol sanity audit for the bundled original PUTS UCAR experiment."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def parse_pgeom(path: Path, synthetic: bool) -> list[np.ndarray]:
    out = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if synthetic:
            if not line.startswith(">0:"):
                continue
            line = line[3:]
        pts = []
        for token in line.strip().strip(";").split(";"):
            try:
                lon, lat = token.split(",")[:2]
                pts.append([float(lat), float(lon)])
            except ValueError:
                continue
        if len(pts) >= 2:
            out.append(np.asarray(pts, dtype=float))
    return out


def meters(traj: np.ndarray) -> float:
    a, b = np.radians(traj[:-1]), np.radians(traj[1:])
    dlat, dlon = b[:, 0] - a[:, 0], b[:, 1] - a[:, 1]
    h = np.sin(dlat / 2) ** 2 + np.cos(a[:, 0]) * np.cos(b[:, 0]) * np.sin(dlon / 2) ** 2
    return float((6_371_000 * 2 * np.arcsin(np.minimum(1.0, np.sqrt(h)))).sum())


def summary(data: list[np.ndarray]) -> dict:
    return {"n": len(data), "median_points": float(np.median([len(x) for x in data])), "median_length_m": float(np.median([meters(x) for x in data])), "mean_length_m": float(np.mean([meters(x) for x in data]))}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--puts-root", type=Path, required=True)
    ap.add_argument("--synthetic", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    real = parse_pgeom(args.puts_root / "Dataset" / "Ucar" / "pgeom.1000", synthetic=False)
    syn = parse_pgeom(args.synthetic, synthetic=True)
    report = {"protocol": "bundled PUTS UCAR / epsilon=(0.33,0.34,0.33) / safeValue=1.5", "real": summary(real), "synthetic": summary(syn)}
    report["median_length_ratio"] = report["synthetic"]["median_length_m"] / report["real"]["median_length_m"]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
