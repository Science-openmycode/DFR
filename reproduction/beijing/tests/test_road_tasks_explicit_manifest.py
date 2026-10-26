import hashlib
import json

import pytest

from evaluate_road_tasks import verify_score_inputs


def test_explicit_arm_manifest_binds_actual_inputs(tmp_path):
    inputs={key:tmp_path/key for key in ('real_routes','synthetic_routes','metric_cache')}
    for key,path in inputs.items():
        path.write_bytes(key.encode())
    ledger={'inputs':{key:{'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
                      for key,path in inputs.items()}}
    manifest=tmp_path/'manifest.json'
    manifest.write_text(json.dumps(ledger),encoding='utf-8')
    assert verify_score_inputs(manifest,inputs)==ledger
    inputs['synthetic_routes'].write_bytes(b'other arm')
    with pytest.raises(ValueError,match='synthetic_routes'):
        verify_score_inputs(manifest,inputs)


def test_missing_score_manifest_is_not_replaced_with_full_method(tmp_path):
    with pytest.raises(FileNotFoundError):
        verify_score_inputs(tmp_path/'missing.json',{})
