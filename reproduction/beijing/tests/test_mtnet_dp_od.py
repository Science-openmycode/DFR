"""Independent budget and frozen-population tests; not formal city scores."""
import json
import importlib.util
from pathlib import Path
import numpy as np
import pytest
from mtnet_dp_od import engine,binding

ROOT=Path(__file__).resolve().parents[1]

def test_original_accounting_and_fixed_time_transform(tmp_path):
    m=engine(tmp_path,'fixture');sigma=m.sigma_for_budget()
    assert m.epsilon(sigma)<=1.+1e-12 and m.epsilon(sigma*.99)>1.
    adj=np.asarray([[3,3,0],[2,3,0],[3,3,0],[3,3,0]])
    row=m.tensor_row([1,2],[100.,2.,3.],adj)
    assert row is not None and np.allclose(row[2][:2],[3/6000,0])
    assert m.tensor_row([1],[0,6000],adj) is None
    assert m.tensor_row([1]*21,[0]*22,adj) is None
    assert m.tensor_row([1],[0,float('nan')],adj) is None

def test_budget_is_not_ordinary_mtnet_plus_extra_od(tmp_path):
    config=tmp_path/'c.json';config.write_text(json.dumps({'epsilon':2.0}))
    with pytest.raises(ValueError,match='fixed at total'):binding(config,tmp_path,tmp_path/'edges','full','cpu')

def test_legacy_numerical_helpers_unchanged(tmp_path):
    # Frozen expected result covers the original replacement-accountant formula.
    m=engine(tmp_path,'fixture')
    orders=np.r_[np.arange(1.1,32,.1),np.arange(32,513)]
    for sigma in [10,30,60]:
        expected=float(np.min(30*2*orders/sigma**2+np.log(1e5)/(orders-1)))
        assert m.epsilon(sigma)==expected

def test_sources_have_no_city_population_or_edge_count_constant():
    text=(ROOT/'vendor/mtnet/dp_od_variant.py').read_text()
    assert 'assert len(valid)==594494' not in text
    assert 'assert len(raw) == 15730' not in text
    assert 'DATASET = None' in text

def test_explicit_population_and_private_storage(tmp_path):
    m=engine(tmp_path,'porto-test')
    assert m.DATASET=='porto-test' and m.HERE==tmp_path
    assert m.epsilon(m.sigma_for_budget())+.4<=1.4+1e-12

def test_no_normal_model_or_other_population_generation(tmp_path):
    m=engine(tmp_path,'porto');release=tmp_path/'release_full';release.mkdir()
    (release/'model.pt').write_bytes(b'not-a-model')
    meta=dict(status='COMPLETE',model_sha256=m.sha(release/'model.pt'),dataset_id='beijing',population='full',public_slots=10,epsilon_model=1.,epsilon_od=.4,updates=30)
    (release/'training_manifest.json').write_text(json.dumps(meta))
    with pytest.raises(ValueError,match='independent'):m.generate({'public_slots':10},'full')

def test_full_preparation_cannot_be_used_as_training_population(tmp_path):
    config=tmp_path/'c.json';config.write_text(json.dumps({'epsilon':1.4,'slots':10,'train_slots':8,'frozen_dataset_id':'city'}))
    (tmp_path/'full_preparation_manifest.json').write_text(json.dumps(dict(dataset_id='city',input_count=10,evaluation_scope='full_corpus')))
    with pytest.raises(ValueError,match='scope differs'):binding(config,tmp_path,tmp_path/'edges','train','cpu')

def test_public_graph_uses_city_counts_and_minimum_parallel_length(tmp_path):
    import gzip,pickle
    m=engine(tmp_path,'city');cache=tmp_path/'cache.gz';edges=tmp_path/'public.gz'
    with gzip.open(cache,'wb') as f:pickle.dump({'labels24':{100:0,200:1,300:2},'edge_nodes':{10:(100,200),11:(100,200),20:(200,300)}},f)
    with gzip.open(edges,'wt') as f:
        for e,u,v,w in [(10,100,200,1),(11,100,200,5),(20,200,300,2)]:
            f.write(json.dumps(dict(edge_id=str(e),u=str(u),v=str(v),length_m=w))+'\n')
    c=dict(dataset_id='city',cache=str(cache),public_edges=str(edges),bindings={str(p):m.sha(p) for p in [cache,edges]})
    m.graph(c)
    assert np.load(tmp_path/'public_graph/distances.npy').shape==(24,3)
    assert np.array_equal(np.load(tmp_path/'public_graph/distances.npy')[2],[3,2,0])

def test_add_application_release_preserves_old_bindings(tmp_path):
    from tools.add_application_release import extend
    from evaluation.applications.metrics import digest
    for name in ['edges','questions','region','real']:(tmp_path/name).write_text('fixture')
    cfg=dict(public_edges='edges',questions='questions',region='region',resources='resources',slots=2,dataset_id='city',methods=[dict(name='Real',slots='real',sha256=digest(tmp_path/'real'))])
    (tmp_path/'base.json').write_text(json.dumps(cfg));slots=tmp_path/'variant/slots.jsonl.gz';slots.parent.mkdir();slots.write_bytes(b'fixture')
    manifest=dict(status='COMPLETE',slots=2,public_edges_sha256=digest(tmp_path/'edges'),output_sha256=digest(slots))
    (slots.parent/'manifest.json').write_text(json.dumps(manifest))
    result=extend(tmp_path/'base.json',slots,'MTNet_DP_OD_coarse24',tmp_path/'nested/new.json')
    assert result['methods'][0]['sha256']==cfg['methods'][0]['sha256']
    assert result['methods'][0]['slots']==str((tmp_path/'real').resolve())
    assert json.loads((tmp_path/'base.json').read_text())==cfg
    manifest['public_edges_sha256']='other city';(slots.parent/'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match='graph'):extend(tmp_path/'base.json',slots,'variant',tmp_path/'bad.json')

def test_readme_contains_all_independent_variant_stages():
    text=(ROOT.parents[1]/'README_CN.md').read_text(encoding='utf-8')
    for stage in ['prepare','graph','train','generate']:assert 'mtnet_dp_od.py '+stage in text
    assert '--population train --out results/mtnet_dp_od/train' in text
    assert 'tools/add_application_release.py' in text
    handoff=(ROOT/'tools/check_readme_handoff.py').read_text('utf-8')
    for name in ['mtnet_dp_od.py','vendor/mtnet/dp_od_variant.py','tools/add_application_release.py']:
        assert name in handoff and (ROOT/name).is_file()

def test_release_training_metadata_excludes_private_runtime_and_counts(tmp_path):
    import inspect
    source=inspect.getsource(engine(tmp_path,'city').train)
    release_metadata=source.split("dump(release/'training_manifest.json'",1)[1]
    assert 'active_private' not in release_metadata
    assert 'seconds=' not in release_metadata
    assert 'gpu_rng' not in release_metadata
