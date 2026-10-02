from __future__ import annotations

import argparse
import hashlib
import json
import os
import pickle
import subprocess
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
    save_trajectories_npz,
    save_trajectories_pkl,
    write_json,
)


BASELINE_METHODS = {
    "sprt-native": ("sprt", "native", "SPRT-native"),
    "sprt-osm": ("sprt", "osm", "SPRT-OSM"),
    "sprt-pra": ("sprt", "pra", "SPRT-OSM"),
    "privtrace-native": ("privtrace", "native", "PrivTrace-native"),
    "privtrace-osm": ("privtrace", "osm", "PrivTrace-OSM"),
    "privtrace-pra": ("privtrace", "pra", "PrivTrace-OSM"),
    "dptrajpm-native": ("dptrajpm", "native", "DPTrajPM-native"),
    "dptrajpm-osm": ("dptrajpm", "osm", "DPTrajPM-OSM"),
    "dptrajpm-pra": ("dptrajpm", "pra", "DPTrajPM-OSM"),
    "dpstd-native": ("dpstd", "native", "DPStd-native"),
    "dpstd-osm": ("dpstd", "osm", "DPStd-OSM"),
    "dpstd-pra": ("dpstd", "pra", "DPStd-OSM"),
}

OFFICIAL_BASELINE_METHODS = {"dptrajpm-official", "privtrace-official", "sprt-paper-structured"}

METHOD_CHOICES = sorted([*BASELINE_METHODS.keys(), *OFFICIAL_BASELINE_METHODS])


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def log(message: str) -> None:
    print(f"[synthesize] {time.strftime('%H:%M:%S')} {message}", flush=True)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Generate a full-size synthetic trajectory dataset. This script only "
            "synthesizes data; downstream task evaluation is handled by "
            "evaluate_downstream.py."
        )
    )
    p.add_argument("--method", required=True, choices=METHOD_CHOICES)
    p.add_argument("--data", default="geolife", help="geolife, oldenburg, porto, or path to .pkl/.npz/.npy/.json")
    p.add_argument("--osm-cache", default="data/osm/osm_cache_beijing.pkl")
    p.add_argument("--bbox", nargs=4, type=float, metavar=("LAT_MIN", "LAT_MAX", "LON_MIN", "LON_MAX"))
    p.add_argument("--epsilon", type=float, default=1.0, help="baseline privacy budget")
    p.add_argument("--n-train", type=int, default=None, help="input trajectories used for fitting; default is full loaded corpus")
    p.add_argument("--n-gen", type=int, default=None, help="synthetic trajectories to generate; default is full loaded corpus size")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out-dir", default=str(PUBLIC_ROOT / "outputs" / "synthetic_releases"))
    p.add_argument("--tag", default=None, help="optional output filename tag")
    p.add_argument("--format", choices=["npz", "pkl", "both"], default="both")
    p.add_argument("--protocol-json", default=None)
    p.add_argument(
        "--official-replicate",
        type=int,
        default=0,
        help="official-code replicate index for methods such as dptrajpm-official",
    )
    p.add_argument(
        "--dptrajpm-official-root",
        default=str(PUBLIC_ROOT / "check" / "official_repos" / "dptrajpm" / "extracted" / "DP_PrefixTreeMarkov-2" / "DP_PrefixTreeMarkov"),
        help="official DPTraj-PM C++ repository root for dptrajpm-official",
    )
    p.add_argument(
        "--dptrajpm-timeout",
        type=int,
        default=2400,
        help="seconds before stopping the official DPTraj-PM C++ entry point on converted datasets",
    )
    p.add_argument(
        "--privtrace-official-root",
        default=str(PUBLIC_ROOT / "check" / "official_repos" / "privtrace" / "PrivTrace-main"),
        help="official PrivTrace repository root for privtrace-official",
    )
    p.add_argument(
        "--privtrace-dataset-name",
        default=None,
        help="dataset filename under official PrivTrace datasets/ for privtrace-official",
    )
    p.add_argument(
        "--privtrace-timeout",
        type=int,
        default=900,
        help="seconds before stopping the official PrivTrace entry point",
    )
    p.add_argument(
        "--privtrace-max-points-per-traj",
        type=int,
        default=None,
        help=(
            "optional deterministic within-trajectory downsampling before running "
            "official PrivTrace; leave unset for full point sequences"
        ),
    )
    p.add_argument(
        "--privtrace-total-epsilon",
        type=float,
        default=None,
        help="override official PrivTrace --total_epsilon; defaults to --epsilon if omitted",
    )
    p.add_argument(
        "--privtrace-epsilon-partition",
        default=None,
        help="comma-separated official PrivTrace epsilon partition, e.g. 0.2,0.52,0.28",
    )
    p.add_argument(
        "--privtrace-level1-parameter",
        type=float,
        default=None,
        help="optional official PrivTrace --level1_parameter; record it for a frozen reproduction",
    )
    p.add_argument(
        "--privtrace-level2-parameter",
        type=float,
        default=None,
        help="optional official PrivTrace --subdividing_inner_parameter; record it for a frozen reproduction",
    )
    return p


def _output_paths(out_dir: str | Path, method: str, tag: str | None, fmt: str) -> dict[str, Path]:
    root = Path(out_dir)
    if not root.is_absolute():
        root = Path.cwd() / root
    root.mkdir(parents=True, exist_ok=True)
    stem = tag or method
    paths: dict[str, Path] = {}
    if fmt in {"npz", "both"}:
        paths["npz"] = root / f"{stem}.npz"
    if fmt in {"pkl", "both"}:
        paths["pkl"] = root / f"{stem}.pkl"
    return paths


def _save_outputs(paths: dict[str, Path], trajs: list[np.ndarray]) -> dict[str, str]:
    written: dict[str, str] = {}
    if "npz" in paths:
        log(f"saving NPZ -> {paths['npz']}")
        written["npz"] = str(save_trajectories_npz(paths["npz"], trajs).resolve())
    if "pkl" in paths:
        log(f"saving PKL -> {paths['pkl']}")
        written["pkl"] = str(save_trajectories_pkl(paths["pkl"], trajs).resolve())
    return written


def synthesize_dptrajpm_official(args: argparse.Namespace, real: list[np.ndarray] | None = None) -> tuple[list[np.ndarray], dict]:
    if real is not None:
        from check.run_dptrajpm_official_on_dataset import (
            copy_official_root,
            export_releases,
            run_official,
            write_official_input,
        )
        from check.run_dptrajpm_official import parse_all_results, read_official_parameters

        n_train = int(args.n_train or len(real))
        n_gen = int(args.n_gen or len(real))
        if n_train > len(real):
            raise RuntimeError(f"n_train={n_train} exceeds loaded trajectories={len(real)}")
        if n_gen != n_train:
            log(
                "DPTraj-PM official C++ generates the official program's input-size release; "
                f"requested n_gen={n_gen:,}, using n_train={n_train:,} as the official output count"
            )
        official_root = Path(args.dptrajpm_official_root)
        if not official_root.is_absolute():
            official_root = (Path.cwd() / official_root).resolve()
        if not (official_root / "bin" / "Debug" / "DP-PrefixMarkov.exe").exists():
            raise RuntimeError(f"official DPTraj-PM executable not found under {official_root}")
        tag = args.tag or "dptrajpm_official"
        work_root = (Path(args.out_dir) / "_official_runs" / f"{tag}_work").resolve()
        release_dir = (Path(args.out_dir) / "_official_runs" / f"{tag}_releases").resolve()
        log(f"DPTraj-PM official: copying official C++ root to {work_root}")
        copy_official_root(official_root, work_root)
        log(f"DPTraj-PM official: writing {n_train:,} converted trajectories in official lon,lat format")
        input_summary = write_official_input(work_root, real[:n_train], parse_bbox(args.bbox))
        if input_summary["written_trajectories"] <= 0:
            raise RuntimeError("DPTraj-PM official input conversion wrote no usable trajectories")
        log("DPTraj-PM official: running official generator/evaluator")
        run_info = run_official(work_root, timeout=int(args.dptrajpm_timeout))
        if run_info["returncode"] != 0:
            raise RuntimeError(
                "official DPTraj-PM failed with return code "
                f"{run_info['returncode']}\nSTDOUT tail:\n{run_info['stdout_tail']}\nSTDERR tail:\n{run_info['stderr_tail']}"
            )
        metrics = parse_all_results(work_root)
        manifest = export_releases(work_root, release_dir, tag)
        releases = manifest.get("releases", [])
        rep = int(args.official_replicate)
        if rep < 0 or rep >= len(releases):
            raise RuntimeError(f"--official-replicate {rep} is out of range; official run produced {len(releases)} releases")
        rel = releases[rep]
        with Path(rel["pkl"]).open("rb") as f:
            trajs = [np.asarray(t, dtype=float) for t in pickle.load(f)]
        diag = {
            "algorithm": "DPTraj-PM-official",
            "display_name": "DPTraj-PM official C++ release",
            "family": "official_code_entrypoint_baseline",
            "privacy_budget": float(args.epsilon),
            "official_root": str(official_root),
            "official_run_root": str(work_root),
            "official_replicate": rep,
            "n_train_used": n_train,
            "n_gen_requested": n_gen,
            "input_summary": input_summary,
            "official_parameters": read_official_parameters(work_root),
            "official_metrics": metrics,
            "export_manifest": manifest,
            "source_pkl": rel.get("pkl"),
            "source_txt": rel.get("source_txt"),
            "official_header_count": rel.get("official_header_count"),
            "summary": rel.get("summary"),
            "coordinate_conversion": "public lat,lon -> official lon,lat -> public lat,lon",
            "certification_status": (
                "official DPTraj-PM C++ entry point on converted public-protocol data; "
                "not original-paper table certification unless the official bundled data is used"
            ),
        }
        return trajs, diag

    manifest_path = PUBLIC_ROOT / "check" / "official_outputs" / "dptrajpm" / "manifest.json"
    if not manifest_path.exists():
        raise RuntimeError(
            "DPTraj-PM official release manifest is missing. Run "
            "`python public_release\\check\\run_dptrajpm_official.py --mode run-and-parse --timeout 900` "
            "and `python public_release\\check\\export_dptrajpm_official_releases.py` first."
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    releases = manifest.get("releases", [])
    rep = int(args.official_replicate)
    if rep < 0 or rep >= len(releases):
        raise RuntimeError(f"--official-replicate {rep} is out of range; manifest has {len(releases)} releases")
    rel = releases[rep]
    pkl_path = Path(rel["pkl"])
    with pkl_path.open("rb") as f:
        trajs = [np.asarray(t, dtype=float) for t in pickle.load(f)]
    diag = {
        "algorithm": "DPTraj-PM-official",
        "display_name": "DPTraj-PM official C++ release",
        "family": "official_code_certified_baseline",
        "official_manifest": str(manifest_path),
        "official_replicate": rep,
        "source_pkl": str(pkl_path),
        "source_txt": rel.get("source_txt"),
        "official_header_count": rel.get("official_header_count"),
        "summary": rel.get("summary"),
        "certification_status": "official package output converted without dropping single-point trajectories",
    }
    return trajs, diag


def _write_privtrace_official_dataset(path: Path, trajs: list[np.ndarray], max_points_per_traj: int | None) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    points_total = 0
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for tr in trajs:
            arr = np.asarray(tr, dtype=float)
            if arr.ndim != 2 or arr.shape[1] < 2 or len(arr) < 2:
                continue
            if max_points_per_traj is not None and len(arr) > int(max_points_per_traj):
                idx = np.linspace(0, len(arr) - 1, int(max_points_per_traj)).round().astype(int)
                arr = arr[idx]
            f.write(f"#{written}:\n")
            # Official PrivTrace format is x,y. Public geographic trajectories are lat,lon.
            pts = [f"{float(lon):.6f},{float(lat):.6f}" for lat, lon in arr[:, :2]]
            f.write(">0:" + ";".join(pts) + ";\n")
            written += 1
            points_total += len(pts)
    return {"written_trajectories": written, "written_points": points_total}


def _read_privtrace_official_generated(path: Path) -> list[np.ndarray]:
    trajs: list[np.ndarray] = []
    pending = False
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if line.startswith("#"):
                pending = True
                continue
            if pending and line.startswith(">"):
                body = line.split(":", 1)[1] if ":" in line else line
                pts = []
                for token in body.split(";"):
                    token = token.strip()
                    if not token or "," not in token:
                        continue
                    x_s, y_s = token.split(",", 1)
                    try:
                        lon, lat = float(x_s), float(y_s)
                    except ValueError:
                        continue
                    pts.append([lat, lon])
                if len(pts) >= 2:
                    trajs.append(np.asarray(pts, dtype=float))
                pending = False
    return trajs


def synthesize_privtrace_official(args: argparse.Namespace, real: list[np.ndarray]) -> tuple[list[np.ndarray], dict]:
    root = Path(args.privtrace_official_root)
    if not root.is_absolute():
        root = Path.cwd() / root
    root = root.resolve()
    main_py = root / "main.py"
    if not main_py.exists():
        raise RuntimeError(f"official PrivTrace main.py not found: {main_py}")
    shim_dir = PUBLIC_ROOT / "check" / "official_wrappers" / "privtrace_shims"
    shim_dir.mkdir(parents=True, exist_ok=True)
    (shim_dir / "fcntl.py").write_text(
        "LOCK_EX = 2\nLOCK_UN = 8\n\ndef flock(*args, **kwargs):\n    return None\n",
        encoding="utf-8",
    )
    (shim_dir / "sitecustomize.py").write_text(
        "import os as _os\n"
        "import numpy as _np\n"
        "if not hasattr(_np, 'int'):\n"
        "    _np.int = int\n"
        "if not hasattr(_np, 'float'):\n"
        "    _np.float = float\n"
        "_seed = _os.environ.get('PRIVTRACE_NUMPY_SEED')\n"
        "if _seed is not None:\n"
        "    _np.random.seed(int(_seed))\n",
        encoding="utf-8",
    )
    dataset_name = args.privtrace_dataset_name or f"codex_{args.tag or 'privtrace_official'}.dat"
    dataset_path = root / "datasets" / dataset_name
    n_train = int(args.n_train or len(real))
    n_gen = int(args.n_gen or len(real))
    if n_train > len(real):
        raise RuntimeError(f"n_train={n_train} exceeds loaded trajectories={len(real)}")
    log(f"PrivTrace official: writing official-format dataset {dataset_name} from {n_train:,} trajectories")
    export_summary = _write_privtrace_official_dataset(
        dataset_path,
        real[:n_train],
        max_points_per_traj=args.privtrace_max_points_per_traj,
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = str(shim_dir) + os.pathsep + env.get("PYTHONPATH", "")
    env["PRIVTRACE_NUMPY_SEED"] = str(int(args.seed))
    cmd = [
        sys.executable,
        "main.py",
        f"--dataset_file_name={dataset_name}",
        f"--trajectory_number_to_generate={n_gen}",
        f"--total_epsilon={float(args.privtrace_total_epsilon if args.privtrace_total_epsilon is not None else args.epsilon)}",
    ]
    if args.privtrace_epsilon_partition:
        cmd.append(f"--epsilon_partition={args.privtrace_epsilon_partition}")
    if args.privtrace_level1_parameter is not None:
        cmd.append(f"--level1_parameter={float(args.privtrace_level1_parameter)}")
    if args.privtrace_level2_parameter is not None:
        cmd.append(f"--subdividing_inner_parameter={float(args.privtrace_level2_parameter)}")
    log(f"PrivTrace official: running official entry point for {n_gen:,} synthetic trajectories")
    timeout_s = int(args.privtrace_timeout)
    start = time.time()
    proc = subprocess.Popen(
        cmd,
        cwd=str(root),
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    while proc.poll() is None:
        elapsed = time.time() - start
        if elapsed > timeout_s:
            proc.kill()
            stdout, stderr = proc.communicate()
            raise RuntimeError(
                "official PrivTrace timed out after "
                f"{timeout_s}s\nSTDOUT tail:\n{stdout[-2000:]}\nSTDERR tail:\n{stderr[-2000:]}"
            )
        log(f"PrivTrace official: still running after {elapsed:.0f}s")
        time.sleep(60)
    stdout, stderr = proc.communicate()
    output_file = root / "generated_tras.txt"
    if proc.returncode != 0:
        raise RuntimeError(
            "official PrivTrace failed with return code "
            f"{proc.returncode}\nSTDOUT tail:\n{stdout[-2000:]}\nSTDERR tail:\n{stderr[-2000:]}"
        )
    syn = _read_privtrace_official_generated(output_file)
    diag = {
        "algorithm": "PrivTrace-official",
        "display_name": "PrivTrace official Python release",
        "family": "official_code_entrypoint_baseline",
        "privacy_budget": float(args.epsilon),
        "official_root": str(root),
        "official_dataset": str(dataset_path),
        "official_output": str(output_file),
        "export_summary": export_summary,
        "n_train_used": n_train,
        "n_gen_requested": n_gen,
        "generated_after_parse": len(syn),
        "max_points_per_traj": args.privtrace_max_points_per_traj,
        "total_epsilon": float(args.privtrace_total_epsilon if args.privtrace_total_epsilon is not None else args.epsilon),
        "epsilon_partition": args.privtrace_epsilon_partition or "official-default",
        "level1_parameter": args.privtrace_level1_parameter,
        "level2_parameter": args.privtrace_level2_parameter,
        "seed": int(args.seed),
        "command": cmd,
        "stdout_tail": stdout[-2000:],
        "stderr_tail": stderr[-2000:],
        "certification_status": (
            "official PrivTrace entry point on converted public-protocol data; "
            "not original-paper table certification unless original data/protocol are supplied"
        ),
    }
    return syn, diag


def synthesize_sprt_paper_structured(
    args: argparse.Namespace, real: list[np.ndarray], osm_ways: list[dict]
) -> tuple[list[np.ndarray], dict]:
    """Run the audited M/U SPRT structure, not the legacy paper-family adapter."""
    from check.reproduce_sprt_paper_protocol import PaperSPRTModel, build_sprt_grid_with_bounds

    bbox = parse_bbox(args.bbox)
    n_gen = int(args.n_gen or len(real))
    np.random.seed(int(args.seed))
    centers, adjacency, area_ids, cell_road_points, grid_info = build_sprt_grid_with_bounds(
        osm_ways, bbox, beta=0.05, road_length_unit="km"
    )
    model = PaperSPRTModel(
        float(args.epsilon), centers, adjacency, area_ids, bbox, alpha=1.5, cell_road_points=cell_road_points
    ).fit(real)
    syn = model.generate(n_gen)
    return syn, {
        "algorithm": "SPRT paper-structured M/U",
        "display_name": "SPRT-native",
        "family": "strict_paper_structured_reproduction",
        "privacy_budget": float(args.epsilon),
        "beta": 0.05,
        "alpha": 1.5,
        "grid_info": grid_info,
        "seed": int(args.seed),
        "certification_status": "audited paper-structured reproduction; not author-code-certified",
    }


def synthesize_baseline(args: argparse.Namespace, real: list[np.ndarray], osm_ways: list[dict]) -> tuple[list[np.ndarray], dict]:
    add_project_paths()
    import eval_layered_framework as layered
    from osm_dbscan import osm_centers_from_ways

    _paper_key, _variant, display_name = BASELINE_METHODS[args.method]
    bbox = parse_bbox(args.bbox)
    n_train = int(args.n_train or len(real))
    n_gen = int(args.n_gen or len(real))
    if n_train > len(real):
        raise RuntimeError(f"n_train={n_train} exceeds loaded trajectories={len(real)}")

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

        log(f"{display_name}: building OSM centers")
        centers = osm_centers_from_ways(osm_ways, bbox, layered.K_OSM)
        log(f"{display_name}: building two-stage road router")
        road_pts, path_cache, center_dists = layered.build_twostage_router(osm_ways, centers)
        log(f"{display_name}: preparing reproduced baseline generators")
        methods = layered.generate_methods(real[:n_train], osm_ways, centers, road_pts, path_cache, center_dists)
        if display_name not in methods:
            raise KeyError(f"baseline generator not available: {display_name}")
        np.random.seed(int(args.seed))
        log(f"{display_name}: generating {n_gen:,} synthetic trajectories from {n_train:,} training trajectories")
        generated = methods[display_name]()
    finally:
        layered.EPS = old_state["EPS"]
        layered.N_TRAIN = old_state["N_TRAIN"]
        layered.N_GEN = old_state["N_GEN"]
        layered.BBOX = old_state["BBOX"]
        layered.BBOX_DICT = old_state["BBOX_DICT"]

    syn = generated[0] if isinstance(generated, tuple) else generated
    actual_budget = getattr(methods[display_name], "budget_ledger", None)
    if args.method == "dpstd-native":
        if actual_budget is None or abs(actual_budget["total"] - float(args.epsilon)) > 1e-9:
            raise RuntimeError("DPStd fitted budget ledger differs from requested epsilon")
    diag = {
        "algorithm": display_name,
        "family": "reproduced_published_baseline",
        "privacy_budget": float(args.epsilon),
        "variant": BASELINE_METHODS[args.method][1],
        "seed": int(args.seed),
        "fitted_budget_ledger": actual_budget,
    }
    return syn, diag


def main() -> None:
    args = build_parser().parse_args()
    t0 = time.time()
    if args.method == "dptrajpm-official" and args.data.lower() in {
        "dptrajpm-official",
        "dptrajpm-bundled",
        "official-dptrajpm",
    }:
        log(f"DPTraj-PM official: loading pre-exported bundled-data replicate {int(args.official_replicate)}")
        syn, diag = synthesize_dptrajpm_official(args)
        paths = _output_paths(args.out_dir, args.method, args.tag, args.format)
        written = _save_outputs(paths, syn)
        protocol = {
            "command_role": "synthesize_dataset",
            "method": args.method,
            "data": args.data,
            "data_used": False,
            "osm_cache": args.osm_cache,
            "osm_used": False,
            "loaded_real_trajectories": None,
            "generated_trajectories": len(syn),
            "default_policy": "official-code bundled-data release export; no local fitting is performed",
            "seed": None,
            "runtime_sec": float(time.time() - t0),
            "outputs": written,
            "diagnostics": diag,
        }
        protocol_path = Path(args.protocol_json) if args.protocol_json else Path(args.out_dir) / f"{args.tag or args.method}_protocol.json"
        if not protocol_path.is_absolute():
            protocol_path = Path.cwd() / protocol_path
        protocol_written = write_json(protocol_path, protocol)
        log(f"wrote protocol JSON -> {protocol_written}")
        log("done")
        return

    public_load_limit = args.n_train if args.n_train is not None else None
    limit_note = "full corpus" if public_load_limit is None else f"first {public_load_limit:,} public-protocol trajectories"
    log(f"loading real trajectories from {args.data} ({limit_note})")
    real = load_trajectories(args.data, limit=public_load_limit)
    if not real:
        raise RuntimeError("no trajectories loaded")
    log(f"loaded {len(real):,} real trajectories")
    bbox = parse_bbox(args.bbox)
    if args.method == "privtrace-official":
        syn, diag = synthesize_privtrace_official(args, real)
        osm_ways = []
    elif args.method == "dptrajpm-official":
        syn, diag = synthesize_dptrajpm_official(args, real)
        osm_ways = []
    else:
        log(f"loading OSM cache from {args.osm_cache}")
        osm_ways_raw = load_osm_ways(args.osm_cache)
        osm_ways = filter_osm_ways_by_bbox(osm_ways_raw, bbox)
        log(f"loaded {len(osm_ways_raw):,} OSM ways; kept {len(osm_ways):,} near bbox")

    if args.method in {"privtrace-official", "dptrajpm-official"}:
        pass
    elif args.method == "sprt-paper-structured":
        syn, diag = synthesize_sprt_paper_structured(args, real, osm_ways)
    else:
        syn, diag = synthesize_baseline(args, real, osm_ways)
    log(f"generated {len(syn):,} trajectories; writing outputs")

    paths = _output_paths(args.out_dir, args.method, args.tag, args.format)
    written = _save_outputs(paths, syn)
    protocol = {
        "command_role": "synthesize_dataset",
        "method": args.method,
        "data": args.data,
        "loaded_real_trajectories": len(real),
        "private_input_occupancy_released": True,
        "public_input_capacity": None,
        "generated_trajectories": len(syn),
        "default_policy": "full-data generation unless n-train or n-gen is explicitly set",
        "bbox": parse_bbox(args.bbox),
        "osm_cache": args.osm_cache,
        "seed": int(args.seed),
        "dp_randomness": None,
        "runtime_sec": float(time.time() - t0),
        "runtime_released": True,
        "outputs": written,
        "diagnostics": diag,
    }
    protocol_path = Path(args.protocol_json) if args.protocol_json else Path(args.out_dir) / f"{args.tag or args.method}_protocol.json"
    if not protocol_path.is_absolute():
        protocol_path = Path.cwd() / protocol_path
    protocol_written = write_json(protocol_path, protocol)
    log(f"completed in {time.time() - t0:.1f}s")
    print(f"wrote protocol {protocol_written}")
    for kind, path in written.items():
        print(f"wrote {kind} {path}")


if __name__ == "__main__":
    main()
