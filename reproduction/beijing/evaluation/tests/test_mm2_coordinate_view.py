import gzip
import hashlib
import json
import pickle
from pathlib import Path

import geopandas as gpd
import numpy as np
import pytest
from shapely.geometry import LineString

from tools.stage_routed_coordinates import stage
from prepare_remote_tstr import parse_cell


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fixture(tmp_path):
    m = tmp_path/'measurement.pkl'
    m.write_bytes(pickle.dumps([np.array([[0., 0.], [1., 1.]])]*2))
    network = tmp_path/'network.shp'
    gpd.GeoDataFrame({'id':[7], 'source':[1], 'target':[2]},
        geometry=[LineString([(116.,39.), (116.1,39.1)])], crs='EPSG:4326').to_file(network)
    cache = tmp_path/'cache.pkl'
    cache.write_bytes(pickle.dumps({'edge_nodes':{7:(1,2)}}))
    routes = tmp_path/'routes.pkl.gz'
    with gzip.open(routes,'wb') as f:
        pickle.dump([{'source_index':0,'accepted':True,'cpath':[7]},
                     {'source_index':1,'accepted':False,'cpath':[]}],f)
    manifest = tmp_path/'route_manifest.json'
    meta = dict(router='MM2-MDP',status='VALID',raw_source_used=False,records=2,
        measurement=str(m),measurement_sha256=digest(m),output_sha256=digest(routes),
        public_edge_cache_sha256=digest(cache),public_raw_node_connectivity_checked=True,
        public_edge_nodes_sha256='a'*64)
    manifest.write_text(json.dumps(meta))
    return dict(routes=routes,manifest=manifest,network=network,edge_cache=cache,
                out_dir=tmp_path/'view',expected_mm2_network_sha256=digest(network))


def test_mm2_explicit_network_keeps_r_geometry_and_all_slots(tmp_path):
    args=fixture(tmp_path); before=Path(args['manifest']).read_bytes()
    result=stage(**args)
    rows=pickle.loads(Path(result['coordinates']['path']).read_bytes())
    np.testing.assert_allclose(rows[0],[[39.,116.],[39.1,116.1]])
    assert rows[1].shape==(0,2)
    assert result['record_count']==2 and result['rematched'] is False
    assert result['route_source']['sha256']==digest(tmp_path/'measurement.pkl')
    assert result['routed_artifact']['sha256']==digest(args['routes'])
    assert Path(args['manifest']).read_bytes()==before
    assert parse_cell('DPStd/MM2-MDP')==('DPStd','MM2-MDP')


@pytest.mark.parametrize('bad',['missing_network','wrong_network','cache','raw_evidence','index'])
def test_mm2_boundary_rejections(tmp_path,bad):
    args=fixture(tmp_path)
    meta=json.loads(Path(args['manifest']).read_text())
    if bad=='missing_network':args['expected_mm2_network_sha256']=None
    if bad=='wrong_network':args['expected_mm2_network_sha256']='0'*64
    if bad=='cache':meta['public_edge_cache_sha256']='0'*64
    if bad=='raw_evidence':meta['public_raw_node_connectivity_checked']=False
    if bad=='index':meta['records']=3
    Path(args['manifest']).write_text(json.dumps(meta))
    with pytest.raises(ValueError):stage(**args)
    assert not args['out_dir'].exists()
