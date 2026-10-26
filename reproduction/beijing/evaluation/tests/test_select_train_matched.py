import gzip
import hashlib
import importlib.util
import json
import pickle
from pathlib import Path

import pytest


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def fixture(tmp):
    rows = [{"accepted": True, "cpath": [10, 11]}, {"accepted": False, "cpath": []}, {"accepted": True, "cpath": [30]}]
    full = tmp / "full.pkl.gz"
    with gzip.open(full, "wb") as f:
        pickle.dump(rows, f)
    train = tmp / "train.pkl"
    train.write_bytes(pickle.dumps(["record1", "record0"]))
    match = tmp / "full.manifest.json"
    match.write_text(json.dumps({"classification": "COMMON_MAP_MATCH_CACHE_NO_SYNTHESIS", "record_count": 3,
        "input_sha256": "full-real-hash", "output_sha256": digest(full), "network_sha256": "network-hash",
        "parameters": {"matcher": "stmatch"}}))
    split = tmp / "split.json"
    split.write_text(json.dumps({"total_count": 3, "train_count": 2, "test_count": 1,
                                "train_indices": [1, 0], "test_indices": [2]}))
    audit = tmp / "audit.json"
    audit.write_text(json.dumps({"schema": "verified_disjoint_split_v1", "status": "passed",
        "all_source_indices_used_once": True, "full_sha256": "full-real-hash", "train_sha256": digest(train),
        "manifest_sha256": digest(split), "train_count": 2, "test_count": 1}))
    return dict(full_routes=full, matching_manifest=match, split_manifest=split, split_audit=audit,
                train_real=train, out_dir=tmp / "out")


def module():
    path = Path(__file__).resolve().parents[2] / "tools/select_train_matched.py"
    assert path.exists(), "train-only selection CLI must exist"
    spec = importlib.util.spec_from_file_location("select_train_matched", path)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


def test_select_preserves_order_and_failed_slots(tmp_path):
    args = fixture(tmp_path)
    result = module().select(**args)
    with gzip.open(args["out_dir"] / "train_routes.pkl.gz", "rb") as f:
        assert pickle.load(f) == [{"accepted": False, "cpath": []}, {"accepted": True, "cpath": [10, 11]}]
    assert result["record_count"] == 2
    assert result["input_sha256"] == digest(args["train_real"])
    assert result["output_sha256"] == digest(args["out_dir"] / "train_routes.pkl.gz")
    assert result["rematched"] is False


@pytest.mark.parametrize("file,key,value", [("split_audit", "train_sha256", "bad"),
    ("matching_manifest", "output_sha256", "bad"), ("split_audit", "status", "failed")])
def test_rejects_mismatched_evidence(tmp_path, file, key, value):
    args = fixture(tmp_path)
    data = json.loads(args[file].read_text())
    data[key] = value
    args[file].write_text(json.dumps(data))
    with pytest.raises(ValueError):
        module().select(**args)
    assert not args["out_dir"].exists()


def test_rejects_existing_output(tmp_path):
    args = fixture(tmp_path)
    args["out_dir"].mkdir()
    with pytest.raises(FileExistsError):
        module().select(**args)
