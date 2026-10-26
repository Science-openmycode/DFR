from __future__ import annotations

import gzip
import hashlib
import json
import pickle
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pytest
from shapely.geometry import LineString

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import run as orchestrator


def dump(path, value):
    with gzip.open(path, "wb") as handle:
        pickle.dump(value, handle)


@pytest.fixture
def inputs(tmp_path):
    network = tmp_path / "network.shp"
    gpd.GeoDataFrame({"id": [7, 8], "source": [100, 101], "target": [101, 102]},
                    geometry=[LineString([(116, 39), (116.1, 39.1)]),
                              LineString([(116.1, 39.1), (116.2, 39.2)])], crs="EPSG:4326").to_file(network, index=False)
    routes, cache = tmp_path / "routes.pkl.gz", tmp_path / "cache.pkl.gz"
    dump(routes, [((1, 2), (2, 3)), ()])
    dump(cache, {"edge_nodes": {7: (1, 2), 8: (2, 3)}})
    manifest = tmp_path / "route_manifest.json"
    manifest.write_text(json.dumps({"M": "MTR-DFR", "native_dfr_rematched": False}), encoding="utf-8")
    return dict(route_file=routes, route_manifest=manifest, out_dir=tmp_path / "metrics",
                edge_cache=cache, public_network=network, source_cache=cache)


def test_legacy_nodes_resolve_by_edge_id_not_network_nodes(inputs):
    coordinate_file, count = orchestrator._stage_native_route_coordinates(**inputs)
    with coordinate_file.open("rb") as handle:
        rows = pickle.load(handle)
    assert count == 2
    np.testing.assert_array_equal(rows[0], [[39, 116], [39.1, 116.1], [39.2, 116.2]])
    assert rows[1].shape == (0, 2)
    sidecar = json.loads(coordinate_file.with_name("coordinates.pkl.manifest.json").read_text(encoding="utf-8"))
    assert sidecar["route_source"]["sha256"] == hashlib.sha256(inputs["route_file"].read_bytes()).hexdigest()
    assert sidecar["edge_cache"]["sha256"] == hashlib.sha256(inputs["edge_cache"].read_bytes()).hexdigest()
    assert sidecar["node_namespace_policy"] == "source-cache node pair -> unique edge ID -> public network ID geometry"
    decoded = Path(sidecar["decoded_edge_ids"]["path"])
    with gzip.open(decoded, "rb") as handle:
        assert pickle.load(handle) == [(7, 8), ()]


def test_network_aligned_mtnet_pairs_keep_correct_coordinates(inputs):
    dump(inputs["route_file"], [[(100, 101), (101, 102)], []])
    dump(inputs["edge_cache"], {"edge_nodes": {7: (100, 101), 8: (101, 102)}})
    coordinate_file, count = orchestrator._stage_native_route_coordinates(**inputs)
    with coordinate_file.open("rb") as handle:
        rows = pickle.load(handle)
    np.testing.assert_array_equal(rows[0], [[39, 116], [39.1, 116.1], [39.2, 116.2]])
    assert count == 2


@pytest.mark.parametrize(("cache", "routes", "message"), [
    ({7: (1, 2), 9: (1, 2), 8: (2, 3)}, [((1, 2), (2, 3))], "ambiguous"),
    ({7: (1, 2)}, [((1, 2), (2, 3))], "unknown.*pair"),
    ({7: (1, 2), 8: (4, 5)}, [((1, 2), (4, 5))], "disconnected"),
])
def test_unresolvable_source_pairs_fail_without_partial_coordinate_output(inputs, cache, routes, message):
    dump(inputs["edge_cache"], {"edge_nodes": cache})
    dump(inputs["route_file"], routes)
    with pytest.raises(ValueError, match=message):
        orchestrator._stage_native_route_coordinates(**inputs)
    assert not inputs["out_dir"].with_name("metrics__input").exists()


def test_duplicate_network_ids_are_refused_by_old_entrypoint(inputs):
    frame = gpd.read_file(inputs["public_network"])
    frame.at[1, "id"] = 7
    frame.to_file(inputs["public_network"], index=False)
    with pytest.raises(ValueError, match="duplicate.*edge"):
        orchestrator._stage_native_route_coordinates(**inputs)
    assert not inputs["out_dir"].with_name("metrics__input").exists()


def test_unbound_manifest_requires_explicit_source_cache(inputs):
    del inputs["source_cache"]
    with pytest.raises(ValueError, match="--source-cache"):
        orchestrator._stage_native_route_coordinates(**inputs)


def test_bound_manifest_validates_passed_cache_hash(inputs):
    digest = hashlib.sha256(inputs["edge_cache"].read_bytes()).hexdigest()
    inputs["route_manifest"].write_text(json.dumps({"edge_cache": {"sha256": digest}}), encoding="utf-8")
    del inputs["source_cache"]
    coordinate_file, count = orchestrator._stage_native_route_coordinates(**inputs)
    assert coordinate_file.is_file()
    assert count == 2


def test_wrong_bound_cache_hash_fails_without_geometry_staging(inputs):
    inputs["route_manifest"].write_text(json.dumps({"edge_cache_sha256": "0" * 64}), encoding="utf-8")
    with pytest.raises(ValueError, match="source.cache.*hash mismatch"):
        orchestrator._stage_native_route_coordinates(**inputs)
    assert not inputs["out_dir"].with_name("metrics__input").exists()


def test_different_source_and_road_scoring_caches_are_refused(inputs, tmp_path):
    other = tmp_path / "other.pkl.gz"
    dump(other, {"edge_nodes": {7: (100, 101), 8: (101, 102)}})
    inputs["source_cache"] = other
    with pytest.raises(ValueError, match="source.cache.*edge.cache"):
        orchestrator._stage_native_route_coordinates(**inputs)


def test_evaluate_cell_cli_exposes_explicit_source_cache(inputs):
    args = orchestrator.build_parser().parse_args([
        "evaluate-cell", "--dataset", "beijing", "--m", "MTR-DFR", "--r", "Origin",
        "--synthetic", "routes", "--real-reference", "real", "--osm-cache", "osm",
        "--out-dir", "metrics", "--source-cache", str(inputs["source_cache"]),
    ])
    assert args.source_cache == inputs["source_cache"]


@pytest.mark.parametrize("different", [False, True])
def test_coordinate_only_alias_requires_exact_directed_geometry(inputs, different):
    import pandas as pd
    frame = gpd.read_file(inputs["public_network"])
    alias = frame.iloc[[0]].copy()
    alias["id"] = 9
    if different:
        alias["geometry"] = [LineString([(116, 39), (116.05, 39.2), (116.1, 39.1)])]
    gpd.GeoDataFrame(pd.concat([frame, alias], ignore_index=True), crs=frame.crs).to_file(inputs["public_network"], index=False)
    dump(inputs["edge_cache"], {"edge_nodes": {7: (1, 2), 9: (1, 2), 8: (2, 3)}})
    if different:
        with pytest.raises(ValueError, match="ambiguous"):
            orchestrator._stage_native_route_coordinates(**inputs, allow_identical_geometry=True)
        return
    output, count = orchestrator._stage_native_route_coordinates(**inputs, allow_identical_geometry=True)
    assert count == 2
    np.testing.assert_array_equal(pickle.load(output.open("rb"))[0], [[39, 116], [39.1, 116.1], [39.2, 116.2]])
    record = json.loads(output.with_name("manifest.json").read_text())
    assert record["geometry_aliases"][0]["edge_ids"] == [7, 9]
    assert "decoded_edge_ids" not in record
    assert record["coordinate_only_edge_representatives"]["not_for_edge_identity_scoring"] is True
