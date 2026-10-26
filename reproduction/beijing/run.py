from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.util
import json
import os
import pickle
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
LEGACY_ROOT = Path(os.environ.get("DFR_LEGACY_ROOT", ROOT/'legacy')).resolve()
MEASUREMENT_METHODS = {"SPRT": "sprt-native", "PrivTrace": "privtrace-native", "DPTraj-PM": "dptrajpm-native", "DPStd": "dpstd-native"}
ROUTERS = ("Origin", "Nearest", "FMM", "STMatch", "MM2-MDP")
NATIVE_METHODS = ("DPMM", "PUTS", "MTNet", "MTR-DFR")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_legacy() -> None:
    if not LEGACY_ROOT.is_dir():
        raise SystemExit(f"legacy DFR implementation not found: {LEGACY_ROOT}; set DFR_LEGACY_ROOT")


def command(args: list[str], cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
    print("+", " ".join(str(item) for item in args), flush=True)
    subprocess.run(args, cwd=str(cwd or ROOT), check=True, env=env)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def bbox_from_prepared(prepared: Path) -> list[float]:
    return list(read_json(prepared / "bbox.json")["bbox"])


def _stage_route_evaluation_coordinates(
    route_file: Path, route_manifest: Path, out_dir: Path,
    edge_cache: Path,
) -> tuple[Path, int]:
    """Stage M coordinates with the legacy evaluator's derivation contract.

    Road route cells contain ``synthetic_routes.pkl.gz`` while the legacy
    evaluator expects a coordinate trajectory file plus a sidecar proving
    which route object was used to score it.  The sidecar is written in the
    evaluation output directory; the original M output is never modified.
    """
    record = read_json(route_manifest)
    measurement = Path(record["measurement"])
    if not measurement.is_file():
        raise FileNotFoundError(f"route manifest measurement is missing: {measurement}")
    opener = gzip.open if measurement.suffix.lower() == ".gz" else open
    with opener(measurement, "rb") as handle:
        coordinates = pickle.load(handle)
    if not isinstance(coordinates, (list, tuple)):
        raise ValueError("measurement transcript must be a list/tuple of coordinate trajectories")
    # Keep the staging input beside (rather than inside) the evaluator output:
    # the legacy evaluator requires its output directory not to exist before
    # startup.  The sidecar remains available for audit and re-running.
    stage = out_dir.with_name(out_dir.name + "__input")
    if stage.exists():
        raise FileExistsError(f"refusing to overwrite evaluation staging input: {stage}")
    stage.mkdir(parents=True, exist_ok=True)
    coordinate_file = stage / "coordinates.pkl"
    shutil.copy2(measurement, coordinate_file)
    derivation = {
        "schema": "road-route-coordinate-derivation-v1",
        "record_count": len(coordinates),
        "coordinates": {"path": str(coordinate_file), "sha256": sha256(coordinate_file)},
        "route_source": {"path": str(route_file), "sha256": sha256(route_file)},
        "edge_cache": {"path": str(edge_cache), "sha256": sha256(edge_cache)},
        "source_measurement": {"path": str(measurement), "sha256": sha256(measurement)},
    }
    (stage / "coordinates.pkl.manifest.json").write_text(
        json.dumps(derivation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return coordinate_file, len(coordinates)


def _stage_native_route_coordinates(
    route_file: Path, route_manifest: Path, out_dir: Path,
    edge_cache: Path, public_network: Path,
    source_cache: Path | None = None,
    allow_identical_geometry: bool = False,
) -> tuple[Path, int]:
    """Resolve source-cache node pairs through unique edge IDs, never node IDs.

    DFR's legacy nodes and MTNet's prepared-network nodes are different
    namespaces. The explicitly supplied source cache is the only authority
    for decoding node pairs. Unknown, ambiguous or disconnected source pairs
    fail closed; physical/geometry failures retain an entirely empty slot.
    """
    if not public_network.is_file():
        raise FileNotFoundError(f"public network is missing: {public_network}")
    if out_dir.exists():
        raise FileExistsError(f"refusing to overwrite evaluation output: {out_dir}")
    from collections import defaultdict
    from numbers import Integral
    from tempfile import TemporaryDirectory
    from tools.stage_native_edge_coordinates import stage as stage_edges

    stage = out_dir.with_name(out_dir.name + "__input")
    if stage.exists():
        raise FileExistsError(f"refusing to overwrite evaluation staging input: {stage}")
    route_record = read_json(route_manifest)
    cache_record = route_record.get("edge_cache")
    expected_cache_hash = (cache_record.get("sha256") if isinstance(cache_record, dict)
                           else route_record.get("edge_cache_sha256"))
    if not expected_cache_hash and source_cache is None:
        raise ValueError("native node-pair manifest has no source-cache hash binding; supply explicit --source-cache")
    source_cache = Path(source_cache or edge_cache).resolve()
    source_cache_hash = sha256(source_cache)
    if expected_cache_hash and source_cache_hash.lower() != str(expected_cache_hash).lower():
        raise ValueError("source-cache hash mismatch with native route manifest binding")
    if source_cache_hash != sha256(edge_cache):
        raise ValueError("source-cache must match --edge-cache for original node-pair road scoring; use the explicit edge-ID helper for a different metric namespace")
    opener = gzip.open if route_file.suffix.lower() == ".gz" else open
    with opener(route_file, "rb") as handle:
        routes = pickle.load(handle)
    if not isinstance(routes, (list, tuple)):
        raise ValueError("native road route file must contain a list/tuple")
    opener = gzip.open if source_cache.suffix.lower() == ".gz" else open
    with opener(source_cache, "rb") as handle:
        cache = pickle.load(handle)
    if not isinstance(cache, dict) or not isinstance(cache.get("edge_nodes"), dict):
        raise ValueError("source edge cache must contain edge_nodes")
    pair_ids = defaultdict(list)
    for edge_id, pair in cache["edge_nodes"].items():
        if (not isinstance(edge_id, Integral) or isinstance(edge_id, bool)
                or not isinstance(pair, (list, tuple)) or len(pair) != 2
                or any(not isinstance(v, Integral) or isinstance(v, bool) for v in pair)):
            raise ValueError("source edge cache requires integer edge IDs and directed integer node pairs")
        pair_ids[tuple(map(int, pair))].append(int(edge_id))
    geometry_aliases = {}
    network_rows = None
    if allow_identical_geometry:
        import geopandas as gpd
        network_frame = gpd.read_file(public_network)
        if network_frame["id"].duplicated().any():
            raise ValueError("duplicate public network edge IDs are ambiguous")
        network_rows = {int(row.id): row for row in
                        network_frame[["id", "source", "target", "geometry"]].itertuples(index=False)}
    decoded = []
    for slot, route in enumerate(routes):
        if not isinstance(route, (list, tuple)):
            raise ValueError(f"native route slot {slot}: expected node-pair sequence")
        ids = []
        previous_target = None
        for position, pair in enumerate(route):
            if (not isinstance(pair, (list, tuple)) or len(pair) != 2
                    or any(not isinstance(v, Integral) or isinstance(v, bool) for v in pair)):
                raise ValueError(f"native route slot {slot} edge {position}: invalid source node pair")
            pair = tuple(map(int, pair))
            candidates = pair_ids.get(pair, [])
            if not candidates:
                raise ValueError(f"native route slot {slot} edge {position}: unknown source node pair {pair}")
            if len(candidates) != 1:
                # Coordinate tasks need unique geometry, not a guessed road ID.
                # Require identical directed endpoints AND byte-identical geometry.
                rows = [network_rows.get(e) for e in candidates] if network_rows is not None else []
                same = bool(rows) and all(r is not None and r.geometry is not None
                                          and not r.geometry.is_empty for r in rows)
                if same:
                    first = rows[0]
                    same = all((r.source, r.target, r.geometry.wkb) ==
                               (first.source, first.target, first.geometry.wkb) for r in rows)
                if not same:
                    raise ValueError(f"native route slot {slot} edge {position}: ambiguous source node pair {pair}")
                candidates = sorted(candidates)
                geometry_aliases[pair] = {"source_pair": list(pair), "edge_ids": candidates,
                                         "policy": "identical directed geometry only; edge identity unresolved"}
            if previous_target is not None and previous_target != pair[0]:
                raise ValueError(f"native route slot {slot} edge {position}: disconnected source pairs")
            ids.append(candidates[0])
            previous_target = pair[1]
        decoded.append(tuple(ids))
    # Intermediate edge IDs are evaluation representation, not generated roads.
    # Retain their exact artifact in the staging directory for audit.
    with TemporaryDirectory(prefix="dfr_native_coordinate_ids_") as temporary:
        decoded_file = Path(temporary) / "native_edge_ids.pkl.gz"
        with gzip.open(decoded_file, "wb") as handle:
            pickle.dump(decoded, handle, protocol=pickle.HIGHEST_PROTOCOL)
        derivation = stage_edges(routes=decoded_file, network=public_network,
                                 out_dir=stage, edge_cache=edge_cache)
        saved_decoded = stage / "native_edge_ids.pkl.gz"
        shutil.copy2(decoded_file, saved_decoded)
    derivation.update({
        "derivation_mode": "native-node-pairs-via-unique-edge-ID-directed-geometry",
        "representation": "node-pairs",
        "node_namespace_policy": "source-cache node pair -> unique edge ID -> public network ID geometry",
        "route_source": {"path": str(route_file.resolve()), "sha256": sha256(route_file)},
        "route_manifest": {"path": str(route_manifest.resolve()), "sha256": sha256(route_manifest)},
        "source_cache": {"path": str(source_cache), "sha256": source_cache_hash},
        "source_cache_authority": "route_manifest_hash_binding" if expected_cache_hash else "explicit_source_cache_argument",
        "decoded_edge_ids": {"path": str(saved_decoded.resolve()), "sha256": sha256(saved_decoded)},
        "adapter": {"path": str(Path(__file__).resolve()), "sha256": sha256(Path(__file__))},
    })
    if geometry_aliases:
        derivation["geometry_aliases"] = list(geometry_aliases.values())
        representatives = derivation.pop("decoded_edge_ids")
        renamed = saved_decoded.with_name("coordinate_only_edge_representatives.pkl.gz")
        saved_decoded.rename(renamed)
        representatives.update(path=str(renamed.resolve()), not_for_edge_identity_scoring=True)
        derivation["coordinate_only_edge_representatives"] = representatives
        derivation["derivation_mode"] = "native-node-pairs-to-unique-directed-geometry"
        derivation["node_namespace_policy"] = "source-cache node pair -> exact directed geometry equivalence; no edge identity claim"
    text = json.dumps(derivation, ensure_ascii=False, indent=2) + "\n"
    (stage / "coordinates.pkl.manifest.json").write_text(text, encoding="utf-8")
    (stage / "manifest.json").write_text(text, encoding="utf-8")
    return stage / "coordinates.pkl", len(decoded)


def dataset_data(prepared: Path) -> Path:
    path = prepared / "trajectories.pkl"
    if not path.is_file():
        path = prepared / "trajectories.pkl.gz"
    if not path.is_file():
        raise SystemExit(f"canonical trajectory file missing: {path}")
    return path


def write_lineage(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_stage_log(path: Path, *, status: str, command_line: list[str] | None = None,
                    error: BaseException | None = None, details: object | None = None) -> None:
    lines = [f"timestamp_utc={datetime.now(timezone.utc).isoformat()}", f"status={status}"]
    if command_line is not None:
        lines.append("command=" + subprocess.list2cmdline([str(value) for value in command_line]))
    if error is not None:
        lines.append(f"error_type={type(error).__name__}")
        lines.append(f"error={error}")
    if details is not None:
        lines.append("details=" + json.dumps(details, ensure_ascii=False, default=str))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_invalid_stage(out_dir: Path, *, kind: str, dataset: str, method: str,
                        error: BaseException, command_line: list[str] | None = None,
                        extra: dict | None = None) -> Path:
    """Record a failed cell without fabricating a numeric result.

    Batch execution must be able to finish its bookkeeping even when one
    external executable or public cache is missing.  The manifest is written
    before the exception is re-raised, so a caller can distinguish INVALID
    from a cell that was never attempted (MISSING).
    """
    out = out_dir.resolve()
    if out.exists() and any(out.iterdir()):
        return out / ("route_manifest.json" if kind == "route_cell" else f"{kind}_manifest.json")
    out.mkdir(parents=True, exist_ok=True)
    filename = "route_manifest.json" if kind == "route_cell" else f"{kind}_manifest.json"
    record = {
        "schema_version": 1,
        "kind": kind,
        "status": "INVALID",
        "dataset": dataset,
        "M": method if kind == "route_cell" else None,
        "error_type": type(error).__name__,
        "error": str(error),
        "raw_source_used": False,
    }
    if command_line is not None:
        record["command"] = [str(value) for value in command_line]
    if extra:
        record.update(extra)
    path = out / filename
    write_lineage(path, record)
    write_stage_log(
        out / ("route_generation.log" if kind == "route_cell" else "generation.log"),
        status="INVALID", command_line=command_line, error=error, details=record,
    )
    return path


def prepare_dataset(args: argparse.Namespace) -> None:
    script = ROOT / "preprocess" / "prepare_dataset.py"
    source = args.source.resolve()
    out_dir = args.out_dir.resolve()
    cmd = [sys.executable, str(script), "--dataset", args.dataset, "--source", str(source), "--out-dir", str(out_dir), "--seed", str(args.seed), "--train-fraction", str(args.train_fraction)]
    if args.limit is not None:
        cmd += ["--limit", str(args.limit)]
    if args.network:
        cmd += ["--network", str(args.network.resolve())]
    if args.bbox:
        cmd += ["--bbox", *(str(value) for value in args.bbox)]
    if getattr(args, "clip_to_bbox", False):
        cmd.append("--clip-to-bbox")
    command(cmd)


def preflight(args: argparse.Namespace) -> None:
    """Check a target machine before paying for a full experiment run."""
    checks: list[dict] = []
    errors: list[str] = []
    warnings: list[str] = []

    def check_path(label: str, value: Path | None, *, required: bool = False) -> None:
        if value is None:
            if required:
                errors.append(f"{label}: not provided")
            return
        path = value.resolve()
        exists = path.exists()
        checks.append({"label": label, "path": str(path), "exists": exists})
        if not exists:
            (errors if required else warnings).append(f"{label}: missing {path}")

    checks.append({"label": "python", "version": sys.version})
    for module in ("numpy", "pandas", "scipy", "matplotlib", "networkx",
                   "shapely", "geopandas", "pyogrio", "osmnx", "utm",
                   "rdp", "requests", "cvxpy"):
        available = importlib.util.find_spec(module) is not None
        checks.append({"label": f"python:{module}", "available": available})
        if not available:
            errors.append(f"python module missing: {module}")

    check_path("legacy_root", LEGACY_ROOT, required=args.require_legacy)
    if args.require_legacy:
        for relative in (
            "generation/baselines/algorithms/literature_baselines/entrypoints/generate.py",
            "evaluation/evaluation/evaluate_all.py",
            "generation/mtr_dfr/run.py",
        ):
            check_path(f"legacy:{relative}", LEGACY_ROOT / relative, required=True)
    check_path("prepared_data", args.prepared_data, required=bool(args.prepared_data))
    check_path("osm_cache", args.osm_cache, required=bool(args.osm_cache))
    check_path("public_network", args.public_network, required=bool(args.public_network))
    check_path("edge_cache", args.edge_cache, required=bool(args.edge_cache))
    check_path("fmm_executable", args.fmm_executable, required=bool(args.fmm_executable))
    check_path("stmatch_executable", args.stmatch_executable, required=bool(args.stmatch_executable))
    check_path("ubodt", args.ubodt, required=bool(args.ubodt))
    check_path("mm2_executable", args.mm2_executable, required=bool(args.mm2_executable))
    check_path("mm2_network", args.mm2_network, required=bool(args.mm2_network))
    report = {
        "schema_version": 1,
        "status": "VALID" if not errors else "INVALID",
        "root": str(ROOT),
        "legacy_root": str(LEGACY_ROOT),
        "checks": checks,
        "warnings": warnings,
        "errors": errors,
    }
    write_lineage(args.out.resolve(), report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if errors and args.strict:
        raise SystemExit(2)


def synthesize_m(args: argparse.Namespace) -> None:
    if args.m in ('SPRT', 'PrivTrace', 'DPStd'):
        prepared=args.prepared_data.resolve()
        slots=min(args.public_slot_count,8) if getattr(args,'smoke',False) else args.public_slot_count
        bbox=args.bbox or bbox_from_prepared(prepared)
        if args.m=='DPStd' and args.dataset=='beijing':
            bbox=[39.4,40.8,115.8,117.4]
        cmd=[sys.executable,'-X','utf8',str(ROOT/'algorithms/measurements/frozen_adapter.py'),
            '--method',args.m,'--data',str(dataset_data(prepared)),'--out',str(args.out_dir.resolve()),
            '--epsilon',str(args.epsilon),'--seed',str(args.seed),'--slots',str(slots),
            '--bbox',*map(str,bbox),'--osm',str(args.osm_cache.resolve())]
        try:
            command(cmd)
        except (subprocess.CalledProcessError,OSError) as error:
            write_invalid_stage(args.out_dir,kind='measurement',dataset=args.dataset,method=args.m,
                error=error,command_line=cmd)
            raise
        write_stage_log(args.out_dir/'generation.log',status='VALID',command_line=cmd,
                        details={'M':args.m,'public_slot_count':slots})
        return
    require_legacy()
    if args.m not in MEASUREMENT_METHODS:
        raise SystemExit(f"unsupported measurement method: {args.m}")
    prepared = args.prepared_data.resolve()
    data = dataset_data(prepared)
    out = args.out_dir.resolve()
    if out.exists():
        raise SystemExit(f"refusing to overwrite output: {out}")
    bbox = args.bbox or bbox_from_prepared(prepared)
    if not args.osm_cache:
        raise SystemExit("--osm-cache is required for the baseline wrapper and must be a public file")
    wrapper = LEGACY_ROOT / "generation" / "baselines" / "algorithms" / "literature_baselines" / "entrypoints" / "generate.py"
    slots = min(args.public_slot_count, 8) if getattr(args, "smoke", False) else args.public_slot_count
    cmd = [sys.executable, str(wrapper), "--method", MEASUREMENT_METHODS[args.m], "--data", str(data), "--epsilon", str(args.epsilon), "--out-dir", str(out), "--seed", str(args.seed), "--format", args.format, "--bbox", *(str(x) for x in bbox), "--osm-cache", str(args.osm_cache.resolve()), "--public-slot-count", str(slots)]
    try:
        command(cmd, cwd=LEGACY_ROOT)
    except (subprocess.CalledProcessError, OSError) as error:
        write_invalid_stage(
            out, kind="measurement", dataset=args.dataset, method=args.m,
            error=error, command_line=cmd,
            extra={"epsilon": args.epsilon, "seed": args.seed,
                   "public_slot_count": slots, "prepared_data": str(prepared)},
        )
        raise
    write_stage_log(out / "generation.log", status="VALID", command_line=cmd,
                    details={"M": args.m, "dataset": args.dataset, "public_slot_count": slots})
    # Stable adapter name: legacy files keep their original method name, while
    # downstream adapters can always consume measurement.pkl.
    generated = next((p for p in out.iterdir() if p.suffix == ".pkl" and p.name != "measurement.pkl"), None)
    if generated is not None:
        shutil.copy2(generated, out / "measurement.pkl")
    files = [path for path in out.rglob("*") if path.is_file()]
    write_lineage(out / "measurement_manifest.json", {
        "schema_version": 1, "kind": "measurement", "M": args.m, "dataset": args.dataset,
        "epsilon": args.epsilon, "seed": args.seed, "public_slot_count": slots,
        "prepared_data": str(prepared), "prepared_sha256": sha256(data),
        "legacy_wrapper": str(wrapper), "outputs": {str(p.relative_to(out)): sha256(p) for p in files},
    })


def synthesize_native(args: argparse.Namespace) -> None:
    # DPMM has its own frozen native entry point.  It is not an M-stage
    # measurement and must not be routed again; the accelerated path is an
    # explicit, validated subprocess rather than a hidden fallback.
    if args.method == "DPMM":
        from algorithms.native.dpmm_adapter import run_accelerated
        required = ("dpmm_accelerator", "dpmm_adapter", "dpmm_validation", "dpmm_input", "osm_cache", "bbox")
        missing = [name for name in required if not getattr(args, name, None)]
        if missing:
            raise SystemExit("DPMM accelerated mode requires: " + ", ".join("--" + name.replace("_", "-") for name in missing))
        if args.dpmm_mode != "accelerated":
            raise SystemExit("only --dpmm-mode accelerated is executable in this isolated directory; use the old archived result for registration-only comparisons")
        record = run_accelerated(
            accelerator_script=args.dpmm_accelerator,
            adapter=args.dpmm_adapter,
            validation=args.dpmm_validation,
            input_pkl=args.dpmm_input,
            osm_cache=args.osm_cache,
            bbox=args.bbox,
            epsilon=args.epsilon,
            seed=args.seed,
            zone_radius_m=args.zone_radius_m,
            utm_zone_number=args.utm_zone_number,
            utm_zone_letter=args.utm_zone_letter,
            clean_seed_waypoint_mode=args.clean_seed_waypoint_mode,
            workers=args.workers,
            checkpoint_every=args.checkpoint_every,
            expected_output_count=args.public_slot_count,
            allow_partial_output=args.allow_partial_output,
            out_dir=args.out_dir,
            tag=args.tag,
            resume=args.resume,
        )
        record.update({"dataset": args.dataset, "public_slot_count": args.public_slot_count})
        write_lineage(args.out_dir.resolve() / "native_manifest.json", record)
        write_stage_log(args.out_dir.resolve() / "generation.log",
                        status=record.get("status", "VALID"),
                        command_line=record.get("command"), details=record)
        print(json.dumps(record, ensure_ascii=False, indent=2))
        return

    require_legacy()
    if args.method not in {"MTR-DFR"}:
        raise SystemExit(f"{args.method} has no executable native source in this isolated DFR directory; use its archived native result or the DPMM accelerated entry point")
    required = ("real_matched", "edge_cache", "network", "real_source")
    missing = [name for name in required if not getattr(args, name, None)]
    if missing:
        raise SystemExit("MTR-DFR requires: " + ", ".join("--" + name.replace("_", "-") for name in missing))
    entry = LEGACY_ROOT / "generation" / "mtr_dfr" / "run.py"
    slots = min(args.public_slot_count, 8) if getattr(args, "smoke", False) else args.public_slot_count
    cmd = [sys.executable, str(entry), "--real-matched", str(args.real_matched.resolve()), "--edge-cache", str(args.edge_cache.resolve()), "--network", str(args.network.resolve()), "--real-source", str(args.real_source.resolve()), "--population", getattr(args, "population", "full-corpus"), "--seed", str(args.seed), "--out-dir", str(args.out_dir.resolve()), "--epsilon-total", str(args.epsilon), "--public-slot-count", str(slots)]
    if args.length_aware:
        cmd.append("--length-aware")
    try:
        command(cmd, cwd=LEGACY_ROOT)
    except (subprocess.CalledProcessError, OSError) as error:
        write_invalid_stage(
            args.out_dir, kind="native", dataset=args.dataset, method=args.method,
            error=error, command_line=cmd,
            extra={"epsilon": args.epsilon, "seed": args.seed,
                   "public_slot_count": slots, "native_original_route": True,
                   "rematched": False},
        )
        raise
    write_stage_log(args.out_dir.resolve() / "generation.log", status="VALID", command_line=cmd,
                    details={"method": args.method, "dataset": args.dataset,
                             "public_slot_count": slots})
    out = args.out_dir.resolve()
    files = [path for path in out.rglob("*") if path.is_file()]
    write_lineage(out / "native_manifest.json", {
        "schema_version": 1, "kind": "native", "method": args.method, "dataset": args.dataset,
        "epsilon": args.epsilon, "seed": args.seed, "public_slot_count": slots,
        "native_original_route": True, "rematched": False,
        "outputs": {str(p.relative_to(out)): sha256(p) for p in files},
    })


def find_route_source(measurement: Path) -> Path:
    candidates = [measurement / name for name in ("road_routes.pkl.gz", "synthetic_routes.pkl.gz", "routes.pkl.gz", "road_routes.pkl")]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    # Native releases (notably MTR-DFR) keep their deterministic seed/output
    # under a child directory.  Search only for the known route filenames;
    # never scan or infer from the raw reference source.
    nested = []
    for name in ("road_routes.pkl.gz", "synthetic_routes.pkl.gz", "routes.pkl.gz", "road_routes.pkl"):
        nested.extend(sorted(path for path in measurement.rglob(name) if path.is_file()))
    if len(nested) == 1:
        return nested[0]
    if len(nested) > 1:
        raise SystemExit("ambiguous route objects; pass --route-source explicitly: "
                         + ", ".join(str(path) for path in nested))
    raise SystemExit("no route object found; pass --route-source explicitly. A router may consume only the M output, never the raw source.")


def route_cell(args: argparse.Namespace) -> None:
    if args.r not in ROUTERS:
        raise SystemExit(f"unsupported router: {args.r}")
    def reject(message: str, error_type: type[BaseException] = ValueError, **extra: object) -> None:
        error = error_type(message)
        write_invalid_stage(
            args.out_dir, kind="route_cell", dataset=args.dataset, method=args.m,
            error=error, extra={"R": args.r, **extra},
        )
        raise SystemExit(message)

    if args.m == "MTR-DFR" and args.r != "Origin":
        reject("MTR-DFR is a native road release; only R=Origin is valid. Do not rematch DFR with FMM/STMatch.",
               ValueError, native_dfr_rematched=True)
    measurement = args.measurement.resolve()
    if not measurement.is_dir():
        reject(f"measurement directory not found: {measurement}", FileNotFoundError,
               measurement=str(measurement))

    def annotate_failure() -> None:
        manifest_path = args.out_dir.resolve() / "route_manifest.json"
        if not manifest_path.is_file():
            return
        try:
            record = read_json(manifest_path)
            record.update({"M": args.m, "R": args.r, "dataset": args.dataset})
            manifest_path.write_text(json.dumps(record, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
        except (OSError, ValueError, TypeError):
            pass

    # MM2-MDP is a real public router, not a registration placeholder.  It
    # consumes only the coordinate transcript emitted by M and writes the
    # evaluator's accepted/cpath representation.  The explicit public binary,
    # prepared network, and edge cache make the routing contract auditable.
    if args.r == "MM2-MDP":
        required = ("mm2_executable", "mm2_network", "edge_cache")
        missing = [name for name in required if not getattr(args, name, None)]
        if missing:
            reject("MM2-MDP requires --mm2-executable, --mm2-network and --edge-cache",
                   ValueError, missing_arguments=missing)
        if not (measurement / "measurement.pkl").is_file():
            reject(f"MM2-MDP requires M coordinate output measurement.pkl: {measurement}",
                   FileNotFoundError, measurement=str(measurement))
        from algorithms.routers.mm2_mdp_adapter import run_mm2
        manifest = run_mm2(
            measurement / "measurement.pkl",
            args.out_dir.resolve(),
            executable=args.mm2_executable.resolve(),
            network=args.mm2_network.resolve(),
            edge_cache=args.edge_cache.resolve(),
            input_srs=args.input_srs,
            tracks_srs=args.tracks_srs,
            network_srs=args.network_srs,
            max_points=args.max_points,
            seed=getattr(args, "seed", None),
        )
        manifest.update({"M": args.m, "R": args.r, "dataset": args.dataset,
                         "measurement_manifest": str((measurement / "measurement_manifest.json").resolve())})
        write_lineage(args.out_dir.resolve() / "route_manifest.json", manifest)
        write_stage_log(args.out_dir.resolve() / "route_generation.log", status=manifest.get("status", "VALID"),
                        command_line=manifest.get("command"), details=manifest)
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return

    if args.r == "Nearest":
        required = ("public_network", "edge_cache")
        missing = [name for name in required if not getattr(args, name, None)]
        if missing:
            reject("Nearest requires --public-network and --edge-cache",
                   ValueError, missing_arguments=missing)
        from algorithms.routers.nearest_adapter import run_nearest
        try:
            manifest = run_nearest(
                measurement / "measurement.pkl", args.out_dir.resolve(),
                network=args.public_network.resolve(), edge_cache=args.edge_cache.resolve(),
                input_srs=args.input_srs,
            )
        except Exception:
            annotate_failure()
            raise
        manifest.update({"M": args.m, "R": args.r, "dataset": args.dataset,
                         "measurement_manifest": str((measurement / "measurement_manifest.json").resolve())})
        write_lineage(args.out_dir.resolve() / "route_manifest.json", manifest)
        write_stage_log(args.out_dir.resolve() / "route_generation.log", status=manifest.get("status", "VALID"),
                        details=manifest)
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return

    if args.r in {"FMM", "STMatch"}:
        executable_name = "fmm_executable" if args.r == "FMM" else "stmatch_executable"
        required = ("public_network", "edge_cache", executable_name)
        missing = [name for name in required if not getattr(args, name, None)]
        if args.r == "FMM" and not getattr(args, "ubodt", None):
            missing.append("ubodt")
        if missing:
            reject(f"{args.r} requires --public-network, --edge-cache, --{executable_name.replace('_', '-')}" + (" and --ubodt" if args.r == "FMM" else ""),
                   ValueError, missing_arguments=missing)
        from algorithms.routers.public_match_adapter import run_public_match
        try:
            manifest = run_public_match(
                measurement / "measurement.pkl", args.out_dir.resolve(), matcher=args.r,
                network=args.public_network.resolve(), executable=getattr(args, executable_name).resolve(),
                edge_cache=args.edge_cache.resolve(), legacy_root=LEGACY_ROOT,
                ubodt=(args.ubodt.resolve() if args.r == "FMM" and getattr(args, "ubodt", None) else None),
                runtime_dir=args.runtime_dir.resolve() if getattr(args, "runtime_dir", None) else None,
                ubodt_executable=(args.ubodt_executable.resolve() if args.r == "FMM" and getattr(args, "ubodt_executable", None) else None),
                max_points=args.max_points, radius_m=args.radius_m, gps_error_m=args.gps_error_m,
                candidates=args.candidates, min_observation_share=args.min_observation_share,
            )
        except Exception:
            annotate_failure()
            raise
        manifest.update({"M": args.m, "R": args.r, "dataset": args.dataset,
                         "measurement_manifest": str((measurement / "measurement_manifest.json").resolve())})
        write_lineage(args.out_dir.resolve() / "route_manifest.json", manifest)
        write_stage_log(args.out_dir.resolve() / "route_generation.log", status=manifest.get("status", "VALID"),
                        command_line=manifest.get("invocation"), details=manifest)
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return

    coordinate_source = measurement / "measurement.pkl"
    route_source = None
    if args.route_source:
        route_source = args.route_source.resolve()
    elif args.r == "Origin" and coordinate_source.is_file():
        route_source = coordinate_source
    else:
        route_source = find_route_source(measurement).resolve()
    if not route_source.is_file():
        raise SystemExit(f"route source not found: {route_source}")
    out = args.out_dir.resolve()
    if out.exists():
        raise SystemExit(f"refusing to overwrite output: {out}")
    out.mkdir(parents=True)
    is_coordinate = args.r == "Origin" and route_source.name == "measurement.pkl"
    target = out / ("synthetic_coordinates.pkl" if is_coordinate else "synthetic_routes.pkl.gz")
    shutil.copy2(route_source, target)
    lineage_file = measurement / "measurement_manifest.json"
    if not lineage_file.is_file():
        lineage_file = measurement / "native_manifest.json"
    if not lineage_file.is_file():
        lineage_file = measurement / "manifest.json"
    if not lineage_file.is_file():
        reject(f"measurement/native lineage manifest missing: {measurement}",
               FileNotFoundError, measurement=str(measurement))
    write_lineage(out / "route_manifest.json", {
        "schema_version": 1, "kind": "route_cell", "router": args.r,
        "M": args.m, "R": args.r, "dataset": args.dataset,
        "measurement": str(measurement), "measurement_manifest": str(lineage_file),
        "route_source": str(route_source), "route_source_sha256": sha256(route_source),
        "output_kind": "coordinates" if is_coordinate else "road_routes",
        "raw_source_used": False, "native_dfr_rematched": False,
        "status": "registered_existing_route",
        "route_generation": "not performed by this I/O adapter; route_source is an already generated route object",
    })
    write_stage_log(out / "route_generation.log", status="VALID",
                    details={"M": args.m, "R": args.r, "dataset": args.dataset,
                             "route_source": str(route_source), "raw_source_used": False})


def route_m(args: argparse.Namespace) -> None:
    failures: list[dict] = []
    for router in args.routers:
        target = args.out_root.resolve() / args.m / router
        cell = argparse.Namespace(dataset=args.dataset, m=args.m, r=router,
                                  measurement=args.measurement, prepared_data=args.prepared_data,
                                  route_source=args.route_source, out_dir=target,
                                  mm2_executable=getattr(args, "mm2_executable", None),
                                  mm2_network=getattr(args, "mm2_network", None),
                                  edge_cache=getattr(args, "edge_cache", None),
                                  input_srs=getattr(args, "input_srs", "EPSG:4326"),
                                  tracks_srs=getattr(args, "tracks_srs", "EPSG:32650"),
                                  network_srs=getattr(args, "network_srs", "EPSG:32650"),
                                  max_points=getattr(args, "max_points", 32),
                                  seed=getattr(args, "seed", None),
                                  public_network=getattr(args, "public_network", None),
                                  fmm_executable=getattr(args, "fmm_executable", None),
                                  stmatch_executable=getattr(args, "stmatch_executable", None),
                                  ubodt=getattr(args, "ubodt", None),
                                  ubodt_executable=getattr(args, "ubodt_executable", None),
                                  runtime_dir=getattr(args, "runtime_dir", None),
                                  radius_m=getattr(args, "radius_m", 200.0),
                                  gps_error_m=getattr(args, "gps_error_m", 50.0),
                                  candidates=getattr(args, "candidates", 8),
                                  min_observation_share=getattr(args, "min_observation_share", 0.95))
        try:
            route_cell(cell)
        except (SystemExit, OSError, ValueError, RuntimeError) as error:
            failures.append({"row": f"{args.m} + {router}", "status": "INVALID",
                             "error_type": type(error).__name__, "error": str(error)})
    write_lineage(args.out_root.resolve() / "route_failures.json",
                  {"schema_version": 1, "failures": failures})
    if failures:
        print(f"route-m completed with {len(failures)} INVALID cells; see {args.out_root.resolve() / 'route_failures.json'}")


def route_all(args: argparse.Namespace) -> None:
    spec = read_json(args.experiment_spec.resolve())
    spec_dir = args.experiment_spec.resolve().parent
    cells = spec.get("cells", [])
    failures: list[dict] = []

    def _run_route_cell(cell_args: argparse.Namespace, label: str) -> None:
        try:
            route_cell(cell_args)
        except (SystemExit, OSError, ValueError, RuntimeError) as error:
            # A missing public executable/cache is an INVALID cell, not a
            # reason to abandon the other independent M×R cells.
            failures.append({"row": label, "status": "INVALID", "error_type": type(error).__name__, "error": str(error)})

    if not cells:
        measurement_root = args.measurement_root.resolve()
        result_root = args.data_results_root.resolve()
        created = 0
        for label in spec.get("rows", []):
            if " + " not in label:
                continue
            m, r = label.split(" + ", 1)
            candidates = sorted((measurement_root / m / args.dataset).glob("*/measurement_manifest.json"))
            if not candidates:
                continue
            measurement = candidates[-1].parent
            batch = measurement.name
            _run_route_cell(argparse.Namespace(dataset=args.dataset, m=m, r=r,
                                          measurement=measurement, prepared_data=args.prepared_data,
                                          route_source=None,
                                          out_dir=result_root / args.dataset / batch / m / r,
                                          mm2_executable=getattr(args, "mm2_executable", None),
                                          mm2_network=getattr(args, "mm2_network", None),
                                          edge_cache=getattr(args, "edge_cache", None),
                                          input_srs=getattr(args, "input_srs", "EPSG:4326"),
                                          tracks_srs=getattr(args, "tracks_srs", "EPSG:32650"),
                                          network_srs=getattr(args, "network_srs", "EPSG:32650"),
                                          max_points=getattr(args, "max_points", 32),
                                          seed=getattr(args, "seed", None),
                                          public_network=getattr(args, "public_network", None),
                                          fmm_executable=getattr(args, "fmm_executable", None),
                                          stmatch_executable=getattr(args, "stmatch_executable", None),
                                          ubodt=getattr(args, "ubodt", None),
                                          ubodt_executable=getattr(args, "ubodt_executable", None),
                                          runtime_dir=getattr(args, "runtime_dir", None),
                                          radius_m=getattr(args, "radius_m", 200.0),
                                          gps_error_m=getattr(args, "gps_error_m", 50.0),
                                          candidates=getattr(args, "candidates", 8),
                                          min_observation_share=getattr(args, "min_observation_share", 0.95)),
                           f"{m} + {r}")
            created += 1
        if created == 0:
            raise SystemExit(f"no measurement manifests found under {measurement_root / args.dataset}")
        write_lineage(result_root / args.dataset / "route_failures.json", {"schema_version": 1, "failures": failures})
        if failures:
            print(f"route-all completed with {len(failures)} INVALID cells; see {result_root / args.dataset / 'route_failures.json'}")
        return
    for cell in cells:
        if cell.get("dataset", args.dataset) != args.dataset:
            continue
        _run_route_cell(argparse.Namespace(
            dataset=args.dataset, m=cell["M"], r=cell["R"],
            measurement=(spec_dir / cell["measurement"]).resolve() if not Path(cell["measurement"]).is_absolute() else Path(cell["measurement"]),
            prepared_data=args.prepared_data,
            route_source=((spec_dir / cell["route_source"]).resolve() if cell.get("route_source") and not Path(cell["route_source"]).is_absolute() else (Path(cell["route_source"]) if cell.get("route_source") else None)),
            out_dir=((spec_dir / cell["out_dir"]).resolve() if not Path(cell["out_dir"]).is_absolute() else Path(cell["out_dir"])),
            mm2_executable=getattr(args, "mm2_executable", None),
            mm2_network=getattr(args, "mm2_network", None),
            edge_cache=getattr(args, "edge_cache", None),
            input_srs=getattr(args, "input_srs", "EPSG:4326"),
            tracks_srs=getattr(args, "tracks_srs", "EPSG:32650"),
            network_srs=getattr(args, "network_srs", "EPSG:32650"),
            max_points=getattr(args, "max_points", 32),
            seed=getattr(args, "seed", None),
            public_network=getattr(args, "public_network", None),
            fmm_executable=getattr(args, "fmm_executable", None),
            stmatch_executable=getattr(args, "stmatch_executable", None),
            ubodt=getattr(args, "ubodt", None),
            ubodt_executable=getattr(args, "ubodt_executable", None),
            runtime_dir=getattr(args, "runtime_dir", None),
            radius_m=getattr(args, "radius_m", 200.0),
            gps_error_m=getattr(args, "gps_error_m", 50.0),
            candidates=getattr(args, "candidates", 8),
            min_observation_share=getattr(args, "min_observation_share", 0.95)),
            f"{cell['M']} + {cell['R']}")
    output_root = args.data_results_root.resolve() / args.dataset
    write_lineage(output_root / "route_failures.json", {"schema_version": 1, "failures": failures})
    if failures:
        print(f"route-all completed with {len(failures)} INVALID cells; see {output_root / 'route_failures.json'}")


def evaluate_cell(args: argparse.Namespace) -> None:
    require_legacy()
    out = args.out_dir.resolve()
    if out.exists():
        raise SystemExit(f"refusing to overwrite output: {out}")
    stale_stage = out.with_name(out.name + "__input")
    if stale_stage.exists():
        # A previous evaluator may have failed after creating only its
        # coordinate staging directory.  It is not a result and is safe to
        # rebuild together with the missing output manifest.
        import shutil
        shutil.rmtree(stale_stage)
    evaluator = LEGACY_ROOT / "evaluation" / "evaluation" / "evaluate_all.py"
    real = args.real_reference.resolve()
    synthetic = args.synthetic.resolve()
    route_manifest: Path | None = None
    # The legacy evaluator's ``--synthetic`` input is a coordinate trajectory
    # file.  A route cell also has ``synthetic_routes.pkl.gz`` for road
    # metrics, so use the measurement transcript recorded in its manifest for
    # coordinate/demand metrics while passing the route file separately via
    # ``--road-routes``.  This keeps evaluation read-only and avoids teaching
    # the legacy evaluator about the new route-cell container.
    if synthetic.name.endswith("synthetic_routes.pkl.gz"):
        route_manifest = synthetic.parent / "route_manifest.json"
        if route_manifest.is_file():
            if not args.road_routes:
                args.road_routes = synthetic
            if not args.edge_cache:
                raise SystemExit("route-cell evaluation requires --edge-cache for synthetic_routes.pkl.gz")
            measurement = Path(read_json(route_manifest)["measurement"])
            if measurement.is_file():
                synthetic, staged_count = _stage_route_evaluation_coordinates(
                    synthetic, route_manifest, out, args.edge_cache.resolve()
                )
            elif getattr(args, "public_network", None):
                synthetic, staged_count = _stage_native_route_coordinates(
                    synthetic, route_manifest, out, args.edge_cache.resolve(), args.public_network.resolve(),
                    source_cache=getattr(args, "source_cache", None),
                )
            else:
                raise FileNotFoundError(
                    "native road route evaluation requires --public-network when route manifest measurement is a directory"
                )
            if args.public_slot_count is None:
                args.public_slot_count = staged_count
    bbox = args.bbox
    if bbox is None and getattr(args, "prepared_data", None):
        bbox = bbox_from_prepared(args.prepared_data.resolve())
    if bbox is None:
        raise SystemExit("evaluation requires --bbox or --prepared-data")
    if not args.osm_cache:
        raise SystemExit("evaluation requires --osm-cache so the public road reference is explicit")
    slots = args.public_slot_count
    if slots is None and getattr(args, "prepared_data", None):
        slots = int(read_json(args.prepared_data.resolve() / "canonical_manifest.json")["trajectory_count"])
    if not slots or slots <= 0:
        raise SystemExit("evaluation requires --public-slot-count or a canonical manifest with trajectory_count")
    cmd = [sys.executable, str(evaluator), "--real", str(real), "--synthetic", str(synthetic), "--out-dir", str(out), "--evaluation-seed", str(args.evaluation_seed), "--bbox", *(str(x) for x in bbox), "--osm-cache", str(args.osm_cache.resolve()), "--public-slot-count", str(slots)]
    if args.witness:
        cmd += ["--witness", str(args.witness.resolve())]
    if args.road_routes:
        cmd += ["--road-routes", str(args.road_routes.resolve())]
    if args.edge_cache:
        cmd += ["--edge-cache", str(args.edge_cache.resolve())]
    try:
        evaluator_env = os.environ.copy()
        # Native road releases preserve one record per public slot, including
        # explicit empty slots.  The isolated loader is instructed to retain
        # those slots; ordinary coordinate releases use its historical path.
        if synthetic.name.endswith("coordinates.pkl") and route_manifest is not None and route_manifest.is_file():
            route_record = read_json(route_manifest)
            measurement_path = route_record.get("measurement")
            if measurement_path and Path(measurement_path).is_dir():
                evaluator_env["DFR_PRESERVE_EMPTY_SLOTS"] = "1"
        command(cmd, cwd=LEGACY_ROOT, env=evaluator_env)
    except subprocess.CalledProcessError as error:
        out.mkdir(parents=True, exist_ok=True)
        write_lineage(out / "evaluation_manifest.json", {
            "schema_version": 1, "kind": "evaluation", "status": "INVALID",
            "dataset": args.dataset, "M": args.m, "R": args.r,
            "error": f"legacy evaluator exited with code {error.returncode}",
            "command": cmd,
        })
        if not getattr(args, "allow_invalid", False):
            raise
        print(f"marked invalid evaluation: {out}")
        return
    files = [path for path in out.rglob("*") if path.is_file()]
    write_lineage(out / "evaluation_manifest.json", {
        "schema_version": 1, "kind": "evaluation", "dataset": args.dataset, "M": args.m, "R": args.r,
        "real_reference": str(real), "synthetic": str(synthetic), "outputs": {str(p.relative_to(out)): sha256(p) for p in files},
    })


def _metrics_rows(path: Path, dataset: str, batch: str, measurement: str, router: str) -> list[dict]:
    import csv
    rows: list[dict] = []
    for candidate in (path / "metrics.csv", path / "results.csv", path / "metrics.json"):
        if not candidate.is_file():
            continue
        if candidate.suffix == ".json":
            value = read_json(candidate)
            if isinstance(value, dict):
                items = value.items()
            else:
                items = []
            for metric, score in items:
                if isinstance(score, (int, float)):
                    rows.append({"dataset": dataset, "batch": batch, "M": measurement, "R": router, "metric": metric, "value": score, "status": "VALID"})
            return rows
        with candidate.open("r", encoding="utf-8", newline="") as handle:
            table = list(csv.DictReader(handle))
        if not table:
            continue
        if len(table) == 1:
            for metric, score in table[0].items():
                if metric in {"M", "R", "dataset", "status"}:
                    continue
                try:
                    numeric = float(score)
                except (TypeError, ValueError):
                    continue
                rows.append({"dataset": dataset, "batch": batch, "M": measurement, "R": router, "metric": metric, "value": numeric, "status": "VALID"})
        else:
            for item in table:
                metric = item.get("metric") or item.get("name")
                score = item.get("value") or item.get("score")
                if metric is None or score is None:
                    continue
                try:
                    numeric = float(score)
                except (TypeError, ValueError):
                    continue
                rows.append({"dataset": dataset, "batch": batch, "M": measurement, "R": router, "metric": metric, "value": numeric, "status": item.get("status", "VALID")})
        return rows
    return rows


def _evaluation_candidates(root: Path) -> list[Path]:
    """Return complete route cells, excluding intermediate MM2 chunk files."""
    return [
        path for path in list(root.rglob("synthetic_routes.pkl.gz")) + list(root.rglob("synthetic_coordinates.pkl"))
        if "mm2_batches" not in path.parts
    ]


def evaluate_all(args: argparse.Namespace) -> None:
    root = args.data_results.resolve()
    all_rows: list[dict] = []
    candidates = _evaluation_candidates(root)
    for route_file in candidates:
        route_dir = route_file.parent
        router = route_dir.name
        measurement = route_dir.parent.name
        batch = route_dir.parent.parent.name
        dataset = route_dir.parent.parent.parent.name
        metrics_dir = route_dir / "metrics"
        evaluation_manifest = metrics_dir / "evaluation_manifest.json"
        needs_evaluation = not metrics_dir.exists() or not evaluation_manifest.exists()
        if evaluation_manifest.exists():
            try:
                evaluation_record = read_json(evaluation_manifest)
                evaluation_status = evaluation_record.get("status")
            except Exception:
                evaluation_record = {}
                evaluation_status = None
            # Successful legacy evaluations predate the wrapper's explicit
            # status field; their manifest has metrics.json and no error.
            if evaluation_status is None and (metrics_dir / "metrics.json").exists():
                evaluation_status = "VALID"
            needs_evaluation = evaluation_status != "VALID" or not (metrics_dir / "metrics.json").exists()
            if needs_evaluation and evaluation_status == "INVALID":
                # The cell is our own failed staging output.  Remove only this
                # explicitly marked INVALID directory so a corrected evaluator
                # can rerun it; valid results are never overwritten.
                import shutil
                shutil.rmtree(metrics_dir)
        elif needs_evaluation and metrics_dir.exists():
            # No wrapper manifest means a prior legacy process was interrupted
            # before completion.  It is not a valid result and can be safely
            # rebuilt by this run.
            import shutil
            shutil.rmtree(metrics_dir)
        if needs_evaluation:
            road_routes = route_file if route_file.name.endswith(".gz") else None
            evaluate_cell(argparse.Namespace(dataset=dataset, m=measurement, r=router,
                                              synthetic=route_file, real_reference=args.real_reference,
                                             out_dir=metrics_dir, witness=None,
                                             road_routes=road_routes,
                                             # A coordinate-only Origin cell must not receive an edge cache:
                                             # the legacy evaluator requires --road-routes whenever
                                             # --edge-cache is supplied.  Road cells still use the
                                             # caller-provided public cache.
                                             edge_cache=args.edge_cache if road_routes is not None else None,
                                             source_cache=getattr(args, "source_cache", None),
                                             evaluation_seed=args.evaluation_seed,
                                             prepared_data=args.prepared_data, bbox=None,
                                             public_network=getattr(args, "public_network", None),
                                             osm_cache=args.osm_cache, public_slot_count=args.public_slot_count,
                                             allow_invalid=True))
        all_rows.extend(_metrics_rows(metrics_dir, dataset, batch, measurement, router))
    if not all_rows:
        raise SystemExit(f"no route results found under {root}")
    import csv
    output = root / "metrics_long.csv"
    # Re-running evaluate-all must not erase separately scored edge-ID route
    # metrics or native-method rows. Those rows have stronger provenance than
    # the generic coordinate evaluator and are preserved by their source.
    preserved: dict[tuple[str, str, str], dict] = {}
    if output.is_file():
        with output.open("r", encoding="utf-8", newline="") as handle:
            for old in csv.DictReader(handle):
                source = old.get("source", "cell_evaluation")
                if source != "cell_evaluation":
                    preserved[(old.get("M", ""), old.get("R", ""), old.get("metric", ""))] = old
    normalized = []
    for row in all_rows:
        row = dict(row)
        row.setdefault("source", "cell_evaluation")
        normalized.append(row)
    merged: dict[tuple[str, str, str], dict] = {
        (row["M"], row["R"], row["metric"]): row for row in normalized
    }
    merged.update(preserved)
    output_rows = list(merged.values())
    fields = ["dataset", "batch", "M", "R", "metric", "value", "status", "source"]
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows(output_rows)
    (root / "metrics_long.json").write_text(json.dumps(output_rows, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.experiment_spec:
        spec = read_json(args.experiment_spec.resolve())
        observed = {(row["M"], row["R"]) for row in output_rows}
        missing = []
        for label in spec.get("rows", []):
            if " + " in label:
                m, r = label.split(" + ", 1)
                if (m, r) not in observed:
                    missing.append({"row": label, "status": "MISSING"})
        (root / "missing_cells.json").write_text(json.dumps(missing, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {len(all_rows)} metric rows to {output}")


def plot(args: argparse.Namespace) -> None:
    script = ROOT / "plotting" / "plot_matrix.py"
    cmd = [sys.executable, str(script), "--spec", str(args.spec.resolve()), "--results", str(args.results.resolve()), "--out-dir", str(args.out_dir.resolve()), "--metric", args.metric]
    for name in ("drop_row", "drop_col", "keep_row", "keep_col"):
        for value in getattr(args, name):
            cmd += [f"--{name.replace('_', '-')}", value]
    command(cmd)


def plot_all(args: argparse.Namespace) -> None:
    # The frozen appendix owns the metric order.  Keep this command complete:
    # it must render every declared column, not silently reduce the experiment
    # to the six road-choice metrics used by the old preview.
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    metrics = list(spec.get("columns", []))
    if not metrics:
        raise SystemExit(f"plot-all spec has no columns: {args.spec}")
    for metric in metrics:
        plot(argparse.Namespace(spec=args.spec, results=args.results, out_dir=args.out_dir, metric=metric,
                                drop_row=[], drop_col=[], keep_row=[], keep_col=[]))


def reproduce_dataset(args: argparse.Namespace) -> None:
    route_all(argparse.Namespace(dataset=args.dataset, experiment_spec=args.experiment_spec, prepared_data=args.prepared_data,
                                 measurement_root=args.measurement_root, data_results_root=args.data_results,
                                 mm2_executable=getattr(args, "mm2_executable", None),
                                 mm2_network=getattr(args, "mm2_network", None),
                                 edge_cache=getattr(args, "edge_cache", None),
                                 input_srs=getattr(args, "input_srs", "EPSG:4326"),
                                 tracks_srs=getattr(args, "tracks_srs", "EPSG:32650"),
                                 network_srs=getattr(args, "network_srs", "EPSG:32650"),
                                 max_points=getattr(args, "max_points", 32),
                                 seed=getattr(args, "seed", None),
                                 public_network=getattr(args, "public_network", None),
                                 fmm_executable=getattr(args, "fmm_executable", None),
                                 stmatch_executable=getattr(args, "stmatch_executable", None),
                                 ubodt=getattr(args, "ubodt", None),
                                 ubodt_executable=getattr(args, "ubodt_executable", None),
                                 runtime_dir=getattr(args, "runtime_dir", None),
                                 radius_m=getattr(args, "radius_m", 200.0),
                                 gps_error_m=getattr(args, "gps_error_m", 50.0),
                                 candidates=getattr(args, "candidates", 8),
                                 min_observation_share=getattr(args, "min_observation_share", 0.95)))
    evaluate_all(argparse.Namespace(dataset=args.dataset, data_results=args.data_results,
                                   real_reference=args.real_reference, edge_cache=args.edge_cache,
                                   prepared_data=args.prepared_data, osm_cache=args.osm_cache,
                                   public_network=getattr(args, "public_network", None),
                                   experiment_spec=args.experiment_spec,
                                   public_slot_count=None, evaluation_seed=args.evaluation_seed))
    plot_all(argparse.Namespace(spec=args.experiment_spec, results=args.data_results.resolve() / "metrics_long.csv",
                                out_dir=args.plot_out))


def reproduce_all(args: argparse.Namespace) -> None:
    config = read_json(args.config.resolve())
    datasets = config.get("datasets", [])
    if not datasets:
        raise SystemExit("reproduction config has no datasets")
    for item in datasets:
        reproduce_dataset(argparse.Namespace(
            dataset=item["dataset"], experiment_spec=Path(item["experiment_spec"]),
            prepared_data=Path(item["prepared_data"]), data_results=Path(item["data_results"]),
            real_reference=Path(item["real_reference"]), plot_out=Path(item["plot_out"]),
            edge_cache=Path(item["edge_cache"]) if item.get("edge_cache") else None,
            osm_cache=Path(item["osm_cache"]),
            mm2_executable=Path(item["mm2_executable"]) if item.get("mm2_executable") else None,
            mm2_network=Path(item["mm2_network"]) if item.get("mm2_network") else None,
            public_network=Path(item["public_network"]) if item.get("public_network") else None,
            fmm_executable=Path(item["fmm_executable"]) if item.get("fmm_executable") else None,
            stmatch_executable=Path(item["stmatch_executable"]) if item.get("stmatch_executable") else None,
            ubodt=Path(item["ubodt"]) if item.get("ubodt") else None,
            ubodt_executable=Path(item["ubodt_executable"]) if item.get("ubodt_executable") else None,
            runtime_dir=Path(item["runtime_dir"]) if item.get("runtime_dir") else None,
            input_srs=item.get("input_srs", "EPSG:4326"),
            tracks_srs=item.get("tracks_srs", "EPSG:32650"),
            network_srs=item.get("network_srs", "EPSG:32650"),
            max_points=int(item.get("max_points", 32)),
            seed=item.get("seed"),
            radius_m=float(item.get("radius_m", 200.0)),
            gps_error_m=float(item.get("gps_error_m", 50.0)),
            candidates=int(item.get("candidates", 8)),
            min_observation_share=float(item.get("min_observation_share", 0.95)),
            measurement_root=Path(item.get("measurement_root", "synthetic_data/measurements")),
            evaluation_seed=int(item.get("evaluation_seed", 20260713))))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="DFR isolated reproducibility orchestrator; legacy algorithms are unchanged.")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("preflight", help="check Python, legacy entry points and supplied public resources before a paid run")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--strict", action="store_true")
    p.add_argument("--require-legacy", action="store_true")
    p.add_argument("--prepared-data", type=Path)
    p.add_argument("--osm-cache", type=Path)
    p.add_argument("--public-network", type=Path)
    p.add_argument("--edge-cache", type=Path)
    p.add_argument("--fmm-executable", type=Path)
    p.add_argument("--stmatch-executable", type=Path)
    p.add_argument("--ubodt", type=Path)
    p.add_argument("--mm2-executable", type=Path)
    p.add_argument("--mm2-network", type=Path)
    p.set_defaults(func=preflight)
    p = sub.add_parser("prepare-dataset"); p.add_argument("--dataset", required=True, choices=("beijing", "oldenburg", "porto", "san_francisco")); p.add_argument("--source", type=Path, required=True); p.add_argument("--out-dir", type=Path, required=True); p.add_argument("--seed", type=int, default=20260713); p.add_argument("--train-fraction", type=float, default=0.8); p.add_argument("--limit", type=int); p.add_argument("--network", type=Path); p.add_argument("--bbox", nargs=4, type=float, metavar=("LAT_MIN", "LAT_MAX", "LON_MIN", "LON_MAX")); p.add_argument("--clip-to-bbox", action="store_true", help="retain only points inside --bbox after trajectory selection"); p.add_argument("--smoke", action="store_true"); p.set_defaults(func=prepare_dataset)
    p = sub.add_parser("synthesize-m"); p.add_argument("--dataset", required=True); p.add_argument("--m", required=True, choices=tuple(MEASUREMENT_METHODS)); p.add_argument("--prepared-data", type=Path, required=True); p.add_argument("--epsilon", type=float, default=1.4); p.add_argument("--seed", type=int, default=42); p.add_argument("--public-slot-count", type=int, required=True); p.add_argument("--out-dir", type=Path, required=True); p.add_argument("--osm-cache", type=Path, required=True); p.add_argument("--format", choices=("pkl", "npz", "both"), default="pkl"); p.add_argument("--bbox", nargs=4, type=float); p.add_argument("--smoke", action="store_true"); p.set_defaults(func=synthesize_m)
    p = sub.add_parser("synthesize-native"); p.add_argument("--dataset", required=True); p.add_argument("--method", required=True, choices=NATIVE_METHODS); p.add_argument("--real-matched", type=Path); p.add_argument("--edge-cache", type=Path); p.add_argument("--network", type=Path); p.add_argument("--real-source", type=Path); p.add_argument("--population", choices=("full-corpus", "accepted-road-subset"), default="full-corpus", help="DFR input population contract; accepted-road-subset is conditional and never silently inferred"); p.add_argument("--epsilon", type=float, default=1.4); p.add_argument("--seed", type=int, default=42); p.add_argument("--public-slot-count", type=int, required=True); p.add_argument("--out-dir", type=Path, required=True); p.add_argument("--length-aware", action="store_true"); p.add_argument("--smoke", action="store_true"); p.add_argument("--dpmm-mode", choices=("accelerated",), default="accelerated"); p.add_argument("--dpmm-accelerator", type=Path, help="validated run_dpmm_fast.py"); p.add_argument("--dpmm-adapter", type=Path, help="official DPMM adapter snapshot"); p.add_argument("--dpmm-validation", type=Path, help="equivalence validation JSON"); p.add_argument("--dpmm-input", type=Path, help="aligned input trajectory pickle"); p.add_argument("--osm-cache", type=Path, help="public OSM cache for DPMM"); p.add_argument("--bbox", nargs=4, type=float, metavar=("LAT_MIN", "LAT_MAX", "LON_MIN", "LON_MAX")); p.add_argument("--zone-radius-m", type=float, default=25.0); p.add_argument("--utm-zone-number", type=int, default=50); p.add_argument("--utm-zone-letter", default="S"); p.add_argument("--clean-seed-waypoint-mode", choices=("raw", "rdp"), default="rdp"); p.add_argument("--workers", type=int, default=16); p.add_argument("--checkpoint-every", type=int, default=25); p.add_argument("--tag", default="dpmm_fast_eps14"); p.add_argument("--resume", action="store_true"); p.add_argument("--allow-partial-output", action="store_true", help="record official DPMM yield<1 as VALID_PARTIAL instead of failing"); p.set_defaults(func=synthesize_native)
    p = sub.add_parser("route-cell"); p.add_argument("--dataset", required=True); p.add_argument("--m", required=True); p.add_argument("--r", required=True, choices=ROUTERS); p.add_argument("--measurement", type=Path, required=True); p.add_argument("--prepared-data", type=Path, required=True); p.add_argument("--route-source", type=Path); p.add_argument("--out-dir", type=Path, required=True); p.add_argument("--mm2-executable", type=Path); p.add_argument("--mm2-network", type=Path); p.add_argument("--public-network", type=Path); p.add_argument("--fmm-executable", type=Path); p.add_argument("--stmatch-executable", type=Path); p.add_argument("--ubodt", type=Path); p.add_argument("--ubodt-executable", type=Path); p.add_argument("--runtime-dir", type=Path); p.add_argument("--edge-cache", type=Path); p.add_argument("--input-srs", default="EPSG:4326"); p.add_argument("--tracks-srs", default="EPSG:32650"); p.add_argument("--network-srs", default="EPSG:32650"); p.add_argument("--max-points", type=int, default=32); p.add_argument("--radius-m", type=float, default=200.0); p.add_argument("--gps-error-m", type=float, default=50.0); p.add_argument("--candidates", type=int, default=8); p.add_argument("--min-observation-share", type=float, default=0.95); p.add_argument("--seed", type=int); p.add_argument("--smoke", action="store_true"); p.set_defaults(func=route_cell)
    p = sub.add_parser("route-m"); p.add_argument("--dataset", required=True); p.add_argument("--m", required=True); p.add_argument("--measurement", type=Path, required=True); p.add_argument("--prepared-data", type=Path, required=True); p.add_argument("--routers", nargs="+", choices=ROUTERS, default=list(ROUTERS)); p.add_argument("--route-source", type=Path); p.add_argument("--out-root", type=Path, required=True); p.add_argument("--mm2-executable", type=Path); p.add_argument("--mm2-network", type=Path); p.add_argument("--public-network", type=Path); p.add_argument("--fmm-executable", type=Path); p.add_argument("--stmatch-executable", type=Path); p.add_argument("--ubodt", type=Path); p.add_argument("--ubodt-executable", type=Path); p.add_argument("--runtime-dir", type=Path); p.add_argument("--edge-cache", type=Path); p.add_argument("--input-srs", default="EPSG:4326"); p.add_argument("--tracks-srs", default="EPSG:32650"); p.add_argument("--network-srs", default="EPSG:32650"); p.add_argument("--max-points", type=int, default=32); p.add_argument("--radius-m", type=float, default=200.0); p.add_argument("--gps-error-m", type=float, default=50.0); p.add_argument("--candidates", type=int, default=8); p.add_argument("--min-observation-share", type=float, default=0.95); p.add_argument("--seed", type=int); p.set_defaults(func=route_m)
    p = sub.add_parser("route-all"); p.add_argument("--dataset", required=True); p.add_argument("--experiment-spec", type=Path, required=True); p.add_argument("--prepared-data", type=Path, required=True); p.add_argument("--measurement-root", type=Path, default=ROOT / "synthetic_data" / "measurements"); p.add_argument("--data-results-root", type=Path, default=ROOT / "data_results"); p.add_argument("--mm2-executable", type=Path); p.add_argument("--mm2-network", type=Path); p.add_argument("--public-network", type=Path); p.add_argument("--fmm-executable", type=Path); p.add_argument("--stmatch-executable", type=Path); p.add_argument("--ubodt", type=Path); p.add_argument("--ubodt-executable", type=Path); p.add_argument("--runtime-dir", type=Path); p.add_argument("--edge-cache", type=Path); p.add_argument("--input-srs", default="EPSG:4326"); p.add_argument("--tracks-srs", default="EPSG:32650"); p.add_argument("--network-srs", default="EPSG:32650"); p.add_argument("--max-points", type=int, default=32); p.add_argument("--radius-m", type=float, default=200.0); p.add_argument("--gps-error-m", type=float, default=50.0); p.add_argument("--candidates", type=int, default=8); p.add_argument("--min-observation-share", type=float, default=0.95); p.add_argument("--seed", type=int); p.set_defaults(func=route_all)
    p = sub.add_parser("evaluate-cell"); p.add_argument("--dataset", required=True); p.add_argument("--m", required=True); p.add_argument("--r", required=True); p.add_argument("--synthetic", type=Path, required=True); p.add_argument("--real-reference", type=Path, required=True); p.add_argument("--prepared-data", type=Path); p.add_argument("--bbox", nargs=4, type=float); p.add_argument("--osm-cache", type=Path, required=True); p.add_argument("--public-slot-count", type=int); p.add_argument("--out-dir", type=Path, required=True); p.add_argument("--witness", type=Path); p.add_argument("--road-routes", type=Path); p.add_argument("--edge-cache", type=Path); p.add_argument("--public-network", type=Path, help="public network for deterministic native-road geometry conversion"); p.add_argument("--evaluation-seed", type=int, default=20260713); p.add_argument("--allow-invalid", action="store_true"); p.set_defaults(func=evaluate_cell)
    p.add_argument("--source-cache", type=Path, help="explicit native node-pair source cache when route manifest has no hash binding; must match --edge-cache")
    p = sub.add_parser("evaluate-all"); p.add_argument("--dataset", required=True); p.add_argument("--data-results", type=Path, required=True); p.add_argument("--real-reference", type=Path, required=True); p.add_argument("--prepared-data", type=Path, required=True); p.add_argument("--osm-cache", type=Path, required=True); p.add_argument("--public-slot-count", type=int); p.add_argument("--experiment-spec", type=Path); p.add_argument("--edge-cache", type=Path); p.add_argument("--public-network", type=Path, help="public network for deterministic native-road geometry conversion"); p.add_argument("--evaluation-seed", type=int, default=20260713); p.set_defaults(func=evaluate_all)
    p.add_argument("--source-cache", type=Path, help="explicit native node-pair source cache; use per-cell evaluation for mixed source namespaces")
    p = sub.add_parser("plot"); p.add_argument("--spec", type=Path, required=True); p.add_argument("--results", type=Path, required=True); p.add_argument("--out-dir", type=Path, required=True); p.add_argument("--metric", default="ALL", help="one frozen metric, or ALL for the full row×metric heatmap"); p.add_argument("--drop-row", action="append", default=[]); p.add_argument("--drop-col", action="append", default=[]); p.add_argument("--keep-row", action="append", default=[]); p.add_argument("--keep-col", action="append", default=[]); p.set_defaults(func=plot)
    p = sub.add_parser("plot-all"); p.add_argument("--spec", type=Path, required=True); p.add_argument("--results", type=Path, required=True); p.add_argument("--out-dir", type=Path, required=True); p.set_defaults(func=plot_all)
    p = sub.add_parser("reproduce-m"); p.add_argument("--dataset", required=True); p.add_argument("--m", required=True, choices=tuple(MEASUREMENT_METHODS)); p.add_argument("--prepared-data", type=Path, required=True); p.add_argument("--epsilon", type=float, default=1.4); p.add_argument("--seed", type=int, default=42); p.add_argument("--public-slot-count", type=int, required=True); p.add_argument("--out-dir", type=Path, required=True); p.add_argument("--osm-cache", type=Path, required=True); p.add_argument("--format", choices=("pkl", "npz", "both"), default="pkl"); p.add_argument("--bbox", nargs=4, type=float); p.add_argument("--smoke", action="store_true"); p.set_defaults(func=synthesize_m)
    p = sub.add_parser("reproduce-mr"); p.add_argument("--dataset", required=True); p.add_argument("--m", required=True); p.add_argument("--measurement", type=Path, required=True); p.add_argument("--prepared-data", type=Path, required=True); p.add_argument("--routers", nargs="+", choices=ROUTERS, default=list(ROUTERS)); p.add_argument("--route-source", type=Path); p.add_argument("--out-root", type=Path, required=True); p.add_argument("--mm2-executable", type=Path); p.add_argument("--mm2-network", type=Path); p.add_argument("--public-network", type=Path); p.add_argument("--fmm-executable", type=Path); p.add_argument("--stmatch-executable", type=Path); p.add_argument("--ubodt", type=Path); p.add_argument("--ubodt-executable", type=Path); p.add_argument("--runtime-dir", type=Path); p.add_argument("--edge-cache", type=Path); p.add_argument("--input-srs", default="EPSG:4326"); p.add_argument("--tracks-srs", default="EPSG:32650"); p.add_argument("--network-srs", default="EPSG:32650"); p.add_argument("--max-points", type=int, default=32); p.add_argument("--radius-m", type=float, default=200.0); p.add_argument("--gps-error-m", type=float, default=50.0); p.add_argument("--candidates", type=int, default=8); p.add_argument("--min-observation-share", type=float, default=0.95); p.add_argument("--seed", type=int); p.set_defaults(func=route_m)
    p = sub.add_parser("reproduce-dataset"); p.add_argument("--dataset", required=True); p.add_argument("--experiment-spec", type=Path, required=True); p.add_argument("--prepared-data", type=Path, required=True); p.add_argument("--data-results", type=Path, required=True); p.add_argument("--measurement-root", type=Path, default=ROOT / "synthetic_data" / "measurements"); p.add_argument("--real-reference", type=Path, required=True); p.add_argument("--plot-out", type=Path, required=True); p.add_argument("--osm-cache", type=Path, required=True); p.add_argument("--edge-cache", type=Path); p.add_argument("--mm2-executable", type=Path); p.add_argument("--mm2-network", type=Path); p.add_argument("--public-network", type=Path); p.add_argument("--fmm-executable", type=Path); p.add_argument("--stmatch-executable", type=Path); p.add_argument("--ubodt", type=Path); p.add_argument("--ubodt-executable", type=Path); p.add_argument("--runtime-dir", type=Path); p.add_argument("--input-srs", default="EPSG:4326"); p.add_argument("--tracks-srs", default="EPSG:32650"); p.add_argument("--network-srs", default="EPSG:32650"); p.add_argument("--max-points", type=int, default=32); p.add_argument("--radius-m", type=float, default=200.0); p.add_argument("--gps-error-m", type=float, default=50.0); p.add_argument("--candidates", type=int, default=8); p.add_argument("--min-observation-share", type=float, default=0.95); p.add_argument("--seed", type=int); p.add_argument("--evaluation-seed", type=int, default=20260713); p.set_defaults(func=reproduce_dataset)
    p = sub.add_parser("reproduce-all"); p.add_argument("--config", type=Path, required=True); p.set_defaults(func=reproduce_all)
    return parser


if __name__ == "__main__":
    args = build_parser().parse_args()
    args.func(args)
