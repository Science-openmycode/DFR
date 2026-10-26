"""Tiny generated fixtures exercise file plumbing, not a scientific experiment."""
import gzip
import json
import pickle
from pathlib import Path
from tools import collect_portable_sweeps as module


def test_all_diagnostic_stages_connect(tmp_path,monkeypatch):
    monkeypatch.setattr(module,'ROOT',tmp_path)
    def dump(p,obj):
        p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(obj),encoding='utf-8')
    def gz(p,obj):
        p.parent.mkdir(parents=True,exist_ok=True)
        with gzip.open(p,'wb') as f:pickle.dump(obj,f)
    real=tmp_path/'resources/dataset/road_records.pkl.gz'
    cache=tmp_path/'resources/metric_cache/metric_cache.pkl.gz'
    graph=tmp_path/'resources/network/network.shp';graph.parent.mkdir(parents=True);graph.write_bytes(b'fixture')
    gz(real,[{'accepted':True,'cpath':[1]}]*15730);gz(cache,{'edge_nodes':{1:(0,1)}})
    cells=[]
    for k in [96,384,768]:
        base=tmp_path/f'cell{k}';native=base/'native/MTR-DFR';run=native/'seed_42_length'
        raw=run/'road_routes.pkl.gz';gz(raw,[(0,1)]*15730)
        transcript=run/'dp_transcript.pkl.gz'
        noisy=[[0.]*k for _ in range(2)];noisy[0][0]=7865.;noisy[1][1]=7865.
        gz(transcript,{'endpoint':{'noisy_cells':noisy,'selected_cells':[[0,0],[1,1]],'fallback_counts':{'a':2}}})
        dump(run/'research_metadata.json',{'tail_states':{'single_edge_fallback':3}})
        dump(native.with_name('MTR-DFR.private_audit')/'input_lineage.json',{'status':'DONE','dataset':{'count':15730},'elapsed_seconds':1,
            'outputs':{str(p.relative_to(native)):module.sha(p) for p in run.iterdir()}})
        routes=base/'representation/synthetic_routes.pkl.gz';gz(routes,[])
        dump(routes.parent/'route_manifest.json',{'records':15730,'rematched':False,'output_sha256':module.sha(routes),'native_sha256':module.sha(raw)})
        for stage,metrics in [('road_scores',{m:.5 for m in ['BTF','RC-CPC','EdgeCPC','TurnCPC','FamilyCPC']}),
                              ('coordinate_scores',{'metrics':{'OD_jsd':.2,'path_length_jsd':.1}}),('road_tasks',{'metrics':{'NextRoadAcc':.4}})]:
            p=base/stage/'metrics.json';dump(p,metrics)
            meta={'outputs':{'metrics.json':module.sha(p)},'result_sha256':module.sha(p),'inputs':{}}
            dump(p.parent/'manifest.json',meta)
        physical=base/'physical';physical.mkdir();csv=physical/'results.csv';csv.write_text('method,EdgeF1\nfixture,0.7\n')
        dump(physical/'manifest.json',{'results_sha256':module.sha(csv),'inputs_sha256':{name:module.sha(p) for name,p in
             [('real_routes',real),('synthetic_routes',routes),('edge_cache',cache),('network',graph)]}})
        dump(tmp_path/f'resources/endpoint_partitions/partition{k}.json',{'labels':{'0':0,'1':1}})
        cells.append({'kind':'endpoint_diagnostic','name':f'k{k}','directory':f'cell{k}','value':k,'seed':42})
    plan=tmp_path/'plan.json';dump(plan,{'cells':cells});out=tmp_path/'summary'
    module.collect('endpoint_diagnostic',plan,out)
    report=json.loads((out/'endpoint_diagnostics.json').read_text())
    assert len(report['rows'])==3 and all(r['fine_noise_l1']==0 and r['fine_head_true_mass_fraction']==1 for r in report['rows'])
    manifest=json.loads((out/'manifest.json').read_text())
    assert manifest['outputs']['endpoint_diagnostics.json']==module.sha(out/'endpoint_diagnostics.json')
