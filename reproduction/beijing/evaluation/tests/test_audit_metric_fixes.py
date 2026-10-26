import ast
from collections import Counter, defaultdict
import math
from pathlib import Path
import types

import numpy as np
import pandas as pd
import pytest
from scipy.spatial.distance import jensenshannon

from evaluation import audit_metric_fixes as fixes
from plotting.plot_matrix import retain_numeric_cells, metric_display_name

LEGACY = Path(__file__).resolve().parents[2]/'legacy/evaluation'


def functions(relative, **extra):
    path = LEGACY/relative
    tree = ast.parse(path.read_text(encoding='utf-8'))
    nodes = [ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0)]
    nodes += [n for n in tree.body if isinstance(n, ast.FunctionDef)]
    module = types.ModuleType('audit_test_'+path.stem)
    module.__file__ = str(path)
    module.__dict__.update(np=np, math=math, Counter=Counter, defaultdict=defaultdict,
                           jensenshannon=jensenshannon, EARTH_KM=6371.0088, **extra)
    exec(compile(ast.fix_missing_locations(ast.Module(body=nodes,type_ignores=[])),str(path),'exec'),module.__dict__)
    return module


def test_hidden_suffix_no_longer_changes_prefix_tie_winner():
    road = functions('pipeline/evaluate_road_mining_tasks.py', graph_context=lambda: None)
    train = [[0,1,2,3,4],[0,1,2,8,9]]
    old = [road.retrieval_metrics(train,[x])['retrieval_top1_suffix_edge_jaccard'] for x in train]
    fixes.install_road_fixes(road)
    new = [road.retrieval_metrics(train,[x])['retrieval_top1_suffix_edge_jaccard'] for x in train]
    assert old == [.5,.5]
    assert new == [.5,0.]
    assert np.mean(new) == .25


def test_candidate_order_depends_only_on_prefix_and_training_ids():
    grams = [{(0,1),(1,2)},{(0,1),(1,2)}]
    assert fixes.blind_candidate_order({(0,1),(1,2)}, {1,0}, grams) == [0,1]
    with pytest.raises(ValueError):
        fixes.blind_candidate_order(set(),set(),[],0)


def test_lengths_keep_tail_and_have_real_only_shared_bins():
    stats = functions('pipeline/evaluate_kdd_revised_statistics.py')
    short = np.array([[0.,0.],[0.,.01]])
    long = np.array([[0.,0.],[0.,10.]])
    real = [short]*100
    result = fixes.length_statistics(real,[short]*99+[long],stats)
    assert result['real_counted'] == result['synthetic_counted'] == 100
    assert result['synthetic_overflow'] == 1
    assert result['path_length_jsd'] > 0
    assert result['edges_km'] == fixes.length_statistics(real,[long]*100,stats)['edges_km']
    assert fixes.length_statistics(real,[np.empty((0,2))],stats)['path_length_jsd'] is None


def test_empty_and_one_point_slots_are_retained():
    rows=fixes.preserve_slots({'trajectories':[[],[[1.,2.]],[[1.,2.],[3.,4.]]]})
    assert list(map(len,rows)) == [0,1,2]
    assert rows[0].shape == (0,2)
    with pytest.raises(ValueError):
        fixes.preserve_slots([[[math.nan,0.]]])


def test_normalized_continuation_law_and_no_negative_loss():
    c=Counter({2:1})
    p=[fixes.normalized_probability(c,x,{2,3}) for x in (2,3)]
    assert sum(p) == pytest.approx(1.)
    assert all(-math.log(x) >= 0 for x in p)
    assert fixes.normalized_probability(c,2,{2}) == 1.
    with pytest.raises(ValueError):
        fixes.normalized_probability(c,4,{2,3})


def test_auxiliary_nll_changes_but_continuation_hit_does_not():
    road=functions('pipeline/evaluate_road_mining_tasks.py',
                   graph_context=lambda: (None,{(0,1),(1,2),(2,3)},None,None))
    rows=[[0,1,2,3]]
    old=road.continuation_metrics(rows,rows)
    fixes.install_road_fixes(road)
    road.graph_context()
    new=road.continuation_metrics(rows,rows)
    assert old['continuation_nll'] < 0
    assert new['continuation_nll'] == 0
    assert old['continuation_hit_at_1'] == new['continuation_hit_at_1']


def test_dirvalid_does_not_rank_coordinate_pairs_as_complete_routes():
    x=fixes.dirvalid_fields({'directed_road_validity':.8},'coordinate_projection')
    assert x['directed_road_validity'] is None
    assert x['CoordinatePairValidity'] == .8
    y=fixes.dirvalid_fields({'directed_road_validity':1.,
        'coordinate_projection_directed_road_validity':.8},'derived_directed_routes')
    assert y['DirValidRoadObject'] == 1.
    assert y['CoordinatePairValidity'] == .8


def test_zero_is_numeric_and_missing_stays_missing():
    x=retain_numeric_cells(pd.DataFrame({'value':[0.,.3,0.,0.],
                                        'status':['ZERO','VALID','NA','MISSING']}))
    assert x['value'].iloc[0] == 0
    assert x['value'].iloc[1] == .3
    assert x['value'].iloc[2:].isna().all()
    assert 'relative retention' in metric_display_name('DestinationHit5')


def test_frozen_btf_and_family_definitions_are_not_replaced():
    core=functions('route_metric_core.py')
    cache=dict(edge_nodes={0:(0,1),1:(1,2),2:(1,3)},outdegree={0:1,1:2,2:0,3:0},
               **{'labels'+str(k):{i:i for i in range(4)} for k in (24,96,384)})
    a,b,plain=((0,1),(1,2)),((0,1),(1,3)),((0,1),)
    score=core.evaluate_routes([a,b],[a,plain],cache)
    assert score['BTF'] == 1 and score['RC-CPC'] == .5
    score=core.evaluate_routes([a,()],[a,a],cache)
    assert score['FamilyCPC'] == score['BTF'] == .5
    assert score['RC-CPC'] == 1
