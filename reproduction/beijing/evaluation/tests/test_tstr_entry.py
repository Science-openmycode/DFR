import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def planned_config(tmp_path):
    # Planning-only synthetic bindings: no formal release or score is created.
    config=json.loads((ROOT/'configs/beijing.json').read_text(encoding='utf-8'))
    config['releases']={'SPRT':{'coordinates':str(tmp_path/'train_coordinates.pkl'),
                              'lineage':str(tmp_path/'train_lineage.json')}}
    path=tmp_path/'planning.json';path.write_text(json.dumps(config),encoding='utf-8')
    return str(path)


def test_single_release_tstr_is_scoring_only(tmp_path):
    out = tmp_path / 'scores'
    result = subprocess.run([sys.executable, '-X', 'utf8', str(ROOT / 'evaluate_tstr.py'), '--config', planned_config(tmp_path), '--method', 'SPRT', '--out', str(out), '--dry-run'], capture_output=True, text=True, encoding='utf-8')
    assert result.returncode == 0, result.stderr
    command = json.loads(result.stdout)['command']
    assert '--require-synthesis-lineage' in command
    assert command[command.index('--names')+1] == 'SPRT'
    assert command.count('--synthetic') == 1
    assert 'synthesize-m' not in command and 'route-cell' not in command
    assert not out.exists()


def test_unbound_method_rejected(tmp_path):
    result = subprocess.run([sys.executable, '-X', 'utf8', str(ROOT / 'evaluate_tstr.py'), '--method', 'MTNet', '--out', str(tmp_path/'scores'), '--dry-run'], capture_output=True, text=True, encoding='utf-8')
    assert result.returncode != 0
    assert 'train-only release' in result.stderr


def test_empty_train_registry_rejects_route_and_table_plans(tmp_path):
    config=json.loads((ROOT/'configs/beijing.json').read_text(encoding='utf-8'))
    config['releases']={}
    path=tmp_path/'empty.json';path.write_text(json.dumps(config),encoding='utf-8')
    for entry,args in [('route_train.py',['--method','SPRT','--router','Nearest']),
                       ('experiments/table.py',['tstr'])]:
        result=subprocess.run([sys.executable,str(ROOT/entry),*args,'--config',str(path),'--dry-run'],
                              capture_output=True,text=True,encoding='utf-8')
        assert result.returncode!=0
        assert 'No registered train-only release' in result.stderr


def test_train_route_does_not_score_or_generate(tmp_path):
    result = subprocess.run([sys.executable, '-X', 'utf8', str(ROOT/'route_train.py'), '--config', planned_config(tmp_path), '--batch',str(tmp_path/'batch'), '--method', 'SPRT', '--router', 'Nearest', '--dry-run'], capture_output=True, text=True, encoding='utf-8')
    assert result.returncode == 0, result.stderr
    tasks = json.loads(result.stdout)
    assert len(tasks) == 3
    assert all('synthesize-m' not in t['command'] for t in tasks)
    assert all(not any('run_tstr_experiment.py' in arg for arg in t['command']) for t in tasks)


def test_routed_tstr_selects_routed_geometry(tmp_path):
    result = subprocess.run([sys.executable, '-X', 'utf8', str(ROOT/'evaluate_tstr.py'), '--config', planned_config(tmp_path), '--batch',str(tmp_path/'batch'), '--method', 'SPRT', '--router', 'Nearest', '--dry-run'], capture_output=True, text=True, encoding='utf-8')
    assert result.returncode == 0, result.stderr
    cmd = json.loads(result.stdout)['command']
    assert cmd[cmd.index('--names')+1] == 'SPRT + Nearest'
    assert Path(cmd[cmd.index('--synthetic')+1]).parts[-4:] == ('SPRT','Nearest','view','coordinates.pkl')


def test_mm2_tstr_selects_explicit_train_geometry_and_lineage(tmp_path):
    source=tmp_path/'coordinates.pkl'
    lineage=tmp_path/'lineage.json'
    result=subprocess.run([sys.executable,'-X','utf8',str(ROOT/'evaluate_tstr.py'),
        '--method','DPStd','--router','MM2-MDP','--input',str(source),'--lineage',str(lineage),
        '--dry-run'],capture_output=True,text=True,encoding='utf-8')
    assert result.returncode==0,result.stderr
    cmd=json.loads(result.stdout)['command']
    assert cmd[cmd.index('--names')+1]=='DPStd + MM2-MDP'
    assert cmd[cmd.index('--synthetic')+1]==str(source.resolve())
    assert cmd[cmd.index('--synthesis-lineage')+1]=='DPStd + MM2-MDP='+str(lineage.resolve())
    assert '--require-synthesis-lineage' in cmd
