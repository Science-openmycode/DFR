import csv
import json
import pickle
from pathlib import Path
import numpy as np
import pytest
from tools.record_native_execution import record
from tools.k_diagnostics import endpoint_diagnostics,paired_summary
from tools.collect_frozen_matrix import merge_collections,sha
from tools import prepare_dpmm_train_evaluation as dpmm
from tools import finalize_mtnet_lineage as mtnet

ROOT=Path(__file__).resolve().parents[1]
def save(p,data):
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(data),encoding='utf-8');return p


def test_k_paired_values_match_original_all_36_groups():
    with (ROOT/'reference_results/k/scores.csv').open(encoding='utf-8-sig') as f:rows=list(csv.DictReader(f))
    for r in rows:
        for k in r:
            if k in ('diagnostic','reused'):r[k]=r[k]=='True'
            elif k in ('k','seed'):r[k]=int(r[k])
            else:r[k]=float(r[k])
    original=json.loads((ROOT/'reference_results/k/summary.json').read_text())
    assert json.loads(json.dumps(paired_summary(rows)))==original


def test_endpoint_original_arithmetic():
    real=[((0,1),(1,2)),((1,2),),()]
    ep={'endpoint':{'noisy_cells':[[.6,.3],[.2,.8]],'selected_cells':[[0,0],[1,1]],'fallback_counts':{'a':3,'b':2}}}
    d=endpoint_diagnostics(real,{0:0,1:1,2:1},2,ep,{'tail_states':{'single_edge_fallback':7}})
    assert d['fine_head_true_mass_fraction']==.75
    assert d['fine_noise_l1']==pytest.approx(.7)
    assert d['endpoint_fallbacks']==5 and d['public_shortest_fallbacks']==7
    with pytest.raises(ValueError):endpoint_diagnostics(real,{0:0,1:1,2:1},3,ep,{'tail_states':{}})


def test_matrix_merge_preserves_missing_zero_and_rejects_conflict():
    base=dict(row='DPMM',column='BTF',value=None,status='MISSING',result='')
    real=dict(base,value=0,status='ZERO',result='new.json')
    assert merge_collections([[base],[real]])==[real]
    with pytest.raises(ValueError):merge_collections([[real],[dict(real,value=.5)]])


def test_dpmm_direct_execution_to_staged_lineage(tmp_path,monkeypatch):
    # Miniature interface fixture, NOT a regenerated DPMM experiment.
    monkeypatch.chdir(tmp_path);monkeypatch.setattr(dpmm,'ROOT',tmp_path)
    train=tmp_path/'train';train.write_text('train');test=tmp_path/'test';test.write_text('test')
    audit=save(tmp_path/'split.json',dict(schema='verified_disjoint_split_v1',status='passed',all_source_indices_used_once=True,
        train_sha256=sha(train),test_sha256=sha(test),train_count=2,test_count=1))
    cfg=save(tmp_path/'config.json',dict(paths=dict(train='train',test='test',split_audit='split.json'),train_slots=2,test_slots=1,frozen_dataset_id='fixture',epsilon=1.4))
    valid=save(tmp_path/'validation.json',dict(complete=True,passed=True,protocol='accelerated-only-process-validation-v1',
        tested_records=60,target_records=60,sixty_record_validation={'results':[{'index':i} for i in range(60)]},
        slow_reference_executed=False,population='train',input_sha256=sha(train),input_count=2,dataset_id='fixture',public_osm_sha256='osm',recommended_workers=3,
        adapter_sha256='adapter',optimization_sha256='opt',public_parameters={'epsilon':1.4}))
    doc=tmp_path/'run.md';doc.write_text('```powershell\n.venv/Scripts/python.exe synthesize_dpmm.py --split train --out generated\n```\n',encoding='utf-8')
    output=Path('generated');ledger=tmp_path/'receipt.jsonl'
    record('start',doc,output,ledger)
    output.mkdir();(output/'dpmm.pkl').write_bytes(pickle.dumps([np.array([[1.,2.],[2.,3.]])]))
    save(output/'dpmm.json',dict(input_count=2,output_count=1,failed_count=1,released_input_indices=[0]))
    execution=dict(status='DONE',population='train',input_count=2,dataset_id='fixture',input_sha256=sha(train),rematched=False,
        validation_sha256=sha(valid),osm_sha256='osm',workers=3,adapter_sha256='adapter',optimizer_sha256='opt',privacy_scope='fixture',
        outputs={n:sha(output/n) for n in ('dpmm.pkl','dpmm.json')})
    save(output/'new_dataset_execution.json',execution)
    record('finish',doc,output,ledger,0)
    r=dpmm.prepare(output,cfg,ledger,doc,valid,tmp_path/'view')
    assert r['outputs']['coordinates.pkl']==sha(tmp_path/'view/coordinates.pkl')
    slots=pickle.loads((tmp_path/'view/coordinates.pkl').read_bytes())
    assert len(slots)==2 and slots[1].shape==(0,2)
    with pytest.raises(ValueError):record('finish',doc,output,ledger,0)


def test_failed_generation_never_verified(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path);doc=tmp_path/'run.md'
    doc.write_text('```\n.venv/Scripts/python.exe synthesize_dpmm.py --split train --out out\n```\n',encoding='utf-8')
    ledger=tmp_path/'log.jsonl';record('start',doc,Path('out'),ledger)
    with pytest.raises(RuntimeError):record('finish',doc,Path('out'),ledger,7)
    assert [json.loads(s)['phase'] for s in ledger.read_text().splitlines()]==['start','finish']


def test_mtnet_documented_layout_to_lineage(tmp_path,monkeypatch):
    # Preparation validation has its own tests; exercise new receipt/layout I/O.
    monkeypatch.setattr(mtnet,'validate_training_preparation',lambda *args:None)
    directory=tmp_path/'部署 空格';directory.mkdir()
    prep=save(tmp_path/'prep.json',{'split_binding':{'train_sha256':'train','test_sha256':'test'}})
    config=save(tmp_path/'cfg.json',{'paths':{'prepared':'.'},'frozen_dataset_id':'fixture','train_slots':2})
    save(directory/'deployment_binding.json',dict(evaluation_scope='strict_tstr',dataset_id='fixture',public_slot_count=2,
        split_binding={'train_sha256':'train','test_sha256':'test'},preparation_manifest_sha256=sha(prep),files={'train_native_mtnet_dpsgd_paper.py':'core'}))
    model=directory/'trained/model.pt';model.parent.mkdir();model.write_bytes(b'model')
    save(directory/'trained/paper_algorithm_manifest.json',{})
    routes=directory/'native_release/routes.pkl';routes.parent.mkdir();routes.write_bytes(pickle.dumps([[1],[2]]))
    save(directory/'native_release/manifest.json',dict(preparation_manifest_sha256=sha(prep),generated_records=2,routes_sha256=sha(routes),model_sha256=sha(model),
        post_generation_matching=False,private_input_access_during_generation=False,epsilon_training=1.4,delta_training=1e-5,privacy_scope='fixture'))
    (directory/'training.log').write_text('\n'.join(json.dumps({'epoch':i,'steps':1}) for i in range(30)),encoding='utf-8')
    receipt=dict(real_exit_code=0,stdout_completion=True,evidence_scope='fixture child exit',command=['python','trainer'])
    (directory/'execution_observation.json').write_text(json.dumps(receipt),encoding='utf-8-sig')
    mtnet.finalize(directory,prep,config)
    lineage=json.loads((directory/'lineage.json').read_text())
    assert lineage['outputs']['native_release/routes.pkl']==sha(routes)
    assert lineage['outputs']['trained/model.pt']==sha(model)
