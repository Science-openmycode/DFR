"""Restore declared DPMM release slots for evaluation only.

Reads only the existing release pickle and its supplied JSON manifest. It does
not open the manifest's private input paths, generate trajectories, resample,
match roads, or alter successful arrays. Output is not a formal DP release.
Only load trusted local experiment pickles.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import pickle
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


def _binding(path):
    path = Path(path).resolve()
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return {"path": path.as_posix(), "sha256": digest.hexdigest(), "bytes": path.stat().st_size}


def _count(value, name):
    if type(value) is not int or value < 0:
        raise ValueError(f"{name}: expected nonnegative integer count")
    return value


def _array_digest(rows, indices):
    """Bind each declared original slot to its dtype, shape and exact data bytes."""
    digest = hashlib.sha256()
    for index, array in zip(indices, rows):
        header = json.dumps([index, array.dtype.str, list(array.shape)], separators=(",", ":")).encode("ascii")
        body = array.tobytes(order="C")
        digest.update(len(header).to_bytes(8, "big"))
        digest.update(header)
        digest.update(len(body).to_bytes(8, "big"))
        digest.update(body)
    return digest.hexdigest()


def stage(*, release, manifest, out_dir):
    started = datetime.now(timezone.utc).isoformat()
    timer = time.perf_counter()
    release, manifest, out_dir = Path(release).resolve(), Path(manifest).resolve(), Path(out_dir).resolve()
    if out_dir.exists():
        raise FileExistsError(f"refusing to overwrite staging directory: {out_dir}")
    inputs = {"release": _binding(release), "manifest": _binding(manifest)}
    metadata = json.loads(manifest.read_text(encoding="utf-8"))
    if not isinstance(metadata, dict):
        raise ValueError("manifest must be a JSON object")
    input_count = _count(metadata.get("input_count"), "input_count")
    output_count = _count(metadata.get("output_count"), "output_count")
    failed_count = _count(metadata.get("failed_count"), "failed_count")
    indices = metadata.get("released_input_indices")
    if not isinstance(indices, list):
        raise ValueError("released_input_indices must be an explicit list")
    if any(type(index) is not int for index in indices):
        raise ValueError("released_input_indices must contain integer indices")
    if len(set(indices)) != len(indices):
        raise ValueError("duplicate released_input_indices")
    if any(index < 0 or index >= input_count for index in indices):
        raise ValueError("released_input_indices contains out-of-range index")
    if input_count != output_count + failed_count or len(indices) != output_count:
        raise ValueError("manifest count mismatch: input/output/failed/index counts are inconsistent")
    opener = gzip.open if release.suffix.lower() == ".gz" else open
    with opener(release, "rb") as handle:
        rows = pickle.load(handle)
    if not isinstance(rows, (list, tuple)) or len(rows) != output_count:
        raise ValueError("release count does not match declared output_count")
    for index, array in enumerate(rows):
        if not isinstance(array, np.ndarray) or array.ndim != 2 or array.shape[1] != 2:
            raise ValueError(f"release row {index}: expected numpy coordinate array of shape (N, 2)")
        if array.dtype.kind not in "fiu":
            raise ValueError(f"release row {index}: unsupported coordinate array dtype {array.dtype}")
    # Assignment preserves the original successful arrays, including dtype and
    # signed zero / NaN bit patterns. No coordinates are constructed for failure.
    slots = [np.empty((0, 2), dtype=float) for _ in range(input_count)]
    for index, array in zip(indices, rows):
        slots[index] = array
    occupied = set(indices)
    failed_indices = [index for index in range(input_count) if index not in occupied]
    source_digest = _array_digest(rows, indices)
    for key, path in (("release", release), ("manifest", manifest)):
        if _binding(path)["sha256"] != inputs[key]["sha256"]:
            raise ValueError(f"{key} changed during staging; refusing inconsistent source binding")
    out_dir.mkdir(parents=True, exist_ok=False)
    output = out_dir / "coordinates.pkl"
    with output.open("wb") as handle:
        pickle.dump(slots, handle, protocol=pickle.HIGHEST_PROTOCOL)
    with output.open("rb") as handle:
        restored = pickle.load(handle)
    restored_released = [restored[index] for index in indices]
    restored_digest = _array_digest(restored_released, indices)
    exact_arrays = all(
        original.dtype == saved.dtype and original.shape == saved.shape
        and original.tobytes(order="C") == saved.tobytes(order="C")
        for original, saved in zip(rows, restored_released)
    )
    if (len(restored) != input_count or source_digest != restored_digest or not exact_arrays
            or any(restored[index].shape != (0, 2) for index in failed_indices)):
        raise RuntimeError("staged output verification failed; output is not approved for evaluation")
    record = {
        "schema_version": "dpmm-evaluation-slot-staging-v1",
        "classification": "EVALUATION_ONLY", "formal_output": False,
        "generator_run": False, "rematched": False, "resampled": False,
        "raw_private_input_accessed": False,
        "inputs": inputs, "stager": _binding(Path(__file__)), "output": _binding(output),
        "original_slot_count": input_count, "released_array_count": output_count,
        "failed_count": failed_count, "nonempty_count": sum(len(row) > 0 for row in restored),
        "released_input_indices": indices, "failed_input_indices": failed_indices,
        "failed_slot_reason": "no released array for original input slot according to supplied DPMM manifest",
        "failed_slot_representation": "numpy.empty((0, 2), dtype=float64)",
        "unchanged_released_arrays_verified": True,
        "verification": "pickle round-trip; each declared index, dtype, shape and exact C-order array bytes compared",
        "source_indexed_arrays_sha256": source_digest,
        "staged_indexed_arrays_sha256": restored_digest,
        "started_at_utc": started, "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": time.perf_counter() - timer,
    }
    (out_dir / "manifest.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    print(json.dumps(stage(**vars(parser.parse_args())), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
