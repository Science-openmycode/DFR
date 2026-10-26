"""Run upstream PUTS on FMM-prepared inputs without monkey patches.

The output count, DP split and ``safeValue`` are exactly the defaults in the
upstream ``Main.py`` (apart from rescaling the three published weights to the
requested total epsilon).  No synthetic sequence or Markov computation is
overridden here.  This script deliberately refuses a malformed input set.
"""
from __future__ import annotations

import argparse
import importlib
import json
import pickle
import sys
import types
from collections import defaultdict
from pathlib import Path

import numpy as np


def install_import_stub() -> None:
    # Upstream imports an unused optional package before any synthesis begins.
    fake = types.ModuleType("DataProcess"); collection = types.ModuleType("DataProcess.Data_Collection")
    reader = types.ModuleType("DataProcess.Data_Collection.gps_reader")
    class GisTransform: pass
    reader.GisTransform = GisTransform; collection.gps_reader = reader; fake.Data_Collection = collection
    sys.modules.update({"DataProcess": fake, "DataProcess.Data_Collection": collection, "DataProcess.Data_Collection.gps_reader": reader})


def shortest_matrix(geometry_file: Path) -> np.ndarray:
    roads = []
    for line in geometry_file.read_text(encoding="utf-8").splitlines():
        body = line.strip().removeprefix("LINESTRING (").removesuffix(")")
        roads.append([tuple(map(float, token.split()[:2])) for token in body.split(",")])
    owners: dict[tuple[float, float], list[int]] = defaultdict(list)
    for rid, road in enumerate(roads):
        for point in road: owners[(round(point[0], 8), round(point[1], 8))].append(rid)
    graph = [set() for _ in roads]
    for members in owners.values():
        for u in members: graph[u].update(v for v in members if v != u)
    r = len(roads); result = np.full((r, r), r + 100, dtype=np.int32)
    for src in range(r):
        result[src, src] = 0; queue = [src]
        for u in queue:
            for v in graph[u]:
                if result[src, v] > result[src, u] + 1:
                    result[src, v] = result[src, u] + 1; queue.append(v)
        if (src + 1) % 100 == 0 or src + 1 == r: print(f"[shortest] {src + 1}/{r}", flush=True)
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--puts-root", type=Path, required=True)
    ap.add_argument("--prepared", type=Path, required=True, help="directory created by prepare_puts_fmm_beijing_subset.py")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--epsilon", type=float, default=1.0)
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args(); np.random.seed(a.seed)
    prepared, data = a.prepared.resolve(), a.prepared.resolve() / "puts_input"
    cpaths = list(data.glob("cpath.*"))
    if len(cpaths) != 1: raise SystemExit("expected exactly one cpath.<n> under puts_input")
    n = int(cpaths[0].name.split(".")[-1])
    for file in [data / f"opath.{n}", data / f"pgeom.{n}", data / "geometry.txt"]:
        if not file.exists(): raise SystemExit(f"missing {file}")
    a.out.mkdir(parents=True, exist_ok=True)
    shortest = a.out / f"shortestLengthM_{n}.npy"
    print(f"[1/3] computing upstream PUTS shortest-length input for R roads", flush=True)
    np.save(shortest, shortest_matrix(data / "geometry.txt"))
    print("[2/3] invoking upstream PUTS code without method patches", flush=True)
    install_import_stub(); sys.path.insert(0, str(a.puts_root.resolve()))
    GlobalDatabase = importlib.import_module("GlobalDatabase").GlobalDatabase
    SrcDestRegionsSample = importlib.import_module("SrcDestRegionsSample").SrcDestRegionsSample
    RoadTransitionMatrix = importlib.import_module("RoadTransitionMatrix").RoadTransitionMatrix
    RoadSpeedSample = importlib.import_module("RoadSpeedSample").RoadSpeedSample
    ts = importlib.import_module("TrajectorySynthesizer")
    db = GlobalDatabase(str(data / f"pgeom.{n}"), str(data / f"cpath.{n}"), str(data / f"opath.{n}"), str(data / "geometry.txt"), 6, str(shortest))
    trip = SrcDestRegionsSample(db, .33 * a.epsilon)
    transition = RoadTransitionMatrix(db, .34 * a.epsilon)
    speed = RoadSpeedSample(db, 5, 0, 7 * .0003, .33 * a.epsilon)
    # Direct upstream calls: output count=n and safeValue=1.5 are upstream defaults.
    roads = ts.RoadSequenceGenerator(trip, transition, db, 1.5, False).getsyntheticRoadDB()
    synthetic = ts.TrajectoryPointGenerator(speed, db, roads, False).getsyntheticTrajectoryDB()
    release = [np.asarray([[p[1], p[0]] for p in trajectory], dtype=float) for trajectory in synthetic]
    with (a.out / "puts_upstream_fmm.pkl").open("wb") as f: pickle.dump(release, f, pickle.HIGHEST_PROTOCOL)
    ledger = {"method": "PUTS upstream code, unmodified", "n_train": n, "n_release": len(release), "epsilon": a.epsilon, "allocation": [0.33*a.epsilon, .34*a.epsilon, .33*a.epsilon], "regioncount": 6, "speed_bins": 5, "safeValue": 1.5, "map_matching": str(prepared / "prepare_manifest.json"), "forbidden_overrides": ["no A-star bridge input", "no output overdraw", "no Markov recurrence patch", "no support truncation"]}
    (a.out / "puts_upstream_fmm_ledger.json").write_text(json.dumps(ledger, indent=2), encoding="utf-8")
    print(f"[3/3] done: {a.out / 'puts_upstream_fmm.pkl'} (n={len(release)})", flush=True)


if __name__ == "__main__": main()
