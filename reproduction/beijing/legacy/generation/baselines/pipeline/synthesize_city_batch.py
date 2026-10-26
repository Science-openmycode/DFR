from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

PUBLIC_RELEASE = Path(__file__).resolve().parents[1]
if str(PUBLIC_RELEASE) not in sys.path:
    sys.path.insert(0, str(PUBLIC_RELEASE))

from public_utils import (
    PUBLIC_ROOT,
    add_project_paths,
    bbox_dict,
    load_osm_ways,
    load_trajectories,
    parse_bbox,
    filter_osm_ways_by_bbox,
    save_trajectories_pkl,
    thin_osm_ways_public,
    write_json,
)
from pipeline.synthesize_dataset import synthesize_dp_gsrt


BASELINE_TAGS = {
    "SPRT-native": "sprt_native",
    "SPRT-OSM": "sprt_osm",
    "PrivTrace-native": "privtrace_native",
    "PrivTrace-OSM": "privtrace_osm",
    "DPTrajPM-native": "dptrajpm_native",
    "DPTrajPM-OSM": "dptrajpm_osm",
    "DPStd-native": "dpstd_native",
    "DPStd-OSM": "dpstd_osm",
}


def log(message: str) -> None:
    print(f"[city-batch] {time.strftime('%H:%M:%S')} {message}", flush=True)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Generate all reproduced baselines for one city with shared router setup.")
    p.add_argument("--data", required=True)
    p.add_argument("--city-tag", required=True)
    p.add_argument("--osm-cache", required=True)
    p.add_argument("--bbox", nargs=4, type=float, required=True, metavar=("LAT_MIN", "LAT_MAX", "LON_MIN", "LON_MAX"))
    p.add_argument("--epsilon", type=float, default=1.2)
    p.add_argument("--epsilon-base", type=float, default=1.0)
    p.add_argument("--epsilon-route", type=float, default=0.2)
    p.add_argument("--n-train", type=int, default=None)
    p.add_argument("--n-gen", type=int, required=True)
    p.add_argument("--public-slot-count", type=int, required=True)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out-dir", default=str(PUBLIC_ROOT / "outputs" / "synthetic_releases"))
    p.add_argument("--skip-baselines", action="store_true")
    p.add_argument("--skip-dp-gsrt", action="store_true")
    p.add_argument("--max-attempts-per-slot", type=int, default=40)
    p.add_argument("--max-candidates", type=int, default=32)
    p.add_argument(
        "--candidate-search-max-visits", type=int, default=25_000,
        help="public fixed graph-search expansion cap used by the bounded MTR decoder",
    )
    p.add_argument("--candidate-mode", default="hybrid_anchor")
    p.add_argument("--anchor-count", type=int, default=40)
    p.add_argument("--osm-max-ways", type=int, default=0)
    return p


def main() -> None:
    args = build_parser().parse_args()
    t0 = time.time()
    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = Path.cwd() / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    bbox = parse_bbox(args.bbox)

    log(f"loading {args.data}")
    real = load_trajectories(args.data, limit=args.n_train)
    if not real:
        raise RuntimeError("no trajectories loaded")
    n_train = len(real)
    n_gen = int(args.n_gen)
    log(f"loaded {n_train:,} trajectories; loading OSM {args.osm_cache}")
    osm_ways_raw = load_osm_ways(args.osm_cache)
    osm_ways = filter_osm_ways_by_bbox(osm_ways_raw, bbox)
    log(f"loaded {len(osm_ways_raw):,} OSM ways; kept {len(osm_ways):,} near bbox")
    if int(args.osm_max_ways) > 0 and len(osm_ways) > int(args.osm_max_ways):
        before = len(osm_ways)
        osm_ways = thin_osm_ways_public(osm_ways, bbox, int(args.osm_max_ways))
        log(f"public OSM thinning: kept {len(osm_ways):,}/{before:,} ways")

    outputs: dict[str, str] = {}
    if not args.skip_baselines:
        add_project_paths()
        import eval_layered_framework as layered
        from osm_dbscan import osm_centers_from_ways

        old_state = {
            "EPS": layered.EPS,
            "N_TRAIN": layered.N_TRAIN,
            "N_GEN": layered.N_GEN,
            "BBOX": layered.BBOX,
            "BBOX_DICT": layered.BBOX_DICT,
        }
        try:
            layered.EPS = float(args.epsilon)
            layered.N_TRAIN = n_train
            layered.N_GEN = n_gen
            layered.BBOX = bbox
            layered.BBOX_DICT = bbox_dict(bbox)
            log("building shared OSM centers")
            centers = osm_centers_from_ways(osm_ways, bbox, layered.K_OSM)
            log("building shared two-stage road router")
            road_pts, path_cache, center_dists = layered.build_twostage_router(osm_ways, centers)
            log("preparing reproduced baseline generators once")
            methods = layered.generate_methods(real[:n_train], osm_ways, centers, road_pts, path_cache, center_dists)
            np.random.seed(int(args.seed))
            for display, suffix in BASELINE_TAGS.items():
                if display not in methods:
                    log(f"skip missing method {display}")
                    continue
                tag = f"{args.city_tag}_{suffix}_full"
                log(f"generating {display} -> {tag}")
                generated = methods[display]()
                syn = generated[0] if isinstance(generated, tuple) else generated
                path = save_trajectories_pkl(out_dir / f"{tag}.pkl", syn)
                outputs[tag] = str(path.resolve())
                write_json(
                    out_dir / f"{tag}_protocol.json",
                    {
                        "command_role": "synthesize_city_batch",
                        "method": display,
                        "data": args.data,
                        "city_tag": args.city_tag,
                        "epsilon": float(args.epsilon),
                        "n_train": n_train,
                        "n_gen": len(syn),
                        "seed": int(args.seed),
                        "bbox": bbox,
                        "osm_cache": args.osm_cache,
                        "osm_max_ways": int(args.osm_max_ways),
                        "output": str(path.resolve()),
                    },
                )
        finally:
            layered.EPS = old_state["EPS"]
            layered.N_TRAIN = old_state["N_TRAIN"]
            layered.N_GEN = old_state["N_GEN"]
            layered.BBOX = old_state["BBOX"]
            layered.BBOX_DICT = old_state["BBOX_DICT"]

    if not args.skip_dp_gsrt:
        ns = argparse.Namespace(
            epsilon_base=float(args.epsilon_base),
            epsilon_route=float(args.epsilon_route),
            n_train=n_train,
            n_gen=n_gen,
            public_slot_count=int(args.public_slot_count),
            strict_fixed_slots=True,
            max_attempts_per_slot=int(args.max_attempts_per_slot),
            max_candidates=int(args.max_candidates),
            candidate_search_max_visits=int(args.candidate_search_max_visits),
            candidate_mode=str(args.candidate_mode),
            anchor_count=int(args.anchor_count),
            keep_all_public_components=False,
            seed=int(args.seed),
            reproducible_dp_noise=False,
            allow_uncommitted_dp_config=False,
            bbox=bbox,
        )
        for public_only, tag in [(True, f"{args.city_tag}_mtr_public_only_full"), (False, f"{args.city_tag}_dp_gsrt_full")]:
            log(f"generating {'MTR-public-only' if public_only else 'MTR / DP-GSRT'}")
            syn, diag = synthesize_dp_gsrt(ns, real, osm_ways, public_only=public_only)
            path = save_trajectories_pkl(out_dir / f"{tag}.pkl", syn)
            outputs[tag] = str(path.resolve())
            diag.update(
                {
                    "command_role": "synthesize_city_batch",
                    "data": args.data,
                    "city_tag": args.city_tag,
                    "bbox": bbox,
                    "osm_cache": args.osm_cache,
                    "osm_max_ways": int(args.osm_max_ways),
                    "output": str(path.resolve()),
                }
            )
            write_json(out_dir / f"{tag}_protocol.json", diag)

    manifest = {
        "command_role": "synthesize_city_batch",
        "data": args.data,
        "city_tag": args.city_tag,
        "n_train": n_train,
        "n_gen_requested": n_gen,
        "runtime_sec": float(time.time() - t0),
        "outputs": outputs,
    }
    write_json(out_dir / f"{args.city_tag}_batch_manifest.json", manifest)
    log(f"completed in {manifest['runtime_sec']:.1f}s")


if __name__ == "__main__":
    main()
