"""Controls are generated, not read from private author directories."""
from types import SimpleNamespace
import numpy as np
import pytest
from prepare_endpoint_controls import generate_routes,check_boundary
from tools.endpoint_control_core import random_route

def router():
    import networkx as nx
    lengths={(-1,0):1,(0,1):1,(0,2):1,(1,3):1,(2,3):1,(3,4):1,(5,6):1}
    graph=nx.DiGraph()
    for (u,v),w in lengths.items():graph.add_edge(u,v,weight=w)
    def path(s,d):
        if s==d:return (s,)
        try:nodes=nx.shortest_path(graph,s[1],d[0],weight='weight')
        except nx.NetworkXNoPath:return ()
        return (s,)+tuple(zip(nodes,nodes[1:]))+(d,)
    return SimpleNamespace(length=lengths,outgoing={u:[e for e in lengths if e[0]==u] for u,v in lengths},path=path)

def test_random_and_shortest_endpoints_and_empty_slots():
    pairs=[((-1,0),(3,4))]*30+[((5,6),(3,4)),((3,4),(3,4))]
    a,b,counts=generate_routes(router(),pairs,42)
    assert len(a)==len(b)==32 and counts=={'valid':31,'unreachable':1}
    assert a[-2]==b[-2]==() and a[-1]==b[-1]==((3,4),)
    assert all(check_boundary(p,*ep) for p,ep in zip(a,pairs) if p)
    assert len(set(a[:30]))==2
    assert generate_routes(router(),pairs,42)==(a,b,counts)

def test_no_single_edge_false_destination_fallback():
    r=router();r.path=lambda s,d:(s,)
    with pytest.raises(ValueError,match='did not reach'):generate_routes(r,[((-1,0),(3,4))],42)

def test_unknown_endpoint_rejected():
    with pytest.raises(ValueError,match='Unknown endpoint'):generate_routes(router(),[((10,11),(3,4))],42)

def test_legacy_random_choice_is_unchanged():
    r=router();index={v:i for i,v in enumerate([-1,0,1,2,3,4,5,6])}
    dist=np.array([3,2,1,1,0,np.inf,np.inf,np.inf])
    a,b,_=generate_routes(r,[((-1,0),(3,4))]*20,42)
    assert a==[random_route(r,dist,index,(-1,0),(3,4),42,i) for i in range(20)]

def test_readme_contains_generation_before_adaptation():
    from pathlib import Path
    text=(Path(__file__).resolve().parents[3]/'README_CN.md').read_text('utf-8')
    assert text.index('prepare_endpoint_controls.py')<text.index('--input $SameEndpointRandomRoutes')
    assert 'Read-Host "输入同端点随机路线' not in text

@pytest.mark.parametrize('change,error',[
    ({'status':'FAILED'},'has not completed'),
    ({'epsilon':2.0},'privacy budget'),
    ({'dataset':{'dataset_id':'porto-instead-of-beijing'}},'another dataset'),
    ({'network_sha256':'wrong'},'public resource'),
])
def test_source_binding_rejected_before_replay(tmp_path,change,error,monkeypatch):
    import json
    import prepare_endpoint_controls as entry
    cfg={'dataset':'beijing','frozen_dataset_id':'test','epsilon':1.4,'paths':{'network':str(tmp_path/'network'),'metric_cache':str(tmp_path/'cache')}}
    for name in ('network','cache'):(tmp_path/name).write_bytes(b'fixture')
    audit={'status':'DONE','epsilon':1.4,'dataset':{'dataset_id':'test'},'network_sha256':entry.sha(tmp_path/'network'),'edge_cache_sha256':entry.sha(tmp_path/'cache')}
    audit.update(change);(tmp_path/'lineage').write_text(json.dumps(audit));(tmp_path/'manifest.json').write_text('{}')
    monkeypatch.setattr(entry,'load_config',lambda *args:cfg)
    monkeypatch.setattr(entry,'replay',lambda *args:pytest.fail('Must reject before replay'))
    with pytest.raises(ValueError,match=error):entry.prepare(tmp_path/'config',tmp_path,tmp_path/'lineage',tmp_path/'out')
    assert not (tmp_path/'out').exists()
