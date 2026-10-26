"""Import the isolated current-batch MM2 cloud results.

The importer is deliberately run only after the remote controller reports
``complete`` for all four methods.  It downloads the merged CSV, checks its
slot coverage, decodes the public edge ids with the current edge cache, and
writes the ordinary ``data_results/<M>/MM2-MDP`` route cell.  No real input is
read during import and no route matching is performed locally.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import pickle
import shutil
import sys
from pathlib import Path

import paramiko

# The script is normally invoked as ``python tools/import_remote_mm2.py``;
# make the isolated package importable without requiring a caller-side
# PYTHONPATH override.
ISOLATED_ROOT = Path(__file__).resolve().parents[1]
if str(ISOLATED_ROOT) not in sys.path:
    sys.path.insert(0, str(ISOLATED_ROOT))

from algorithms.routers.mm2_mdp_adapter import _edge_cache, _read_mm2_rows, convert_rows


METHODS = ("SPRT", "PrivTrace", "DPTraj-PM", "DPStd")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_remote_measurement_binding(
    remote_info: dict,
    measurement: Path,
    *,
    expected_records: int,
) -> dict:
    """Verify that the remote export was produced from this local M output."""
    if int(remote_info.get("records", -1)) != expected_records:
        raise ValueError(
            f"remote measurement record mismatch: {remote_info.get('records')} != {expected_records}"
        )
    expected_hash = str(remote_info.get("measurement_sha256", ""))
    if not expected_hash:
        raise ValueError("remote measurement manifest has no measurement_sha256")
    actual_hash = sha256(measurement)
    if actual_hash != expected_hash:
        raise ValueError(
            f"measurement hash mismatch for {measurement}: {actual_hash} != {expected_hash}"
        )
    return {"records": expected_records, "measurement_sha256": actual_hash}


def validate_downloaded_csv(path: Path, expected_hash: str) -> str:
    actual_hash = sha256(path)
    if actual_hash != str(expected_hash):
        raise ValueError(
            f"downloaded MM2 CSV hash mismatch: {actual_hash} != {expected_hash}"
        )
    return actual_hash


def cell_output_dir(batch: Path, method: str, *, out_root: Path | None = None) -> Path:
    """Resolve an import destination without coupling staging to live outputs."""
    root = out_root.resolve() if out_root is not None else batch / "data_results" / "beijing" / "batch_001"
    return root / method / "MM2-MDP"


def ensure_empty_cell(path: Path) -> None:
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="i-1.gpushare.com")
    ap.add_argument("--port", type=int, default=5531)
    ap.add_argument("--username", default="root")
    ap.add_argument("--password", required=True)
    ap.add_argument("--remote-root", required=True)
    ap.add_argument("--batch-root", type=Path, required=True)
    ap.add_argument("--edge-cache", type=Path, required=True)
    ap.add_argument(
        "--measurement-root",
        type=Path,
        help="root containing <M>/beijing/batch_001/measurement.pkl; defaults to batch synthetic_data/measurements",
    )
    ap.add_argument(
        "--out-root",
        type=Path,
        help="staging root for imported route cells; defaults to batch data_results/beijing/batch_001",
    )
    ap.add_argument("--prepared-input-sha256", required=True)
    ap.add_argument("--public-slot-count", type=int, required=True)
    args = ap.parse_args()

    edge_nodes = _edge_cache(args.edge_cache.resolve())
    batch = args.batch_root.resolve()
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(args.host, port=args.port, username=args.username, password=args.password, timeout=30)
    sftp = ssh.open_sftp()
    try:
        remote_root = args.remote_root.rstrip("/")
        status = json.loads(sftp.open(remote_root + "/cloud_results/status.json").read().decode())
        if status.get("status") != "complete":
            raise RuntimeError(f"remote MM2 is not complete: {status}")
        track_manifest = json.loads(sftp.open(remote_root + "/inputs/tracks_manifest.json").read().decode())
        track_by_method = {str(item.get("M")): item for item in track_manifest}
        measurement_root = (args.measurement_root or (batch / "synthetic_data" / "measurements")).resolve()
        results: dict[str, object] = {}
        for method in METHODS:
            remote_dir = f"{remote_root}/cloud_results/merged/{method}"
            complete = json.loads(sftp.open(remote_dir + "/complete.json").read().decode())
            if int(complete.get("records", -1)) != args.public_slot_count:
                raise ValueError(f"{method}: merged count mismatch: {complete}")
            measurement = measurement_root / method / "beijing" / "batch_001" / "measurement.pkl"
            if not measurement.is_file():
                raise FileNotFoundError(f"local measurement not found for {method}: {measurement}")
            remote_info = track_by_method.get(method)
            if remote_info is None:
                raise ValueError(f"remote tracks_manifest.json has no entry for {method}")
            binding = validate_remote_measurement_binding(
                remote_info,
                measurement,
                expected_records=args.public_slot_count,
            )
            local_tmp = batch / "remote_imports" / "mm2_current_20261012" / f"{method}.matches.csv"
            local_tmp.parent.mkdir(parents=True, exist_ok=True)
            partial_csv = local_tmp.with_suffix(local_tmp.suffix + ".part")
            if partial_csv.exists():
                partial_csv.unlink()
            sftp.get(remote_dir + "/matches.csv", str(partial_csv))
            partial_csv.replace(local_tmp)
            downloaded_csv_hash = validate_downloaded_csv(
                local_tmp,
                str(complete.get("output_sha256", "")),
            )
            rows = _read_mm2_rows(local_tmp)
            routes, reasons = convert_rows(rows, edge_nodes, args.public_slot_count)
            out_dir = cell_output_dir(batch, method, out_root=args.out_root)
            ensure_empty_cell(out_dir)
            staging_dir = out_dir.parent / f".{out_dir.name}.{method}.importing"
            ensure_empty_cell(staging_dir)
            try:
                out = staging_dir / "synthetic_routes.pkl.gz"
                with gzip.open(out, "wb") as f:
                    pickle.dump(routes, f, protocol=pickle.HIGHEST_PROTOCOL)
                manifest = {
                    "schema_version": 1,
                    "kind": "route_cell",
                    "status": "VALID",
                    "M": method,
                    "R": "MM2-MDP",
                    "dataset": "beijing",
                    "route_generation": "executed_remote_mm2_value_iteration",
                    "remote_root": remote_root,
                    "remote_complete": complete,
                    "remote_track_manifest": remote_info,
                    "prepared_input_sha256": args.prepared_input_sha256,
                    "measurement": str(measurement.resolve()),
                    **binding,
                    "public_edge_cache_sha256": sha256(args.edge_cache.resolve()),
                    "records": len(routes),
                    "reasons": reasons,
                    "raw_source_used": False,
                    "output": {"path": str(out), "sha256": sha256(out)},
                    "downloaded_csv": {"path": str(local_tmp), "sha256": downloaded_csv_hash},
                }
                (staging_dir / "route_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                (staging_dir / "route_generation.log").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                staging_dir.replace(out_dir)
            except Exception:
                shutil.rmtree(staging_dir, ignore_errors=True)
                raise
            manifest["output"]["path"] = str(out_dir / "synthetic_routes.pkl.gz")
            manifest["output"]["sha256"] = sha256(out_dir / "synthetic_routes.pkl.gz")
            (out_dir / "route_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            (out_dir / "route_generation.log").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            results[method] = {"records": len(routes), "reasons": reasons, "out_dir": str(out_dir)}
    finally:
        sftp.close()
        ssh.close()
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
