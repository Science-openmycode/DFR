from __future__ import annotations

import gzip
import hashlib
import importlib.util
import json
import pickle
from pathlib import Path

import geopandas as gpd
import numpy as np
import pytest
from shapely.geometry import LineString


TOOL = Path(__file__).resolve().parents[2] / "tools" / "stage_native_edge_coordinates.py"


def stage(**kwargs):
    assert TOOL.is_file(), "edge-ID geometry staging is not implemented"
    spec = importlib.util.spec_from_file_location("native_geometry_test", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.stage(**kwargs)


def save_routes(path, rows):
    with gzip.open(path, "wb") as handle:
        pickle.dump(rows, handle)


@pytest.fixture
def inputs(tmp_path):
    routes = tmp_path / "edge_ids.pkl.gz"
    save_routes(routes, [[7, 8], []])
    network = tmp_path / "network.shp"
    gpd.GeoDataFrame({"id": [7, 8], "source": [100, 101], "target": [101, 102]},
                    geometry=[LineString([(116, 39), (116.1, 39.1), (116.1, 39.1), (116.2, 39.2)]),
                              LineString([(116.2, 39.2), (116.3, 39.3)])],
                    crs="EPSG:4326").to_file(network, index=False)
    return {"routes": routes, "network": network, "out_dir": tmp_path / "stage"}


def staged_rows(result):
    with Path(result["coordinates"]["path"]).open("rb") as handle:
        return pickle.load(handle)


def test_ids_select_directed_geometry_and_remove_only_one_shared_join(inputs):
    result = stage(**inputs)
    rows = staged_rows(result)
    np.testing.assert_array_equal(rows[0], [[39, 116], [39.1, 116.1], [39.1, 116.1], [39.2, 116.2], [39.3, 116.3]])
    assert rows[1].shape == (0, 2)
    assert result["record_count"] == 2
    assert result["reason_counts"] == {"valid": 1, "empty_native_slot": 1}
    assert result["formal_output"] is False
    assert result["rematched"] is False


def test_missing_middle_edge_invalidates_whole_slot_without_partial_join(inputs):
    save_routes(inputs["routes"], [[7, 999, 8], [7], []])
    result = stage(**inputs)
    rows = staged_rows(result)
    assert [row.shape for row in rows] == [(0, 2), (4, 2), (0, 2)]
    assert result["reason_counts"]["missing_edge_id"] == 1
    assert result["invalid_slots"][0]["slot"] == 0
    assert result["invalid_slots"][0]["edge_id"] == 999


@pytest.mark.parametrize(("field", "value", "reason"), [
    ("source", 999, "network_disconnected"),
    ("geometry", None, "empty_geometry"),
    ("geometry", LineString([(116.21, 39.2), (116.3, 39.3)]), "geometry_disconnected"),
])
def test_bad_edge_or_connection_retains_empty_whole_slot(inputs, field, value, reason):
    frame = gpd.read_file(inputs["network"])
    frame.at[1, field] = value
    frame.to_file(inputs["network"], index=False)
    result = stage(**inputs)
    assert staged_rows(result)[0].shape == (0, 2)
    assert result["reason_counts"][reason] == 1


def test_reversed_edge_order_is_not_repaired(inputs):
    save_routes(inputs["routes"], [[8, 7]])
    result = stage(**inputs)
    assert staged_rows(result)[0].shape == (0, 2)
    assert result["reason_counts"]["network_disconnected"] == 1


def test_duplicate_edge_ids_fail_before_any_output(inputs):
    frame = gpd.read_file(inputs["network"])
    frame.at[1, "id"] = 7
    frame.to_file(inputs["network"], index=False)
    with pytest.raises(ValueError, match="duplicate.*edge"):
        stage(**inputs)
    assert not inputs["out_dir"].exists()


def test_parallel_directed_edges_keep_their_explicit_ids(inputs):
    frame = gpd.read_file(inputs["network"])
    frame.at[1, "source"] = 100
    frame.at[1, "target"] = 101
    frame.at[1, "geometry"] = LineString([(116, 39), (116.5, 39.5), (116.2, 39.2)])
    frame.to_file(inputs["network"], index=False)
    save_routes(inputs["routes"], [[8]])
    np.testing.assert_array_equal(staged_rows(stage(**inputs))[0], [[39, 116], [39.5, 116.5], [39.2, 116.2]])


def test_hashes_all_network_sidecars_and_legacy_derivation_contract(inputs, tmp_path):
    cache = tmp_path / "cache.pkl.gz"
    save_routes(cache, {"edge_nodes": {7: (1, 2), 8: (2, 3)}})
    result = stage(**inputs, edge_cache=cache)
    assert result["schema"] == "road-route-coordinate-derivation-v1"
    assert result["edge_cache"]["sha256"] == hashlib.sha256(cache.read_bytes()).hexdigest()
    expected = {p.name for p in inputs["network"].parent.glob("network.*")}
    actual = {Path(item["path"]).name for item in result["network_files"]}
    assert expected == actual
    for item in result["network_files"]:
        assert item["sha256"] == hashlib.sha256(Path(item["path"]).read_bytes()).hexdigest()
    sidecar = inputs["out_dir"] / "coordinates.pkl.manifest.json"
    assert json.loads(sidecar.read_text(encoding="utf-8"))["record_count"] == 2


def test_refuses_existing_staging_directory(inputs):
    inputs["out_dir"].mkdir()
    with pytest.raises(FileExistsError):
        stage(**inputs)


def test_noninteger_edge_id_is_not_coerced_or_skipped(inputs):
    save_routes(inputs["routes"], [[7.5, 8]])
    result = stage(**inputs)
    assert staged_rows(result)[0].shape == (0, 2)
    assert result["reason_counts"]["invalid_route_schema"] == 1
