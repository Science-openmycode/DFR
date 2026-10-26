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

ROOT = Path(__file__).resolve().parents[2]


def tool():
    spec = importlib.util.spec_from_file_location('routed_view', ROOT / 'tools/stage_routed_coordinates.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_view_uses_routed_geometry_not_original_coordinates(tmp_path):
    measurement = tmp_path / 'measurement.pkl'
    measurement.write_bytes(pickle.dumps([np.array([[0., 0.], [0., 1.]]), np.array([[0., 0.], [0., 1.]])]))
    routes = tmp_path / 'synthetic_routes.pkl.gz'
    with gzip.open(routes, 'wb') as stream:
        pickle.dump([{'accepted': True, 'cpath': [7]}, {'accepted': False, 'connected': False, 'cpath': [7]}], stream)
    route_manifest = tmp_path / 'route_manifest.json'
    route_manifest.write_text(json.dumps({'measurement': str(measurement), 'measurement_sha256': hashlib.sha256(measurement.read_bytes()).hexdigest(), 'status': 'VALID', 'router': 'STMatch', 'raw_source_used': False}))
    network = tmp_path / 'network.shp'
    gpd.GeoDataFrame({'id': [7], 'source': [1], 'target': [2]}, geometry=[LineString([(116,39), (116.1,39.1)])], crs='EPSG:4326').to_file(network)
    meta = json.loads(route_manifest.read_text())
    meta.update(router='Nearest', output_sha256=hashlib.sha256(routes.read_bytes()).hexdigest(), public_network_sha256=hashlib.sha256(network.read_bytes()).hexdigest())
    route_manifest.write_text(json.dumps(meta))
    bad = dict(meta, public_network_sha256='0'*64)
    route_manifest.write_text(json.dumps(bad))
    with pytest.raises(ValueError, match='network'):
        tool().stage(routes, route_manifest, network, tmp_path / 'bad_view')
    route_manifest.write_text(json.dumps(dict(meta, output_sha256=None)))
    with pytest.raises(ValueError, match='route hash'):
        tool().stage(routes, route_manifest, network, tmp_path / 'bad_view')
    route_manifest.write_text(json.dumps(meta))
    result = tool().stage(routes, route_manifest, network, tmp_path / 'view')
    rows = pickle.loads(Path(result['coordinates']['path']).read_bytes())
    np.testing.assert_allclose(rows[0], [[39.,116.], [39.1,116.1]])
    assert rows[1].shape == (0,2)
    assert result['route_source']['sha256'] == hashlib.sha256(measurement.read_bytes()).hexdigest()
    assert result['routed_artifact']['sha256'] == hashlib.sha256(routes.read_bytes()).hexdigest()


def test_modified_measurement_rejected_before_geometry(tmp_path):
    measurement = tmp_path / 'measurement.pkl'
    measurement.write_bytes(b'changed')
    manifest = tmp_path / 'route_manifest.json'
    manifest.write_text(json.dumps({'measurement': str(measurement), 'measurement_sha256': '0'*64, 'status': 'VALID', 'router': 'FMM', 'raw_source_used': False}))
    with pytest.raises(ValueError, match='measurement'):
        tool().stage(tmp_path / 'roads.pkl.gz', manifest, tmp_path / 'network.shp', tmp_path / 'view')
