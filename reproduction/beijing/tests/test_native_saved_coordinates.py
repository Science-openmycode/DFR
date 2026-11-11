import gzip
import hashlib
import json
import pickle

import geopandas as gpd
import numpy as np
import pytest
from shapely.geometry import LineString

from tools.stage_native_saved_coordinates import build


def fixture(tmp):
    network=tmp/'network.shp'
    gpd.GeoDataFrame({'id':[7],'source':[1],'target':[2]},
                     geometry=[LineString([(116,39),(116.1,39.1)])],crs='EPSG:4326').to_file(network)
    native=tmp/'native.pkl.gz'
    native.write_bytes(b'bound native generation artifact')
    routes=tmp/'synthetic_routes.pkl.gz'
    with gzip.open(routes,'wb') as f:
        pickle.dump([dict(source_index=0,accepted=True,cpath=[7]),
                     dict(source_index=1,accepted=False,cpath=[])],f)
    def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
    manifest=dict(classification='NATIVE_ROAD_REPRESENTATION_ONLY',rematched=False,
                  output_sha256=sha(routes),public_network_sha256=sha(network),native_sha256=sha(native))
    (tmp/'route_manifest.json').write_text(json.dumps(manifest))
    return routes,network,native


def test_native_view_preserves_geometry_slots_and_exact_road_binding(tmp_path):
    routes,network,native=fixture(tmp_path)
    result=build(routes,network,None,tmp_path/'view')
    with open(result['coordinates']['path'],'rb') as f: values=pickle.load(f)
    np.testing.assert_allclose(values[0],[[39,116],[39.1,116.1]])
    assert values[1].shape==(0,2)
    assert result['route_source']['path']==routes.as_posix()
    assert not result['rematched'] and not result['gap_filling']


def test_train_view_binds_the_native_generator_release_not_a_temporary_file(tmp_path):
    routes,network,native=fixture(tmp_path)
    result=build(routes,network,None,tmp_path/'view',native_source=native,bind_native_source=True)
    assert result['route_source']['path']==native.as_posix()
    assert result['routed_artifact']['path']==routes.as_posix()


def test_wrong_native_release_cannot_enter_native_provenance(tmp_path):
    routes,network,native=fixture(tmp_path)
    native.write_bytes(b'changed')
    with pytest.raises(ValueError,match='executed native release'):
        build(routes,network,None,tmp_path/'view',native_source=native,bind_native_source=True)

def frozen_fixture(tmp):
    routes,network,native=fixture(tmp)
    routes=routes.rename(tmp/'road_records.pkl.gz')
    (tmp/'route_manifest.json').unlink()
    def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
    with gzip.open(routes,'wb') as f:
        pickle.dump([dict(source_index=2,accepted=True,cpath=[7]),
                     dict(source_index=8,accepted=False,cpath=[])],f)
    (tmp/'source_indices.json').write_text('[2,8]')
    (tmp/'canonical_manifest.json').write_text(json.dumps(dict(
        schema='frozen-road-dataset-v1',status='FROZEN',trajectory_count=2,
        artifacts={'road_records.pkl.gz':sha(routes),'source_indices.json':sha(tmp/'source_indices.json')},network_sha256=sha(network))))
    return routes,network

def test_frozen_real_reference_uses_real_manifest_without_fake_native_provenance(tmp_path):
    routes,network=frozen_fixture(tmp_path)
    result=build(routes,network,None,tmp_path/'view')
    assert result['source_classification']=='FROZEN_REAL_GEOMETRY_REFERENCE'
    assert result['record_count']==2 and 'native_representation_manifest' not in result
    assert result['route_source']['path']==routes.as_posix()
    with open(result['coordinates']['path'],'rb') as f:values=pickle.load(f)
    np.testing.assert_allclose(values[0],[[39,116],[39.1,116.1]])
    assert values[1].shape==(0,2)

def test_frozen_real_source_mutation_is_rejected(tmp_path):
    routes,network=frozen_fixture(tmp_path)
    routes.write_bytes(b'changed')
    with pytest.raises(ValueError,match='binding changed'):
        build(routes,network,None,tmp_path/'view')

def test_real_reference_cannot_masquerade_as_native_generation(tmp_path):
    routes,network=frozen_fixture(tmp_path)
    with pytest.raises(ValueError,match='not a native generator'):
        build(routes,network,None,tmp_path/'view',native_source=routes,bind_native_source=True)

def test_frozen_source_index_mutation_rejected(tmp_path):
    routes,network=frozen_fixture(tmp_path)
    (tmp_path/'source_indices.json').write_text('[8,2]')
    with pytest.raises(ValueError,match='source-index binding changed'):
        build(routes,network,None,tmp_path/'view')
