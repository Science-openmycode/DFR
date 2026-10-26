"""Prepare one Beijing subset in the input format consumed by upstream PUTS.

PUTS starts *after* map matching.  Its ``cpath``, ``opath`` and ``pgeom``
files therefore must describe the same matched observations, rather than a
pointwise snap plus an invented shortest-path bridge.  This utility uses the
public FMM matcher to create those three files, then reindexes exactly the
roads used by FMM.  It changes neither the PUTS mechanism nor its parameters.
"""
from __future__ import annotations

import argparse
import csv
import json
import pickle
import shutil
import subprocess
import os
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
from pyproj import Transformer
from shapely import wkt

csv.field_size_limit(sys.maxsize)


ROOT = Path(__file__).resolve().parents[2]
FMM_ROOT = ROOT / "third_party" / "fmm-v0.1.1" / "cyang-kth-fmm-344fb8c"
FMM = FMM_ROOT / "build" / "Release" / "fmm.exe"
UBODT = FMM_ROOT / "build" / "Release" / "ubodt_gen.exe"


def run(command: list[str], cwd: Path) -> None:
    print("[exec]", " ".join(str(x) for x in command), flush=True)
    runtime = "C:/Users/ASUS/.conda/envs/LSTM_TrajGAN/Library/bin"
    env = dict(os.environ); env["PATH"] = runtime + ";" + env.get("PATH", "")
    subprocess.run(command, cwd=cwd, check=True, env=env)


def parse_ids(value: str) -> list[int]:
    return [int(x) for x in (value or "").split(",") if x.strip().lstrip("-").isdigit()]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--real", required=True, type=Path, help="pickle trajectories in [lat, lon]")
    ap.add_argument("--network", required=True, type=Path, help="directed FMM OSM shapefile in EPSG:32650")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--n", type=int, default=1000)
    ap.add_argument("--max-accepted", type=int, default=None,
                    help="publicly fixed release/training size after FMM eligibility; omit to retain all matches")
    ap.add_argument("--radius-m", type=float, default=300.0)
    ap.add_argument("--gps-error-m", type=float, default=50.0)
    ap.add_argument("--candidates", type=int, default=8)
    ap.add_argument("--ubodt-delta-m", type=float, default=3000.0)
    ap.add_argument("--overwrite", action="store_true")
    a = ap.parse_args()
    if not FMM.exists() or not UBODT.exists():
        raise SystemExit("FMM executables are unavailable under public_release/third_party/fmm-v0.1.1")
    out = a.out.resolve()
    if out.exists() and any(out.iterdir()) and not a.overwrite:
        raise SystemExit(f"{out} is nonempty; pass --overwrite")
    if out.exists() and a.overwrite:
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    with a.real.open("rb") as f:
        raw = [np.asarray(t, dtype=float) for t in pickle.load(f)[: a.n]]
    raw = [t for t in raw if len(t) >= 2]
    to_utm = Transformer.from_crs("EPSG:4326", "EPSG:32650", always_xy=True)
    to_wgs = Transformer.from_crs("EPSG:32650", "EPSG:4326", always_xy=True)
    # The bundled Windows FMM binaries crash on non-ASCII paths.  The project
    # itself may live in a Chinese-named directory, so invoke them from a
    # deterministic ASCII staging area and copy only their plain-text results.
    stage = Path("C:/ara_puts_fmm_stage") / ("subset_" + str(abs(hash(str(out))) % 10**9))
    if stage.exists(): shutil.rmtree(stage)
    stage.mkdir(parents=True)
    stage_network = stage / "network.shp"
    for binary in (FMM, UBODT, FMM.parent / "FMMLIB.dll"):
        shutil.copy2(binary, stage / binary.name)
    # These are runtime dependencies of the vendored Windows FMM build.  Keep
    # the lookup explicit so a missing dependency fails with a useful message
    # rather than Windows' opaque 0xc0000135 loader status.
    fmm_runtime = Path("C:/Users/ASUS/.conda/envs/LSTM_TrajGAN/Library/bin")
    for name in ("gdal204.dll", "boost_serialization.dll"):
        source = fmm_runtime / name
        if not source.exists():
            raise SystemExit(f"FMM runtime dependency missing: {source}")
        shutil.copy2(source, stage / name)
    stage_fmm, stage_ubodt = stage / FMM.name, stage / UBODT.name
    for companion in a.network.parent.glob(a.network.stem + ".*"):
        shutil.copy2(companion, stage / ("network" + companion.suffix))
    gps = stage / "gps.csv"
    with gps.open("w", newline="", encoding="utf-8") as f:
        # CSVTrajectoryReader is less fragile than the point-stream reader and
        # makes exactly one FMM record per raw trajectory.  FMM's trajectory
        # CSV format is semicolon-separated and stores a WKT LINESTRING.
        writer = csv.writer(f, delimiter=";"); writer.writerow(["id", "geom"])
        for rid, traj in enumerate(raw):
            coords = [to_utm.transform(float(lon), float(lat)) for lat, lon in traj]
            writer.writerow([rid, "LINESTRING(" + ",".join(f"{x:.3f} {y:.3f}" for x, y in coords) + ")"])
    print(f"[1/4] wrote {len(raw)} raw trajectories for FMM", flush=True)
    ubodt = stage / "ubodt.txt"
    run([str(stage_ubodt), "--network", str(stage_network), "--network_id", "id", "--source", "source", "--target", "target", "--delta", str(a.ubodt_delta_m), "--output", str(ubodt), "--use_omp"], stage)
    matched = stage / "fmm_matches.csv"
    run([str(stage_fmm), "--ubodt", str(ubodt), "--network", str(stage_network), "--network_id", "id", "--source", "source", "--target", "target", "--gps", str(gps), "--gps_id", "id", "--gps_geom", "geom", "--candidates", str(a.candidates), "--radius", str(a.radius_m), "--error", str(a.gps_error_m), "--output", str(matched), "--output_fields", "opath,cpath,pgeom,mgeom", "--use_omp"], stage)
    shutil.copy2(matched, out / "fmm_matches.csv")
    shutil.copy2(ubodt, out / "ubodt.txt")
    print("[2/4] parsing FMM's connected paths and matched points", flush=True)
    records: list[tuple[list[int], list[int], list[tuple[float, float]], int]] = []
    with matched.open("r", newline="", encoding="utf-8", errors="ignore") as f:
        for row in csv.DictReader(f, delimiter=";"):
            cpath, opath = parse_ids(row.get("cpath", "")), parse_ids(row.get("opath", ""))
            try:
                points = list(wkt.loads(row.get("pgeom", "")).coords)
            except Exception:
                points = []
            if len(cpath) >= 2 and len(opath) == len(points) >= 2:
                records.append((cpath, opath, [(float(x), float(y)) for x, y in points], int(row["id"])))
    if not records:
        raise RuntimeError("FMM produced no valid matched trajectories")
    fmm_valid_before_cap = len(records)
    if a.max_accepted is not None:
        if len(records) < a.max_accepted:
            raise RuntimeError(f"FMM yielded {len(records)} valid records, below requested --max-accepted={a.max_accepted}")
        records = records[:a.max_accepted]
    used = sorted({edge for cpath, _, _, _ in records for edge in cpath})
    old_to_new = {old: new for new, old in enumerate(used)}
    gdf = gpd.read_file(a.network).set_index("id")
    missing = [edge for edge in used if edge not in gdf.index]
    if missing:
        raise RuntimeError(f"FMM returned {len(missing)} edge ids absent from the network")
    data = out / "puts_input"; data.mkdir(exist_ok=True)
    n = len(records)
    (data / f"cpath.{n}").write_text("\n".join(",".join(str(old_to_new[e]) for e in cpath) for cpath, _, _, _ in records) + "\n", encoding="utf-8")
    (data / f"opath.{n}").write_text("\n".join(",".join(str(old_to_new[e]) for e in opath) for _, opath, _, _ in records) + "\n", encoding="utf-8")
    def lonlat(x: float, y: float) -> tuple[float, float]:
        return to_wgs.transform(x, y)
    (data / f"pgeom.{n}").write_text("\n".join(
        ";".join(f"{lonlat(x, y)[0]:.8f},{lonlat(x, y)[1]:.8f}" for x, y in points)
        for _, _, points, _ in records) + "\n", encoding="utf-8")
    geoms = []
    for edge in used:
        coords = [lonlat(float(x), float(y)) for x, y in gdf.loc[edge].geometry.coords]
        geoms.append("LINESTRING (" + ",".join(f"{x:.8f} {y:.8f}" for x, y in coords) + ")")
    (data / "geometry.txt").write_text("\n".join(geoms) + "\n", encoding="utf-8")
    accepted = [raw[source] for _, _, _, source in records]
    with (out / "accepted_raw.pkl").open("wb") as f:
        pickle.dump(accepted, f, pickle.HIGHEST_PROTOCOL)
    (out / "matched_source_indices.json").write_text(json.dumps([source for _, _, _, source in records]), encoding="utf-8")
    manifest = {"status": "prepared", "raw_requested": a.n, "fmm_valid_before_cap": fmm_valid_before_cap, "selected_for_puts": n, "matched_road_support": len(used), "input_files": {"cpath": f"cpath.{n}", "opath": f"opath.{n}", "pgeom": f"pgeom.{n}"}, "fmm": {"network": str(a.network), "candidates": a.candidates, "radius_m": a.radius_m, "gps_error_m": a.gps_error_m, "ubodt_delta_m": a.ubodt_delta_m}, "claim_boundary": "FMM is a transparent map-matching implementation of the prerequisite stated by PUTS; the subsequent PUTS mechanism is invoked unchanged."}
    (out / "prepare_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"[3/4] wrote original PUTS files: n={n}, R={len(used)}", flush=True)
    print(f"[4/4] done: {out}", flush=True)


if __name__ == "__main__":
    main()
