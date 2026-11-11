from pathlib import Path
import pytest
from evaluation.audit_v2_runner import resolve_forwarded_paths

def test_caller_relative_paths_not_legacy_root(tmp_path):
    args=['--real','results/view.pkl','--synthetic','results/view.pkl','--out-dir','results/score',
          '--bbox','39','40','116','117','--public-slot-count','15730']
    result=resolve_forwarded_paths(args,tmp_path)
    assert result[1]==str((tmp_path/'results/view.pkl').resolve())
    assert result[3]==result[1]
    assert result[5]==str((tmp_path/'results/score').resolve())
    assert result[6:]==args[6:]
    assert args[1]=='results/view.pkl'

def test_absolute_paths_preserved(tmp_path):
    absolute=str((tmp_path/'road.pkl').resolve())
    assert resolve_forwarded_paths(['--road-routes',absolute],tmp_path)==['--road-routes',absolute]

def test_missing_path_value_rejected(tmp_path):
    with pytest.raises(ValueError,match='Missing path'):
        resolve_forwarded_paths(['--real','--bbox','39'],tmp_path)
