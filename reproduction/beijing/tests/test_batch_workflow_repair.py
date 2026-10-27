import copy
import json
from pathlib import Path
import re
import shutil
import sys
import pickle
import numpy as np

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools import write_batch_commands as planner
from tools.prepare_dpmm_train_evaluation import validate_training_evidence
from tools import prepare_dpmm_train_evaluation as dpmm
from tools.record_native_execution import record
from preprocess.dataset_contract import sha


def evidence():
    config=dict(train_slots=100,frozen_dataset_id='dataset',epsilon=1.4)
    execution=dict(validation_protocol='slow-equivalence',osm_sha256='osm',adapter_sha256='adapter',optimizer_sha256='opt',workers=2)
    v=dict(complete=True,passed=True,tested_records=60,target_records=60,population='train',input_count=100,
           public_osm_sha256='osm',adapter_sha256='adapter',optimization_sha256='opt',public_parameters={'epsilon':1.4},
           frozen_dataset_id='dataset',real_input_sha256='train',input_sha256='train',
           rows=[dict(index=i,exact_output_equal=True) for i in range(60)],public_path_comparisons=[{'paths_equal':True}])
    return v,execution,config


def test_slow_equivalence_can_reach_train_registration():
    v,e,c=evidence();validate_training_evidence(v,e,'train',c)


def test_slow_generation_receipt_reaches_coordinate_lineage(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path);monkeypatch.setattr(dpmm,'ROOT',tmp_path)
    def save(path,obj):path.write_text(json.dumps(obj),encoding='utf-8');return path
    train=tmp_path/'train.pkl';train.write_text('train')
    test=tmp_path/'test.pkl';test.write_text('test')
    split=save(tmp_path/'split.json',dict(schema='verified_disjoint_split_v1',status='passed',all_source_indices_used_once=True,
        train_sha256=sha(train),test_sha256=sha(test),train_count=2,test_count=1))
    cfg=save(tmp_path/'config.json',dict(paths=dict(train='train.pkl',test='test.pkl',split_audit='split.json'),
        train_slots=2,test_slots=1,frozen_dataset_id='dataset',epsilon=1.4))
    v,execution,c=evidence();v.update(input_count=2,input_sha256=sha(train),real_input_sha256=sha(train))
    valid=save(tmp_path/'validation.json',v)
    doc=tmp_path/'commands.md';doc.write_text('```powershell\n.venv/Scripts/python.exe synthesize_dpmm.py --split train --out release\n```\n',encoding='utf-8')
    release=Path('release');ledger=tmp_path/'ledger.jsonl';record('start',doc,release,ledger)
    release.mkdir();(release/'dpmm.pkl').write_bytes(pickle.dumps([np.array([[1.,2.],[2.,3.]])]))
    save(release/'dpmm.json',dict(input_count=2,output_count=1,failed_count=1,released_input_indices=[0]))
    execution.update(status='DONE',population='train',input_count=2,dataset_id='dataset',input_sha256=sha(train),rematched=False,
        validation_sha256=sha(valid),privacy_scope='fixture',outputs={n:sha(release/n) for n in ('dpmm.pkl','dpmm.json')})
    save(release/'new_dataset_execution.json',execution);record('finish',doc,release,ledger,0)
    result=dpmm.prepare(release,cfg,ledger,doc,valid,tmp_path/'view')
    assert result['public_slot_count']==2
    assert len(pickle.loads((tmp_path/'view/coordinates.pkl').read_bytes()))==2


@pytest.mark.parametrize('change',['unequal','duplicate','other_input','other_dataset','other_protocol'])
def test_bad_slow_evidence_still_rejected(change):
    v,e,c=evidence()
    if change=='unequal':v['rows'][0]['exact_output_equal']=False
    if change=='duplicate':v['rows'][0]['index']=1
    if change=='other_input':v['real_input_sha256']='other'
    if change=='other_dataset':v['frozen_dataset_id']='other'
    if change=='other_protocol':e['validation_protocol']='unknown'
    with pytest.raises(ValueError):validate_training_evidence(v,e,'train',c)


def test_new_batch_binds_all_followups(tmp_path,monkeypatch):
    for directory in ['configs','supplement/sweeps','reproduction_checked_20261024']:
        shutil.copytree(ROOT/directory,tmp_path/directory)
    for doc in planner.DOCS:
        target=tmp_path/doc;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(ROOT/doc,target)
    c=json.loads((ROOT/'configs/beijing.json').read_text());c['batch']='new_user_batch'
    cfg=tmp_path/'input.json';cfg.write_text(json.dumps(c),encoding='utf-8')
    monkeypatch.setattr(planner,'ROOT',tmp_path)
    monkeypatch.setattr('preprocess.dataset_contract.validate_dataset',lambda *a,**k:{'dataset_id':c['frozen_dataset_id']})
    result=planner.generate(cfg,tmp_path/'plans/new',tmp_path/'times.json',tmp_path/'raw.pkl')
    assert result['followups']['sweep_cells']==68
    assert result['followups']['training_releases']==23
    native=(tmp_path/'plans/new/commands/REPRODUCE_NATIVE_TSTR_CN.md').read_text()
    assert '--validation results/new_user_batch/dpmm_validation_train/validation.json' in native
    assert 'vendor/dpmm/evidence/train_accelerated.json' not in native
    sweep=json.loads((tmp_path/'plans/new/sweeps_plan.json').read_text())
    assert all(x['directory'].startswith('results/new_user_batch/') for x in sweep['cells'])
    for x in sweep['cells']:
        assert (tmp_path/x['config']).is_file()
        cfg=json.loads((tmp_path/x['config']).read_text())
        assert (Path(cfg['paths']['output'])/cfg['batch']).as_posix()==x['directory']
        assert all('--config supplement/sweeps/' not in s['command'] for s in x['steps'])
    supplement=(tmp_path/'plans/new/commands/SUPPLEMENT_COMMANDS.md').read_text()
    assert '--plan plans/new/sweeps_plan.json' in supplement
    assert 'configs/portable_supplement.json' not in supplement
    for relative in result['configs'].values():
        bound=json.loads((tmp_path/relative).read_text())
        assert bound['tstr_releases']==bound['attack_releases']=={}


def test_readme_translation_has_identical_command_blocks():
    blocks=lambda p:re.findall(r'```([^\n]*)\n(.*?)```',p.read_text(encoding='utf-8'),re.S)
    assert blocks(ROOT.parents[1]/'README.md')==blocks(ROOT.parents[1]/'README_CN.md')
