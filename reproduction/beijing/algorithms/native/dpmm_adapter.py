"""Adapter for the validated DPMM accelerated entry point.

The accelerated implementation is intentionally kept outside the DFR core.  It
is the frozen ``run_dpmm_fast.py`` wrapper from the earlier reproducibility
batch; this module only builds the command, executes it, and writes a lineage
manifest.  No routing or post-hoc matching is performed here.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Sequence


METHOD = "DPMM"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _required_file(path: Path, label: str) -> Path:
    path = Path(path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"{label} does not exist: {path}")
    return path


def build_accelerated_command(
    *,
    accelerator_script: Path,
    adapter: Path,
    validation: Path,
    input_pkl: Path,
    osm_cache: Path,
    bbox: Sequence[float],
    epsilon: float,
    seed: int,
    zone_radius_m: float,
    utm_zone_number: int,
    utm_zone_letter: str,
    clean_seed_waypoint_mode: str,
    workers: int,
    checkpoint_every: int,
    out_dir: Path,
    tag: str,
    resume: bool,
) -> list[str]:
    """Return the exact frozen accelerated-DPMM command line.

    The old accelerator requires both an equivalence-validation JSON and the
    unchanged official adapter.  They are explicit arguments so a migrated
    experiment cannot silently fall back to an unvalidated implementation.
    """
    if len(bbox) != 4:
        raise ValueError("bbox must contain LAT_MIN LAT_MAX LON_MIN LON_MAX")
    if workers < 1:
        raise ValueError("workers must be >= 1")
    if checkpoint_every < 0:
        raise ValueError("checkpoint_every must be >= 0")
    if clean_seed_waypoint_mode not in {"raw", "rdp"}:
        raise ValueError("clean_seed_waypoint_mode must be raw or rdp")
    return [
        sys.executable,
        str(_required_file(accelerator_script, "DPMM accelerator script")),
        "--adapter", str(_required_file(adapter, "DPMM official adapter")),
        "--validation", str(_required_file(validation, "DPMM validation manifest")),
        "--input-pkl", str(_required_file(input_pkl, "DPMM input pickle")),
        "--osm-cache", str(_required_file(osm_cache, "DPMM public OSM cache")),
        "--bbox", *(str(float(value)) for value in bbox),
        "--epsilon", str(float(epsilon)),
        "--seed", str(int(seed)),
        "--zone-radius-m", str(float(zone_radius_m)),
        "--utm-zone-number", str(int(utm_zone_number)),
        "--utm-zone-letter", str(utm_zone_letter),
        "--clean-seed-waypoint-mode", clean_seed_waypoint_mode,
        "--workers", str(int(workers)),
        "--checkpoint-every", str(int(checkpoint_every)),
        "--out-dir", str(Path(out_dir).resolve()),
        "--tag", str(tag),
        *( ["--resume"] if resume else [] ),
    ]


def run_accelerated(
    *,
    accelerator_script: Path,
    adapter: Path,
    validation: Path,
    input_pkl: Path,
    osm_cache: Path,
    bbox: Sequence[float],
    epsilon: float,
    seed: int,
    zone_radius_m: float,
    utm_zone_number: int,
    utm_zone_letter: str,
    clean_seed_waypoint_mode: str,
    workers: int,
    checkpoint_every: int,
    expected_output_count: int,
    allow_partial_output: bool,
    out_dir: Path,
    tag: str,
    resume: bool,
) -> dict:
    if expected_output_count < 1:
        raise ValueError("expected_output_count must be >= 1")
    out_dir = Path(out_dir).resolve()
    if out_dir.exists() and not resume and any(out_dir.iterdir()):
        raise FileExistsError(f"refusing to overwrite non-empty DPMM output: {out_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)
    # The frozen accelerator uses a small PID lock.  A killed parent can leave
    # that file behind and make an otherwise safe ``--resume`` invocation fail
    # before it reaches the checkpoint.  Remove it only when the recorded PID
    # is no longer alive; a live lock remains a hard error in the accelerator.
    stale_lock_removed = False
    lock_path = out_dir / ".fast_generation.lock"
    if lock_path.exists() and resume:
        try:
            lock_pid = int(lock_path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            lock_pid = None
        if lock_pid is None:
            lock_path.unlink(missing_ok=True)
            stale_lock_removed = True
        else:
            try:
                import os
                os.kill(lock_pid, 0)
            except OSError:
                lock_path.unlink(missing_ok=True)
                stale_lock_removed = True
            else:
                raise RuntimeError(
                    f"DPMM output is locked by live pid {lock_pid}: {lock_path}"
                )
    command = build_accelerated_command(
        accelerator_script=accelerator_script, adapter=adapter,
        validation=validation, input_pkl=input_pkl, osm_cache=osm_cache,
        bbox=bbox, epsilon=epsilon, seed=seed, zone_radius_m=zone_radius_m,
        utm_zone_number=utm_zone_number, utm_zone_letter=utm_zone_letter,
        clean_seed_waypoint_mode=clean_seed_waypoint_mode, workers=workers,
        checkpoint_every=checkpoint_every, out_dir=out_dir, tag=tag,
        resume=resume,
    )
    launch = {
        "schema_version": 1,
        "kind": "native-dpmm",
        "method": METHOD,
        "status": "running",
        "acceleration_mode": "validated_parallel_path_cache",
        "workers": int(workers),
        "expected_output_count": int(expected_output_count),
        "allow_partial_output": bool(allow_partial_output),
        "epsilon": float(epsilon),
        "seed": int(seed),
        "command": command,
        "accelerator_script": {"path": str(Path(accelerator_script).resolve()), "sha256": sha256(Path(accelerator_script).resolve())},
        "official_adapter": {"path": str(Path(adapter).resolve()), "sha256": sha256(Path(adapter).resolve())},
        "validation_manifest": {"path": str(Path(validation).resolve()), "sha256": sha256(Path(validation).resolve())},
        "input_pkl": {"path": str(Path(input_pkl).resolve()), "sha256": sha256(Path(input_pkl).resolve())},
        "osm_cache": {"path": str(Path(osm_cache).resolve()), "sha256": sha256(Path(osm_cache).resolve())},
        "rematched": False,
        "raw_source_used_by_router": False,
        "stale_lock_removed": stale_lock_removed,
    }
    lineage = out_dir / "native_manifest.json"
    lineage.write_text(json.dumps(launch, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        subprocess.run(command, cwd=str(Path(accelerator_script).resolve().parent), check=True)
    except Exception as exc:
        launch.update({"status": "INVALID", "error_type": type(exc).__name__, "error": str(exc)})
        lineage.write_text(json.dumps(launch, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        raise
    release = out_dir / f"{tag}.pkl"
    manifest = out_dir / f"{tag}.json"
    if not release.is_file() or not manifest.is_file():
        launch.update({"status": "INVALID", "error_type": "MissingOutput", "expected": [str(release), str(manifest)]})
        lineage.write_text(json.dumps(launch, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        raise FileNotFoundError(f"DPMM accelerator did not produce {release} and {manifest}")
    try:
        generation = json.loads(manifest.read_text(encoding="utf-8"))
        actual_count = int(generation["output_count"])
    except (OSError, KeyError, TypeError, ValueError) as exc:
        launch.update({"status": "INVALID", "error_type": "InvalidGenerationManifest", "error": str(exc)})
        lineage.write_text(json.dumps(launch, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        raise ValueError(f"DPMM generation manifest has no valid output_count: {manifest}") from exc
    if actual_count != int(expected_output_count) and not allow_partial_output:
        launch.update({
            "status": "INVALID",
            "error_type": "OutputCountMismatch",
            "actual_output_count": actual_count,
            "expected_output_count": int(expected_output_count),
        })
        lineage.write_text(json.dumps(launch, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        raise ValueError(
            f"DPMM output_count={actual_count} does not match public_slot_count={expected_output_count}"
        )
    output_status = "VALID" if actual_count == int(expected_output_count) else "VALID_PARTIAL"
    launch.update({
        "status": output_status,
        "actual_output_count": actual_count,
        "output_yield": actual_count / float(expected_output_count),
        "release": {"path": str(release), "sha256": sha256(release)},
        "generation_manifest": {"path": str(manifest), "sha256": sha256(manifest)},
    })
    lineage.write_text(json.dumps(launch, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return launch
