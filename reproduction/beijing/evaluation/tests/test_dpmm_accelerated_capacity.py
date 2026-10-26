import importlib.util
import json
from pathlib import Path
import sys
import numpy as np
import pytest

ROOT=Path(__file__).parents[2]
sys.path.insert(0,str(ROOT))
spec=importlib.util.spec_from_file_location('dpmm_capacity',ROOT/'tools/benchmark_dpmm_accelerated.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def test_sample_includes_two_longest_deterministically():
    data=[range((i*17)%997) for i in range(100)]
    selected=module.sample_indices(data,24)
    assert len(selected)==len(set(selected))==24
    assert selected==module.sample_indices(data,24)
    assert set(sorted(range(100),key=lambda i:(len(data[i]),i))[-2:])<=set(selected)


def test_memory_limit_includes_reserve_and_headroom():
    gib=2**30
    assert module.admissible(2,9*gib,1*gib,2*gib,2*gib)
    assert not module.admissible(4,9*gib,1*gib,2*gib,2*gib)


def test_digest_retains_shape_dtype_and_none():
    a=np.array([[39.,116.],[39.1,116.1]])
    assert module.output_digest(a)==module.output_digest(a.copy())
    assert module.output_digest(a)!=module.output_digest(a.astype('float32'))
    assert module.output_digest(None)=='NONE'
    with pytest.raises(ValueError):module.output_digest(np.array([[np.nan,116.]]))
    with pytest.raises(ValueError):module.output_digest(np.array([39.,116.]))


def test_new_protocol_does_not_pass_old_equivalence_gate(tmp_path):
    import synthesize_dpmm
    path=tmp_path/'validation.json'
    path.write_text(json.dumps({'protocol':'accelerated-only-process-validation-v1','passed':True,'complete':True,'tested_records':60,'target_records':60,'rows':[]}))
    with pytest.raises(ValueError):synthesize_dpmm.verify_equivalence(path,'adapter','optimizer','source','osm')


def test_partial_or_slow_replay_cannot_pass_new_gate(tmp_path):
    import synthesize_dpmm
    for complete,slow in [(False,False),(True,True)]:
        path=tmp_path/'validation.json'
        path.write_text(json.dumps({'protocol':'accelerated-only-process-validation-v1','passed':True,'complete':complete,'tested_records':60,'target_records':60,'slow_reference_executed':slow}))
        with pytest.raises(ValueError):
            synthesize_dpmm.verify_accelerated_validation(path,'adapter','optimizer','source','osm',2)
