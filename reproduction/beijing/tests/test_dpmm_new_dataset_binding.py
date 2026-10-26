from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
import multiprocessing

import pytest

from synthesize_dpmm import verify_equivalence, prior_evidence_path
from tools.dpmm_worker_bootstrap import initialize, process


def test_incomplete_old_validation_cannot_launch_new_generation(tmp_path):
    path=tmp_path/'validation.json'
    path.write_text(json.dumps({'passed':True,'complete':False}))
    with pytest.raises(ValueError,match='incomplete or failed'):
        verify_equivalence(path,None,None,None,None)

def test_fifty_record_validation_cannot_lower_required_sixty_gate(tmp_path):
    path=tmp_path/'validation.json'
    path.write_text(json.dumps({'passed':True,'complete':True,'tested_records':50,
        'target_records':50,'rows':[{'exact_output_equal':True}]*50,
        'public_path_comparisons':[{'paths_equal':True}]}))
    with pytest.raises(ValueError,match='incomplete or failed'):
        verify_equivalence(path,None,None,None,None)

def test_relocated_evidence_keeps_original_bytes_and_rejects_escape(tmp_path):
    validation=tmp_path/'train.json';validation.write_text('{}')
    evidence=tmp_path/'full.json';evidence.write_bytes(b'original evidence')
    original=evidence.read_bytes();digest=hashlib.sha256(original).hexdigest()
    locations=tmp_path/'train.locations.json'
    locations.write_text(json.dumps({'sha256_locations':{digest:'full.json'}}))
    prior={'path':'Z:/old/server/full.json','sha256':digest}
    assert prior_evidence_path(validation,prior)==evidence
    assert evidence.read_bytes()==original
    locations.write_text(json.dumps({'sha256_locations':{digest:'../outside.json'}}))
    with pytest.raises(ValueError,match='inside evidence'):
        prior_evidence_path(validation,prior)


def test_spawned_worker_installs_accelerator_not_parent_only(tmp_path,monkeypatch):
    adapter=tmp_path/'reference.py'
    adapter.write_text('''
from types import SimpleNamespace
_WORKER_MM=None
def install_semantic_path_cache(mm):mm.accelerated=False
def _init_worker(config):
    global _WORKER_MM
    _WORKER_MM=SimpleNamespace()
    install_semantic_path_cache(_WORKER_MM)
def _worker_process(item):return item,_WORKER_MM.accelerated
''')
    optimizer=tmp_path/'optimizer.py'
    optimizer.write_text('def install_semantic_path_cache(mm):mm.accelerated=True\n')
    for key,file in [('ADAPTER',adapter),('OPTIMIZER',optimizer)]:
        monkeypatch.setenv('DFR_DPMM_'+key,str(file))
        monkeypatch.setenv('DFR_DPMM_'+key+'_SHA256',hashlib.sha256(file.read_bytes()).hexdigest())
    with ProcessPoolExecutor(max_workers=2,mp_context=multiprocessing.get_context('spawn'),
                             initializer=initialize,initargs=({},)) as pool:
        result=list(pool.map(process,range(5)))
    assert result==[(i,True) for i in range(5)]
