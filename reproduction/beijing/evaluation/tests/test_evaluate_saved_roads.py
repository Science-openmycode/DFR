from __future__ import annotations

import gzip
import hashlib
import importlib.util
import json
import pickle
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "evaluate_saved_roads.py"


@pytest.fixture
def evaluator():
    # Resolve the actual implementation when called, so missing behavior is a
    # test-body failure rather than a collection/setup error. No dependency is mocked.
    def evaluate_saved(**kwargs):
        assert TOOL.is_file(), "evaluation-only saved-road CLI is not implemented"
        spec = importlib.util.spec_from_file_location("saved_road_evaluator_test", TOOL)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.evaluate_saved(**kwargs)
    return SimpleNamespace(evaluate_saved=evaluate_saved)


def dump(path, value):
    with gzip.open(path, "wb") as handle:
        pickle.dump(value, handle)
    return path


@pytest.fixture
def inputs(tmp_path):
    cache = {
        "edge_nodes": {1: (10, 11), 2: (11, 12), 3: (11, 13), 4: (12, 10)},
        "outdegree": {10: 1, 11: 2, 12: 1, 13: 0},
        "labels24": {10: 0, 11: 1, 12: 2, 13: 3},
        "labels96": {10: 0, 11: 1, 12: 2, 13: 3},
        "labels384": {10: 0, 11: 1, 12: 2, 13: 3},
    }
    real = [
        {"accepted": True, "cpath": [1, 2, 4, 1, 3]},
        {"accepted": True, "cpath": [1, 3]},
        {"accepted": False, "cpath": []},
    ]
    return {
        "real_routes": dump(tmp_path / "real.pkl.gz", real),
        "synthetic_routes": dump(tmp_path / "syn.pkl.gz", [[1, 2, 4, 1, 3], [1, 3], []]),
        "metric_cache": dump(tmp_path / "cache.pkl.gz", cache),
        "representation": "edge-ids",
        "method": "Example",
        "router": "Native",
        "out": tmp_path / "scores",
    }


def test_keeps_empty_slots_and_reports_conditioned_real_reference(evaluator, inputs):
    manifest = evaluator.evaluate_saved(**inputs)
    values = json.loads((inputs["out"] / "metrics.json").read_text())
    assert len(values) == 19
    assert values["RoadYield"] == pytest.approx(2 / 3)
    assert values["EdgeCPC"] == 1.0
    assert values["BTF"] == pytest.approx(2 / 3)
    assert manifest["real"]["slots"] == 3
    assert manifest["real"]["valid_routes"] == 2
    assert manifest["real"]["reference_slots"] == 2
    assert manifest["synthetic"]["slots"] == 3
    assert manifest["synthetic"]["valid_routes"] == 2
    assert manifest["rematched"] is False


def test_edge_records_ignore_unrelated_node_namespace(evaluator, inputs):
    inputs["representation"] = "edge-records"
    dump(inputs["synthetic_routes"], [
        {"accepted": True, "cpath": [1, 3], "node_sequence": [900, 901, 902]},
        {"accepted": False, "cpath": [1, 3], "node_sequence": [10, 11, 13]},
    ])
    evaluator.evaluate_saved(**inputs)
    values = json.loads((inputs["out"] / "metrics.json").read_text())
    assert values["RoadYield"] == 0.5


def test_node_pairs_convert_only_by_unique_common_edge_id(evaluator, inputs, tmp_path):
    inputs["representation"] = "node-pairs"
    inputs["source_cache"] = dump(tmp_path / "source.pkl.gz", {
        "edge_nodes": {1: (100, 101), 2: (101, 102), 3: (101, 103), 4: (102, 100)},
    })
    dump(inputs["synthetic_routes"], [
        [(100, 101), (101, 102), (102, 100), (100, 101), (101, 103)],
        [(100, 101), (101, 103)], [],
    ])
    manifest = evaluator.evaluate_saved(**inputs)
    values = json.loads((inputs["out"] / "metrics.json").read_text())
    assert values["EdgeCPC"] == 1.0
    assert values["RoadYield"] == pytest.approx(2 / 3)
    assert manifest["inputs"]["source_cache"]["sha256"] == hashlib.sha256(inputs["source_cache"].read_bytes()).hexdigest()


@pytest.mark.parametrize(("representation", "raw", "message"), [
    ("edge-ids", [[999]], "unknown.*edge"),
    ("edge-ids", [[1.5]], "integer"),
    ("edge-ids", [[True]], "integer"),
    ("edge-ids", [[(10, 11)]], "integer"),
    ("edge-records", [[1, 3]], "record"),
    ("edge-records", [{"cpath": [1, 3]}], "accepted"),
    ("edge-records", [{"accepted": "false", "cpath": [1, 3]}], "boolean"),
    ("edge-records", [{"accepted": True, "node_sequence": [10, 11]}], "cpath"),
    ("edge-ids", [None], "sequence"),
])
def test_refuses_wrong_schema_without_creating_outputs(evaluator, inputs, representation, raw, message):
    inputs["representation"] = representation
    dump(inputs["synthetic_routes"], raw)
    with pytest.raises(ValueError, match=message):
        evaluator.evaluate_saved(**inputs)
    assert not inputs["out"].exists()


def test_node_pairs_require_source_cache(evaluator, inputs):
    inputs["representation"] = "node-pairs"
    with pytest.raises(ValueError, match="source.cache"):
        evaluator.evaluate_saved(**inputs)


@pytest.mark.parametrize(("source", "route", "message"), [
    ({1: (100, 101), 2: (100, 101)}, [(100, 101)], "ambiguous"),
    ({1: (100, 101)}, [(101, 102)], "unknown.*node"),
    ({999: (100, 101)}, [(100, 101)], "common.*edge"),
])
def test_refuses_ambiguous_or_unmapped_source_pairs(evaluator, inputs, tmp_path, source, route, message):
    inputs["representation"] = "node-pairs"
    inputs["source_cache"] = dump(tmp_path / "source.pkl.gz", {"edge_nodes": source})
    dump(inputs["synthetic_routes"], [route])
    with pytest.raises(ValueError, match=message):
        evaluator.evaluate_saved(**inputs)
    assert not inputs["out"].exists()


def test_disconnected_routes_keep_slots_without_filling(evaluator, inputs):
    dump(inputs["synthetic_routes"], [[1, 4], [1, 3], []])
    manifest = evaluator.evaluate_saved(**inputs)
    assert manifest["synthetic"]["disconnected_routes"] == 1
    values = json.loads((inputs["out"] / "metrics.json").read_text())
    assert values["RoadYield"] == pytest.approx(1 / 3)


def test_self_reference_does_not_force_all_metrics_to_one(evaluator, inputs):
    inputs["synthetic_routes"] = inputs["real_routes"]
    inputs["representation"] = "edge-records"
    manifest = evaluator.evaluate_saved(**inputs)
    values = json.loads((inputs["out"] / "metrics.json").read_text())
    assert manifest["self_reference"] is True
    assert values["RoadYield"] == pytest.approx(2 / 3)
    assert values["EdgeCPC"] == 1.0


def test_records_hashes_times_and_output_artifacts(evaluator, inputs):
    manifest = evaluator.evaluate_saved(**inputs)
    for key in ("real_routes", "synthetic_routes", "metric_cache"):
        assert manifest["inputs"][key]["sha256"] == hashlib.sha256(inputs[key].read_bytes()).hexdigest()
    assert manifest["metric_core"]["sha256"] == hashlib.sha256(Path(manifest["metric_core"]["path"]).read_bytes()).hexdigest()
    assert manifest["evaluator"]["sha256"] == hashlib.sha256(TOOL.read_bytes()).hexdigest()
    assert manifest["elapsed_seconds"] >= 0
    assert manifest["finished_at_utc"] >= manifest["started_at_utc"]
    assert {item["path"].rsplit("/", 1)[-1] for item in manifest["outputs"].values()} == {"metrics.json", "metrics.csv"}
    for item in manifest["outputs"].values():
        assert item["sha256"] == hashlib.sha256(Path(item["path"]).read_bytes()).hexdigest()


def test_refuses_overwriting_existing_evaluation(evaluator, inputs):
    inputs["out"].mkdir()
    marker = inputs["out"] / "keep.txt"
    marker.write_text("existing")
    with pytest.raises(FileExistsError):
        evaluator.evaluate_saved(**inputs)
    assert marker.read_text() == "existing"


def make_network(path, ids=(1, 2, 3, 4)):
    import geopandas as gpd
    from shapely.geometry import LineString
    nodes = {1: (100, 101), 2: (101, 102), 3: (101, 103), 4: (102, 100)}
    gpd.GeoDataFrame({"id": list(ids), "length_m": [10.0] * len(ids),
                     "source": [nodes[e][0] for e in ids], "target": [nodes[e][1] for e in ids]},
                    geometry=[LineString([(0, 0), (10, 0)])] * len(ids),
                    crs="EPSG:32650").to_file(path, driver="GeoJSON")
    return path


def test_network_adds_existing_five_shape_metrics_with_empty_denominator(evaluator, inputs, tmp_path):
    inputs["network"] = make_network(tmp_path / "network.geojson")
    evaluator.evaluate_saved(**inputs)
    values = json.loads((inputs["out"] / "metrics.json").read_text())
    assert len(values) == 24
    for metric in ("TotalLengthRetention", "BackboneLengthRetention", "ClosedLengthRetention",
                   "ClosedSegmentRetention", "RepeatedEdgeRetention"):
        assert values[metric] == pytest.approx(2 / 3)


def test_missing_network_lengths_refused_not_silently_zero(evaluator, inputs, tmp_path):
    inputs["network"] = make_network(tmp_path / "network.geojson", ids=(1, 2, 3))
    with pytest.raises(ValueError, match="missing.*length"):
        evaluator.evaluate_saved(**inputs)
    assert not inputs["out"].exists()


def test_physical_network_disconnect_is_not_hidden_by_legacy_merged_nodes(evaluator, inputs, tmp_path):
    import geopandas as gpd
    network = make_network(tmp_path / "network.geojson")
    frame = gpd.read_file(network)
    frame.loc[frame["id"] == 3, "source"] = 301
    frame.to_file(network, driver="GeoJSON")
    inputs["network"] = network
    dump(inputs["real_routes"], [{"accepted": True, "cpath": [1, 2]}, {"accepted": True, "cpath": [3]}])
    dump(inputs["synthetic_routes"], [[1, 3], []])
    manifest = evaluator.evaluate_saved(**inputs)
    values = json.loads((inputs["out"] / "metrics.json").read_text())
    assert values["RoadYield"] == 0.0
    assert manifest["synthetic"]["physical_disconnected_routes"] == 1
    assert manifest["synthetic"]["slots"] == 2
    assert manifest["real"]["valid_routes"] == 2


def test_reference_refuses_unknown_node_only_schema(evaluator, inputs):
    dump(inputs["real_routes"], [{"accepted": True, "node_sequence": [900, 901]}])
    with pytest.raises(ValueError, match="cpath"):
        evaluator.evaluate_saved(**inputs)
    assert not inputs["out"].exists()


def test_cli_runs_only_saved_input_evaluation(evaluator, inputs):
    command = [sys.executable, "-B", str(TOOL)]
    for key, value in inputs.items():
        command.extend(["--" + key.replace("_", "-"), str(value)])
    result = subprocess.run(command, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    manifest = json.loads((inputs["out"] / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["method"] == "Example"
    assert manifest["router"] == "Native"
    assert manifest["synthetic"]["slots"] == 3


def test_empty_real_reference_is_refused_not_given_placeholder_scores(evaluator, inputs):
    dump(inputs["real_routes"], [{"accepted": False, "cpath": []}])
    with pytest.raises(ValueError, match="no valid real"):
        evaluator.evaluate_saved(**inputs)
    assert not inputs["out"].exists()


def test_node_pair_source_disconnect_is_not_hidden_by_metric_node_merge(evaluator, inputs, tmp_path):
    inputs["representation"] = "node-pairs"
    inputs["source_cache"] = dump(tmp_path / "source.pkl.gz", {"edge_nodes": {1: (100, 101), 3: (301, 103)}})
    dump(inputs["synthetic_routes"], [[(100, 101), (301, 103)]])
    manifest = evaluator.evaluate_saved(**inputs)
    values = json.loads((inputs["out"] / "metrics.json").read_text())
    assert values["RoadYield"] == 0.0
    assert manifest["synthetic"]["source_disconnected_routes"] == 1


def test_incomplete_metric_labels_are_refused(evaluator, inputs):
    with gzip.open(inputs["metric_cache"], "rb") as handle:
        cache = pickle.load(handle)
    del cache["labels96"][11]
    dump(inputs["metric_cache"], cache)
    with pytest.raises(ValueError, match="labels96.*missing.*node"):
        evaluator.evaluate_saved(**inputs)
    assert not inputs["out"].exists()


def test_missing_branch_outdegree_is_refused_not_silently_zero(evaluator, inputs):
    with gzip.open(inputs["metric_cache"], "rb") as handle:
        cache = pickle.load(handle)
    del cache["outdegree"][11]
    dump(inputs["metric_cache"], cache)
    with pytest.raises(ValueError, match="outdegree.*missing.*node"):
        evaluator.evaluate_saved(**inputs)
    assert not inputs["out"].exists()
