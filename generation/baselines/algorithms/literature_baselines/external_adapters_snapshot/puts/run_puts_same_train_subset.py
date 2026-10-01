"""Run the unmodified PUTS algorithm on a genuinely matched small subset.

The original implementation materializes (L+1) x R x R dense Markov powers.
For a 1,000-trajectory Beijing prefix this exceeds 2.8 GiB before temporary
matrix products; this script therefore uses the first 100 records, for which
the original tensor is about 0.29 GiB.  Crucially, PUTS and the companion MTR
native-graph diagnostic must both use this exact input prefix and the exact
road subset derived by PUTS's own CpathDatabase.

No synthesis rule in PUTS is edited.  The only operational override is the
public number of requested release slots, so enough drawable output records
can be retained for a count-matched visualization.
"""
from __future__ import annotations

import argparse
import heapq
import importlib
import logging
import pickle
import shutil
import sys
import types
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

PUBLIC_RELEASE = Path(__file__).resolve().parents[2]
if str(PUBLIC_RELEASE) not in sys.path:
    sys.path.insert(0, str(PUBLIC_RELEASE))
from public_utils import load_osm_ways


def install_optional_dependency_stub() -> None:
    """PUTS imports this unused preprocessing class at module import time."""
    fake = types.ModuleType("DataProcess")
    collection = types.ModuleType("DataProcess.Data_Collection")
    reader = types.ModuleType("DataProcess.Data_Collection.gps_reader")
    class GisTransform:  # noqa: N801 - preserve the original import name
        def transform_func(self, *args):
            return args
    reader.GisTransform = GisTransform
    collection.gps_reader = reader; fake.Data_Collection = collection
    sys.modules.update({"DataProcess": fake, "DataProcess.Data_Collection": collection,
                        "DataProcess.Data_Collection.gps_reader": reader})


def build_puts_input_from_raw(real_path: Path, osm_cache: Path, output: Path, n_train: int, top_k: int) -> tuple[int, dict]:
    """Map the supplied raw trajectories to the original PUTS road-state input.

    This follows the repository's supplied Beijing builder: nearest public OSM
    segment midpoint, consecutive-state deduplication, public top-K support,
    and 80-state truncation.  Crucially, the geometry file is written in the
    same reindexed order as cpath, unlike the obsolete adapter.
    """
    with real_path.open("rb") as handle:
        raw = [np.asarray(x, dtype=float) for x in pickle.load(handle)[:n_train]]
    ways = load_osm_ways(osm_cache)
    roads: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for way in ways:
        pts = [(float(p["lat"]), float(p["lon"])) for p in way.get("geometry", [])]
        roads.extend((a, b) for a, b in zip(pts[:-1], pts[1:]) if a != b)
    mids = np.asarray([[(a[0] + b[0]) / 2, (a[1] + b[1]) / 2] for a, b in roads])
    tree = cKDTree(mids)
    endpoint_roads: dict[tuple[float, float], list[int]] = defaultdict(list)
    for rid, (a, b) in enumerate(roads):
        endpoint_roads[(round(a[0], 6), round(a[1], 6))].append(rid)
        endpoint_roads[(round(b[0], 6), round(b[1], 6))].append(rid)
    adjacency: list[set[int]] = [set() for _ in roads]
    for members in endpoint_roads.values():
        for rid in members:
            adjacency[rid].update(other for other in members if other != rid)

    def bridge(src: int, dst: int, max_visits: int = 18000) -> list[int] | None:
        """Public-road A* bridge used only to create PUTS's required matched cpath."""
        if src == dst:
            return [src]
        parent: dict[int, int] = {}
        best = {src: 0.0}
        queue = [(float(np.linalg.norm(mids[src] - mids[dst])), 0.0, src)]
        visits = 0
        while queue and visits < max_visits:
            _, cost, node = heapq.heappop(queue)
            if cost != best.get(node):
                continue
            visits += 1
            if node == dst:
                out = [dst]
                while out[-1] != src:
                    out.append(parent[out[-1]])
                return list(reversed(out))
            for nxt in adjacency[node]:
                candidate = cost + float(np.linalg.norm(mids[node] - mids[nxt]))
                if candidate < best.get(nxt, float("inf")):
                    best[nxt] = candidate; parent[nxt] = node
                    heapq.heappush(queue, (candidate + float(np.linalg.norm(mids[nxt] - mids[dst])), candidate, nxt))
        return None
    # Keep provenance to the original raw record.  A fair companion-method
    # run must fit on exactly these accepted records, not on the larger input
    # prefix before native PUTS's map-matching eligibility filter.
    matched: list[tuple[list[int], np.ndarray, list[int], int, np.ndarray]] = []
    usage: Counter[int] = Counter()
    for source_index, traj in enumerate(raw):
        if len(traj) < 3:
            continue
        # First snap GPS observations, then bridge successive snaps on the
        # public road graph. PUTS assumes map-matched *connected* road states;
        # independent pointwise nearest-segment labels violate that assumption.
        # PUTS's dense all-step transition tensor is defined over connected
        # road-state sequences.  Use the matched trip endpoints and the public
        # shortest road chain between them; do not subsample an already-built
        # chain, which would create artificial non-adjacent transitions.
        snap_idx = np.asarray([0, len(traj) - 1], dtype=int)
        raw_ids = [int(x) for x in tree.query(traj, k=1)[1].tolist()]
        snapped = [raw_ids[int(i)] for i in snap_idx]
        seq = [snapped[0]]
        for nxt in snapped[1:]:
            chain = bridge(seq[-1], nxt)
            if chain is None:
                seq.append(nxt)
            else:
                seq.extend(chain[1:])
        if len(seq) > 80:
            # The supplied PUTS datasets cap matched sequences at 80 states.
            # Excluding a long route preserves graph validity; index thinning
            # would not.
            continue
        # Match pgeom samples one-for-one with the retained PUTS states.
        traj = traj[np.linspace(0, len(traj) - 1, len(seq), dtype=int)]
        if len(seq) >= 2:
            seq = seq[:80]
            matched.append((seq, traj, raw_ids, source_index, traj.copy()))
            usage.update(seq)
    selected = [rid for rid, _ in usage.most_common(min(top_k, len(usage)))]
    old_to_new = {rid: i for i, rid in enumerate(selected)}
    final = []
    for seq, traj, raw_ids, source_index, source_traj in matched:
        # cpath: connected public bridge. opath/pgeom: repeated per-GPS road
        # observations, required by PUTS's original speed sampler.
        kept = [old_to_new[r] for r in seq if r in old_to_new]
        observed = [(old_to_new[r], point) for r, point in zip(raw_ids, traj) if r in old_to_new]
        if len(kept) >= 2 and len(observed) >= 2:
            final.append((kept, [r for r, _ in observed], np.asarray([p for _, p in observed], dtype=float), source_index, source_traj))
    if not final:
        raise RuntimeError("No supplied raw trajectories could be converted to PUTS road sequences")
    used_new = {r for cpath, _, _, _, _ in final for r in cpath}
    cleaned = []
    for cpath, opath, points, source_index, source_traj in final:
        observed = [(r, p) for r, p in zip(opath, points) if r in used_new]
        if len(observed) >= 2:
            cleaned.append((cpath, [r for r, _ in observed], np.asarray([p for _, p in observed], dtype=float), source_index, source_traj))
    final = cleaned
    (output / f"cpath.{len(final)}").write_text("\n".join(",".join(map(str, cpath)) for cpath, _, _, _, _ in final) + "\n", encoding="utf-8")
    (output / f"opath.{len(final)}").write_text("\n".join(",".join(map(str, opath)) for _, opath, _, _, _ in final) + "\n", encoding="utf-8")
    (output / f"pgeom.{len(final)}").write_text("\n".join(
        ";".join(f"{point[1]},{point[0]}" for point in points) for _, _, points, _, _ in final
    ) + "\n", encoding="utf-8")
    (output / "geometry.txt").write_text("\n".join(
        "LINESTRING (" + ",".join(f"{lon} {lat}" for lat, lon in roads[rid]) + ")" for rid in selected
    ) + "\n", encoding="utf-8")
    accepted_raw = [source_traj for _, _, _, _, source_traj in final]
    accepted_indices = [int(source_index) for _, _, _, source_index, _ in final]
    accepted_path = output.parent / "accepted_raw_for_fair_comparison.pkl"
    with accepted_path.open("wb") as handle:
        pickle.dump(accepted_raw, handle, pickle.HIGHEST_PROTOCOL)
    (output.parent / "accepted_raw_for_fair_comparison_indices.json").write_text(
        __import__("json").dumps({"source_file": str(real_path), "source_indices": accepted_indices}, indent=2),
        encoding="utf-8",
    )
    return len(final), {"raw_requested": n_train, "raw_with_road_sequence": len(matched), "final_matched": len(final), "selected_roads": len(selected), "all_matched_roads": len(usage), "matcher": "public-road snap plus A-star bridge", "fair_comparison_raw_subset": str(accepted_path), "fair_comparison_source_indices": str(output.parent / "accepted_raw_for_fair_comparison_indices.json")}


def selected_road_ids(cpath: Path) -> list[int]:
    return sorted({int(x) for line in cpath.read_text().splitlines() for x in line.split(",") if x})


def geometry(path: Path, road_ids: list[int]) -> list[list[tuple[float, float]]]:
    source = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    output = []
    for road_id in road_ids:
        points = []
        for token in source[road_id].strip().removeprefix("LINESTRING (").removesuffix(")").split(","):
            lon, lat = map(float, token.split()[:2]); points.append((lon, lat))
        output.append(points)
    return output


def shortest_matrix(roads: list[list[tuple[float, float]]]) -> np.ndarray:
    owners: dict[tuple[float, float], list[int]] = defaultdict(list)
    for i, line in enumerate(roads):
        for point in line:
            owners[(round(point[0], 7), round(point[1], 7))].append(i)
    graph = [set() for _ in roads]
    for members in owners.values():
        for member in members:
            graph[member].update(other for other in members if other != member)
    size = len(graph); result = np.full((size, size), size + 100, dtype=np.int32)
    for source in range(size):
        result[source, source] = 0; queue = [source]
        for node in queue:
            for neighbour in graph[node]:
                if result[source, neighbour] > result[source, node] + 1:
                    result[source, neighbour] = result[source, node] + 1; queue.append(neighbour)
        if (source + 1) % 100 == 0 or source + 1 == size:
            print(f"  shortest-path rows {source+1}/{size}", flush=True)
    return result


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--puts-root", type=Path, required=True)
    p.add_argument("--real", type=Path, required=True, help="the exact raw trajectory subset also given to MTR")
    p.add_argument("--osm-cache", type=Path, required=True, help="public OSM used only to form PUTS's required road states")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--n-train", type=int, default=100)
    p.add_argument("--n-gen", type=int, default=100)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--epsilon", type=float, default=1.0)
    p.add_argument("--top-k-roads", type=int, default=3000)
    p.add_argument(
        "--allow-reduced-support",
        action="store_true",
        help="allow a top-K road subset; this is a scalability diagnostic, not a paper-faithful PUTS run",
    )
    p.add_argument("--safe-value", type=float, default=10.0, help="original PUTS maximum-length multiplier")
    p.add_argument("--prepare-only", action="store_true", help="write and audit PUTS-format inputs without fitting")
    a = p.parse_args(); np.random.seed(a.seed)
    data = a.out / "puts_original_input"
    data.mkdir(parents=True, exist_ok=True)
    print("[1/5] Converting the supplied raw subset into original PUTS inputs...", flush=True)
    n_effective, conversion = build_puts_input_from_raw(a.real, a.osm_cache, data, a.n_train, a.top_k_roads)
    if conversion["selected_roads"] < conversion["all_matched_roads"] and not a.allow_reduced_support:
        raise RuntimeError(
            "Refusing a reduced-road PUTS run without --allow-reduced-support. "
            "The original PUTS protocol operates on its complete matched-road support; "
            "a top-K subset is only a documented scalability diagnostic."
        )
    print(f"      raw-to-PUTS conversion: {conversion}", flush=True)
    if a.prepare_only:
        (a.out / "input_conversion.json").write_text(__import__("json").dumps(conversion, indent=2), encoding="utf-8")
        return
    cpath = data / f"cpath.{n_effective}"
    used = selected_road_ids(cpath)
    print(f"      training records={a.n_train}; PUTS-selected roads={len(used)}", flush=True)
    print("[2/5] Computing the original algorithm's public shortest-length matrix...", flush=True)
    matrix = shortest_matrix(geometry(data / "geometry.txt", used))
    shortest = data / f"shortestLengthM_{n_effective}.npy"; np.save(shortest, matrix)
    (a.out / "used_road_ids.txt").write_text("\n".join(map(str, used)) + "\n", encoding="utf-8")

    print("[3/5] Importing the original PUTS modules (no synthesis edits)...", flush=True)
    install_optional_dependency_stub(); sys.path.insert(0, str(a.puts_root))
    # The upstream RegionMap emits one warning per unassigned road, which can
    # overwhelm a long experiment log without conveying progress.
    logging.disable(logging.WARNING)
    GlobalDatabase = importlib.import_module("GlobalDatabase").GlobalDatabase
    SrcDestRegionsSample = importlib.import_module("SrcDestRegionsSample").SrcDestRegionsSample
    RoadTransitionMatrix = importlib.import_module("RoadTransitionMatrix").RoadTransitionMatrix
    RoadSpeedSample = importlib.import_module("RoadSpeedSample").RoadSpeedSample
    ts = importlib.import_module("TrajectorySynthesizer")
    db = GlobalDatabase(str(data / f"pgeom.{n_effective}"), str(cpath), str(data / f"opath.{n_effective}"),
                        str(data / "geometry.txt"), regionCount=6, shortestLengthFile=str(shortest))

    print("[4/5] Training and sampling original PUTS components...", flush=True)
    # Same three-query allocation used by the supplied Beijing runner, rescaled
    # to the requested total epsilon without changing PUTS query definitions.
    trip = SrcDestRegionsSample(db, .33 * a.epsilon)
    transition = RoadTransitionMatrix(db, .34 * a.epsilon)
    speed = RoadSpeedSample(db, 5, 0, 7 * .0003, .33 * a.epsilon)
    original_init = ts.RoadSequenceGenerator.__init__
    original_precompute = ts.RoadSequenceGenerator.precomputeMarkov
    requested = int(a.n_gen * 3)  # public overdraw; retain first drawable slots.
    def requested_slots(self, sd, tm, global_db, safeValue=1.5, MulProcesses=False):
        self.desiredNumberOfTrajectories = requested
        self.usedRoad = global_db.getCpathDatabase().getusedRoad(); self.roadErrorCount = 0
        self.unAdjaceRoadTransitionMatrix = tm.getunAdjaceRoadTransitionMatrix()
        self.maxSteps = global_db.getCpathDatabase().getMaxRoadSequenceLength()
        self.transitionProbsMatrixs = self.precomputeMarkov(tm.getnoisyRoadTransitionProbsMatrix(), self.maxSteps)
        self.srcDestLengthSampler = ts.SrcDestLengthSample(global_db, self.transitionProbsMatrixs, safeValue)
        self.adjacRoadDic = global_db.getRoadGeometry().getAdjacentRoad()
        self.syntheticRoadDB = self.generatedSyntheticRoadSequence(sd)
    ts.RoadSequenceGenerator.__init__ = requested_slots
    def out_of_core_precompute(self, one_step_matrix, max_step):
        """Exact PUTS recurrence with a disk-backed tensor, not a sparse approximation."""
        road_count = len(self.usedRoad)
        backing = data / f"puts_markov_powers_{n_effective}_{road_count}_{max_step}.dat"
        powers = np.memmap(backing, dtype=np.float64, mode="w+",
                           shape=(max_step + 1, road_count, road_count))
        powers[0] = one_step_matrix; powers[1] = one_step_matrix
        for step in range(2, max_step + 1):
            powers[step] = np.dot(powers[step - 1], one_step_matrix)
            if step % 10 == 0 or step == max_step:
                powers.flush()
                print(f"      exact out-of-core Markov power {step}/{max_step}", flush=True)
        return powers
    ts.RoadSequenceGenerator.precomputeMarkov = out_of_core_precompute
    try:
        sequences = ts.RoadSequenceGenerator(trip, transition, db, float(a.safe_value), False).getsyntheticRoadDB()
    finally:
        ts.RoadSequenceGenerator.__init__ = original_init
        ts.RoadSequenceGenerator.precomputeMarkov = original_precompute
    raw = ts.TrajectoryPointGenerator(speed, db, sequences, False).getsyntheticTrajectoryDB()
    # Original PUTS coordinates are (lon, lat); retain a public fixed number of
    # drawable synthetic records, then convert to repository convention (lat, lon).
    drawable = [np.asarray([[p[1], p[0]] for p in line], dtype=float) for line in raw if len(line) >= 2]
    if len(drawable) < a.n_gen:
        raise RuntimeError(f"PUTS yielded only {len(drawable)} drawable records; requested {a.n_gen}")
    release = drawable[:a.n_gen]
    print("[5/5] Writing a count-matched original-PUTS release...", flush=True)
    with (a.out / "puts_original_same_train.pkl").open("wb") as handle:
        pickle.dump(release, handle, pickle.HIGHEST_PROTOCOL)
    (a.out / "puts_original_same_train.json").write_text(
        __import__("json").dumps({"method": "original PUTS", "n_train_requested": a.n_train, "n_train_effective": n_effective, "n_gen": a.n_gen,
        "n_roads_puts_selected": len(used), "epsilon": a.epsilon,
        "allocation": [0.33*a.epsilon, .34*a.epsilon, .33*a.epsilon],
        "input_conversion": conversion,
        "paper_faithful_support": bool(conversion["selected_roads"] == conversion["all_matched_roads"]),
        "reduced_support_diagnostic": bool(conversion["selected_roads"] < conversion["all_matched_roads"]),
        "safe_value": float(a.safe_value),
        "note": "Original PUTS synthesis code; raw trajectories are converted to PUTS road states using public OSM. Only the public output slot count and disk backing for the exact dense recurrence are operational overrides."}, indent=2), encoding="utf-8")
    print(f"Done: {a.out / 'puts_original_same_train.pkl'}", flush=True)


if __name__ == "__main__":
    main()
