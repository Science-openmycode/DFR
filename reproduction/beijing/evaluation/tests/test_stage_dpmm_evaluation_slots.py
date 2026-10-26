from __future__ import annotations

import hashlib
import importlib.util
import json
import pickle
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest


TOOL = Path(__file__).resolve().parents[2] / "tools" / "stage_dpmm_evaluation_slots.py"


def stage(**kwargs):
    assert TOOL.is_file(), "DPMM evaluation slot staging is not implemented"
    spec = importlib.util.spec_from_file_location("dpmm_eval_slots_test", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.stage(**kwargs)


@pytest.fixture
def inputs(tmp_path):
    release = tmp_path / "native.pkl"
    with release.open("wb") as handle:
        pickle.dump([np.array([[3.25, -0.0], [np.nan, 9.0]], dtype=np.float32),
                     np.array([[1.0, 2.0]], dtype=np.float64)], handle)
    manifest = tmp_path / "native.json"
    manifest.write_text(json.dumps({"input_count": 4, "output_count": 2, "failed_count": 2,
                                    "released_input_indices": [2, 0],
                                    "input_pkl": "does-not-exist-private-input.pkl"}), encoding="utf-8")
    return {"release": release, "manifest": manifest, "out_dir": tmp_path / "eval-stage"}


def test_restores_declared_indices_and_preserves_successful_array_bytes(inputs):
    result = stage(**inputs)
    with Path(result["output"]["path"]).open("rb") as handle:
        rows = pickle.load(handle)
    with inputs["release"].open("rb") as handle:
        original = pickle.load(handle)
    assert len(rows) == 4
    for release_index, slot_index in enumerate([2, 0]):
        assert rows[slot_index].dtype == original[release_index].dtype
        assert rows[slot_index].shape == original[release_index].shape
        assert rows[slot_index].tobytes() == original[release_index].tobytes()
    assert rows[1].shape == rows[3].shape == (0, 2)
    assert result["released_input_indices"] == [2, 0]
    assert result["failed_input_indices"] == [1, 3]
    assert result["unchanged_released_arrays_verified"] is True
    assert result["original_slot_count"] == 4
    assert result["nonempty_count"] == 2
    assert result["formal_output"] is False
    assert result["classification"] == "EVALUATION_ONLY"


@pytest.mark.parametrize(("field", "value", "message"), [
    ("released_input_indices", [2, 2], "duplicate"),
    ("released_input_indices", [4, 0], "out.of.range"),
    ("released_input_indices", [-1, 0], "out.of.range"),
    ("released_input_indices", [2.0, 0], "integer"),
    ("released_input_indices", [True, 0], "integer"),
    ("released_input_indices", [2], "count"),
    ("output_count", 3, "count"),
    ("input_count", 5, "count"),
    ("failed_count", 1, "count"),
])
def test_refuses_inconsistent_slot_manifest_before_writing(inputs, field, value, message):
    data = json.loads(inputs["manifest"].read_text(encoding="utf-8"))
    data[field] = value
    inputs["manifest"].write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        stage(**inputs)
    assert not inputs["out_dir"].exists()


def test_records_input_output_hashes_and_does_not_modify_sources(inputs):
    original_hashes = {key: hashlib.sha256(inputs[key].read_bytes()).hexdigest()
                       for key in ("release", "manifest")}
    result = stage(**inputs)
    for key, digest in original_hashes.items():
        assert result["inputs"][key]["sha256"] == digest
        assert hashlib.sha256(inputs[key].read_bytes()).hexdigest() == digest
    assert result["output"]["sha256"] == hashlib.sha256(Path(result["output"]["path"]).read_bytes()).hexdigest()
    assert result["generator_run"] is False
    assert result["rematched"] is False


def test_rejects_nonarray_release_instead_of_converting_data(inputs):
    with inputs["release"].open("wb") as handle:
        pickle.dump([[[1.0, 2.0]], np.array([[3.0, 4.0]])], handle)
    with pytest.raises(ValueError, match="numpy.*array"):
        stage(**inputs)
    assert not inputs["out_dir"].exists()


def test_refuses_overwriting_stage_directory(inputs):
    inputs["out_dir"].mkdir()
    marker = inputs["out_dir"] / "keep"
    marker.write_text("keep")
    with pytest.raises(FileExistsError):
        stage(**inputs)
    assert marker.read_text() == "keep"


def test_cli_emits_evaluation_only_stage_manifest(inputs):
    result = subprocess.run([sys.executable, "-B", str(TOOL), "--release", str(inputs["release"]),
                             "--manifest", str(inputs["manifest"]), "--out-dir", str(inputs["out_dir"])],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    manifest = json.loads((inputs["out_dir"] / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["classification"] == "EVALUATION_ONLY"
    assert manifest["formal_output"] is False
    assert (inputs["out_dir"] / "coordinates.pkl").is_file()
