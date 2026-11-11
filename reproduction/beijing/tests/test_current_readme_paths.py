"""Static checks only: documentation entry files, names and unchanged K values."""
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]

def test_main_readme_has_only_requested_experiment_chapters():
    text=(ROOT.parents[1]/'README.md').read_text(encoding='utf-8')
    for title in ('## 1．准备数据和资源','## 2．实验一：MR热力图，ε＝1',
                  '## 3．实验二：隐私预算变化','## 4．超参数设置：DFR的K变化'):
        assert title in text
    assert 'MTNet、MTNet＋DP-OD' in text
    assert '24、48、96、192、384、768' in text
    assert 'mm2_profile' in text and '"standard"' in text and '"light"' in text

def test_all_literal_python_entry_files_in_main_readme_exist():
    text=(ROOT.parents[1]/'README.md').read_text(encoding='utf-8')
    entries=re.findall(r'^(?:python|\.venv/Scripts/python\.exe)\s+([^\s]+\.py)\b',text,re.M)
    assert len(entries)>300
    assert all((ROOT/script).is_file() for script in entries)
    assert not re.search(r'^.*--method\s+[^\n]*(?:DPTraj-PM \(64|DPTraj-PM64)',text,re.M)

def test_representative_regions_do_not_distribute_individual_slot_membership():
    import json
    regions=json.loads((ROOT/'configs/application_regions/regions.json').read_text(encoding='utf-8'))
    assert len(regions)==10
    assert all('real_slot_ids' not in r for r in regions)
    assert all(r['real_population']>0 for r in regions)
