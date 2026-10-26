import json
import sys
from pathlib import Path

import pytest
import evaluate_road_tasks as tool


def test_migrated_road_task_binds_explicit_public_network(tmp_path,monkeypatch):
    config=tmp_path/'config.json'
    config.write_text(json.dumps({'paths':{'prepared':str(tmp_path/'dataset'),
        'network':str(tmp_path/'new_public/network.shp')}}))
    seen={}
    def validate(directory,public_network=None):
        seen.update(directory=directory,network=public_network)
        raise ValueError('validation sentinel')
    monkeypatch.setattr(tool,'validate_dataset',validate)
    monkeypatch.setattr(sys,'argv',['evaluate_road_tasks.py','--config',str(config),
        '--method','DPStd','--router','MM2-MDP'])
    with pytest.raises(ValueError,match='validation sentinel'):tool.main()
    assert seen=={'directory':tmp_path/'dataset','network':tmp_path/'new_public/network.shp'}
