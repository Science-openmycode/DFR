import gzip
import hashlib
import json
import pickle
from pathlib import Path
import pytest
from tools.coordinate_resource_binding import coordinate_resources


def setup(tmp_path):
    paths = {}
    for key in ('edge_cache', 'metric_cache', 'mm2_edge_cache', 'network', 'mm2_public_edge_nodes'):
        file = tmp_path/key
        file.write_bytes(key.encode())
        paths[key] = file.name
    paths['prepared'] = 'prepared'
    (tmp_path/'prepared').mkdir()
    expected = hashlib.sha256((tmp_path/'network').read_bytes()).hexdigest()
    (tmp_path/'prepared/canonical_manifest.json').write_text(json.dumps({'network_sha256': expected}))
    meta = {'router': 'MM2-MDP', 'raw_source_used': False,
            'public_edge_cache_sha256': hashlib.sha256((tmp_path/'mm2_edge_cache').read_bytes()).hexdigest(),
            'public_edge_nodes_sha256': hashlib.sha256((tmp_path/'mm2_public_edge_nodes').read_bytes()).hexdigest()}
    manifest = tmp_path/'route_manifest.json'
    manifest.write_text(json.dumps(meta))
    return {'paths': paths}, manifest, expected


def test_exact_mm2_resources_and_default_router(tmp_path):
    c, m, expected = setup(tmp_path)
    cache, options = coordinate_resources(c, tmp_path, 'MM2-MDP', m)
    assert cache == tmp_path/'mm2_edge_cache'
    assert options == {'expected_mm2_network_sha256': expected}
    assert coordinate_resources(c, tmp_path, 'Nearest') == (tmp_path/'edge_cache', {})


@pytest.mark.parametrize('key', ['mm2_edge_cache', 'mm2_public_edge_nodes', 'network'])
def test_changed_resources_rejected(tmp_path, key):
    c, m, _ = setup(tmp_path)
    (tmp_path/key).write_bytes(b'changed')
    with pytest.raises(ValueError):
        coordinate_resources(c, tmp_path, 'MM2-MDP', m)


@pytest.mark.parametrize('via_cli', [False, True])
def test_mm2_view_preserves_slots_and_geometry(tmp_path, via_cli):
    import geopandas as gpd
    import numpy as np
    from shapely.geometry import LineString
    from tools.stage_routed_coordinates import stage
    c, m, _ = setup(tmp_path)
    network = tmp_path/'public.shp'
    gpd.GeoDataFrame({'id':[7], 'source':[1], 'target':[2]},
                    geometry=[LineString([(116,39), (116.1,39.1)])], crs='EPSG:4326').to_file(network)
    c['paths']['network'] = network.name
    (tmp_path/'prepared/canonical_manifest.json').write_text(json.dumps({'network_sha256':hashlib.sha256(network.read_bytes()).hexdigest()}))
    measurement = tmp_path/'measurement.pkl'
    measurement.write_bytes(pickle.dumps([np.array([[0.,0.],[0.,1.]]), np.empty((0,2))]))
    routes = tmp_path/'routes.pkl.gz'
    with gzip.open(routes,'wb') as f:
        pickle.dump([{'source_index':0,'accepted':True,'cpath':[7]},
                     {'source_index':1,'accepted':False,'cpath':[]}], f)
    meta=json.loads(m.read_text())
    meta.update(measurement=str(measurement), measurement_sha256=hashlib.sha256(measurement.read_bytes()).hexdigest(),
                output_sha256=hashlib.sha256(routes.read_bytes()).hexdigest(),
                status='VALID', public_raw_node_connectivity_checked=True, records=2)
    m.write_text(json.dumps(meta))
    cache, options=coordinate_resources(c,tmp_path,'MM2-MDP',m)
    if via_cli:
        import subprocess
        import sys
        root=Path(__file__).resolve().parents[1]
        c['paths']={k:str(tmp_path/v) for k,v in c['paths'].items()}
        config=tmp_path/'config.json'
        config.write_text(json.dumps(c))
        process=subprocess.run([sys.executable,str(root/'tools/stage_bound_coordinates.py'),
            '--config',str(config),'--routes',str(routes),'--measurement',str(measurement),
            '--out',str(tmp_path/'view')],capture_output=True,text=True)
        assert process.returncode == 0, process.stderr
        receipt=json.loads(process.stdout.strip().splitlines()[-1])
        assert receipt['mode']=='representation_only_no_new_routes'
        result=json.loads((tmp_path/'view/manifest.json').read_text(encoding='utf-8'))
    else:
        result=stage(routes,m,network,tmp_path/'view',measurement=measurement,edge_cache=cache,**options)
    arrays=pickle.loads(Path(result['coordinates']['path']).read_bytes())
    np.testing.assert_allclose(arrays[0],[[39,116],[39.1,116.1]])
    assert arrays[1].shape == (0,2)
    assert result['record_count']==2
