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
    result=build(routes,network,None,tmp_path/'view',native_source=native,for_tstr=True)
    assert result['route_source']['path']==native.as_posix()
    assert result['routed_artifact']['path']==routes.as_posix()


def test_wrong_native_release_cannot_enter_strict_tstr(tmp_path):
    routes,network,native=fixture(tmp_path)
    native.write_bytes(b'changed')
    with pytest.raises(ValueError,match='executed native release'):
        build(routes,network,None,tmp_path/'view',native_source=native,for_tstr=True)
