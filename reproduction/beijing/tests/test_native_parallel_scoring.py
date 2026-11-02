import gzip
import importlib.util
import pickle
from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import LineString

from evaluate_road_tasks import road_task_records
from tools.convert_native_node_pairs import resolve_pairs, source_pairs, convert


def graph(*, bent=False, reversed_endpoints=False):
    line=LineString([(0,0),(1,0)])
    return gpd.GeoDataFrame(dict(id=[182790,589552],source=[121514,121514],
        target=[80485,80485 if not reversed_endpoints else 999]),
        geometry=[line,LineString([(0,0),(0,1),(1,0)]) if bent else line],crs=4326)


SOURCE={182790:(121514,80485),589552:(121514,80485)}
METRIC={182790:(100,200),589552:(100,200)}


def test_published_parallel_pair_has_same_policy_in_converter_and_scorer():
    frame=graph()
    pairs=resolve_pairs(SOURCE,METRIC,frame=frame)
    raw=[[(121514,80485)],[]]
    rows=convert(raw,pairs)
    assert pairs=={(121514,80485):182790}
    assert rows==convert(raw,source_pairs({'edge_nodes':SOURCE},frame))
    path=Path(__file__).resolve().parents[1]/'tools/evaluate_saved_roads.py'
    spec=importlib.util.spec_from_file_location('parallel_scoring',path)
    scorer=importlib.util.module_from_spec(spec);spec.loader.exec_module(scorer)
    roads,audit=scorer._convert(raw,'node-pairs',METRIC,SOURCE,SOURCE,'synthetic',pairs)
    assert roads==[((100,200),),()]
    assert audit['slots']==2 and audit['empty_routes']==1
    # Without geometry evidence the old strict private API still rejects.
    with pytest.raises(ValueError,match='ambiguous'):
        scorer._convert(raw,'node-pairs',METRIC,SOURCE,SOURCE,'synthetic')


@pytest.mark.parametrize('kwargs',[{'bent':True},{'reversed_endpoints':True}])
def test_different_physical_roads_are_not_selected(kwargs):
    with pytest.raises(ValueError,match='Ambiguous'):
        resolve_pairs(SOURCE,METRIC,frame=graph(**kwargs))


def test_different_metric_nodes_are_not_silently_merged():
    with pytest.raises(ValueError,match='metric endpoints'):
        resolve_pairs(SOURCE,{182790:(100,200),589552:(100,999)},frame=graph())


def test_no_geometry_proof_still_rejects():
    with pytest.raises(ValueError,match='missing public geometry proof'):
        resolve_pairs(SOURCE,METRIC)


def test_missing_shared_edge_is_not_guessed():
    with pytest.raises(ValueError,match='shared public edge'):
        resolve_pairs(SOURCE,{182790:(100,200)},frame=graph())


def test_road_tasks_resolve_the_same_physical_aliases(tmp_path):
    network=tmp_path/'network.gpkg';graph().to_file(network)
    rows=road_task_records([[(121514,80485)],[]],'node-pairs',METRIC,SOURCE,network)
    assert rows[0]['cpath']==[182790]
    assert len(rows)==2 and rows[1]['accepted'] is False


def test_unvisited_ambiguous_pair_does_not_block_a_release():
    assert resolve_pairs({**SOURCE,7:(1,2)}, {**METRIC,7:(10,20)},
                         required_pairs={(1,2)})=={(1,2):7}


def test_complete_saved_scorer_resolves_parallel_ids_and_preserves_denominator(tmp_path):
    from tools.evaluate_saved_roads import evaluate_saved
    frame=graph();frame['length_m']=100.
    network=tmp_path/'network.gpkg';frame.to_file(network)
    def save(name,value):
        path=tmp_path/name
        with gzip.open(path,'wb') as stream:pickle.dump(value,stream)
        return path
    cache={'edge_nodes':METRIC,'outdegree':{100:1,200:0},
           **{'labels'+str(k):{100:0,200:1} for k in (24,96,384)}}
    raw=[[(121514,80485)],[]]
    manifest=evaluate_saved(real_routes=save('real.gz',[dict(accepted=True,cpath=[182790])]),
        synthetic_routes=save('synthetic.gz',raw),metric_cache=save('cache.gz',cache),
        representation='node-pairs',method='MTR-DFR',router='Origin',out=tmp_path/'score',
        source_cache=save('source.gz',{'edge_nodes':SOURCE}),network=network)
    assert manifest['synthetic']['slots']==2
    assert manifest['synthetic']['valid_routes']==1
    assert manifest['synthetic']['empty_routes']==1
    assert manifest['rematched'] is False and manifest['gap_filling'] is False
    assert manifest['representation_resolver']['sha256']
