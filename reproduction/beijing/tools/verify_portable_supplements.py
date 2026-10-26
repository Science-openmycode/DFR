"""Relocate to a new directory and deny reads of the original project; no experiments."""
import argparse
import csv
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]


def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def child(forbidden,out):
    forbidden=forbidden.resolve()
    def guard(event,args):
        if event=='open' and isinstance(args[0],(str,bytes,os.PathLike)):
            p=Path(os.fsdecode(args[0])).resolve()
            if p.is_relative_to(forbidden) and not p.is_relative_to(forbidden/'.venv'):
                raise RuntimeError('Forbidden original-project read: '+str(p))
    sys.addaudithook(guard)
    sys.path.insert(0,str(ROOT))
    from tools.check_documented_command import check
    from tools.audit_readme_commands import probe
    checks=[]
    cfg=json.loads((ROOT/'configs/portable_supplement.json').read_text(encoding='utf-8'))
    for key,value in cfg['paths'].items():
        p=(ROOT/value).resolve()
        assert p.is_relative_to(ROOT),(key,value)
        if key!='output':assert p.exists(),(key,value)
    checks.append('All active supplementary resource paths inside relocated directory')
    sys.path.insert(0,str(ROOT/'legacy/evaluation'))
    from run_tstr_experiment import base_release_hash
    from synthesis_lineage import validate_record,bind_split
    train=sha(ROOT/cfg['paths']['train']);test=sha(ROOT/cfg['paths']['test'])
    bind_split(ROOT/cfg['paths']['split_audit'],train,test)
    for item in cfg['tstr_releases'].values():
        release=base_release_hash(ROOT/item['coordinates'])
        validate_record(ROOT/item['lineage'],train,test,release)
    checks.append('23 saved train-only releases and ancestors independently bound inside relocated folder')
    from experiment_contract import validate_attack_release
    for item in cfg['attack_releases'].values():
        validate_attack_release(ROOT/cfg['paths']['attack_manifest'], ROOT/item['lineage'],ROOT/item['coordinates'],
            ROOT/cfg['paths']['members'],ROOT/cfg['paths']['nonmembers'],ROOT/cfg['paths']['reference'])
    checks.append('23 attack release input contracts valid')
    from experiments._plans import build
    for experiment in ['tstr','privacy_attack']:
        steps,_,_=build(experiment,cfg,SimpleNamespace(),ROOT)
        for step in steps:
            for path in step['inputs']:
                p=Path(path);assert p.is_relative_to(ROOT) and p.is_file(),path
    checks.append('Actual TSTR/attack plan builders have closed input dependencies')
    plan=json.loads((ROOT/'supplement/sweeps/plan.json').read_text(encoding='utf-8'))
    count=0
    for cell in plan['cells']:
        config=json.loads((ROOT/cell['config']).read_text(encoding='utf-8'))
        for key,value in config['paths'].items():
            p=(ROOT/value).resolve();assert p.is_relative_to(ROOT)
            if key!='output':assert p.exists(),(cell['name'],key)
        for step in cell['steps']:
            check(ROOT/cell['document'],step['line'],step['command'],cell['document_sha256'])
            # The parser auditor expects its interpreter to exist; no experiment executes.
            probe(step['command']);count+=1
    checks.append(f'{count} new sweep commands match documents and actual parsers')
    with (ROOT/'reference_results/matrix/matrix_sources.csv').open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
    verified={}
    for r in rows:
        for key in ['result','manifest']:
            if r[key]:
                p=(ROOT/r[key]).resolve();assert p.is_relative_to(ROOT)
                if p not in verified:verified[p]=sha(p)
                assert verified[p]==r[key+'_sha256']
    checks.append(f'{len(rows)} matrix cells retain their exact source result bytes')
    payload={'status':'PASSED','relocated_root':str(ROOT),'forbidden_original_project':str(forbidden),
             'formal_experiments_repeated':0,'checks':checks,'sweep_commands_checked':count}
    out.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(payload,ensure_ascii=True))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--forbid-original',type=Path);a=p.parse_args()
    if a.forbid_original:return child(a.forbid_original,a.out)
    if a.out.exists():raise FileExistsError(a.out)
    target=ROOT.parent/'便携验证 空格 20261024'
    if target.exists():raise FileExistsError(target)
    target.mkdir()
    def transfer(src,dst):
        # Immutable data hard-links save disk; code/config are independent copies.
        if any(x in Path(src).parts for x in ('resources','reference_results')):
            os.link(src,dst)
        else:shutil.copy2(src,dst)
    folders=['algorithms','experiments','evaluation','preprocess','plotting','tools','legacy',
             'resources','reference_results','configs','supplement','repairs']
    for folder in folders:
        shutil.copytree(ROOT/folder,target/folder,copy_function=transfer,
                        ignore=shutil.ignore_patterns('__pycache__','previous_code','transferred_ancestors','output_v5'))
    for file in ROOT.glob('*.py'):shutil.copy2(file,target/file.name)
    # Interpreter only: it belongs to the validated environment, not to experiment inputs.
    (target/'.venv/Scripts').mkdir(parents=True)
    shutil.copy2(ROOT/'.venv/Scripts/python.exe',target/'.venv/Scripts/python.exe')
    tick=time.perf_counter()
    command=[sys.executable,str(target/'tools/verify_portable_supplements.py'),'--forbid-original',str(ROOT),
             '--out',str((target/'result.json').resolve())]
    result=subprocess.run(command,cwd=target,text=True,capture_output=True,encoding='utf-8',errors='replace')
    a.out.parent.mkdir(parents=True,exist_ok=True)
    receipt={'command':command,'exit_code':result.returncode,'seconds':time.perf_counter()-tick,
             'stdout':result.stdout,'stderr':result.stderr,'relocated_root':str(target),'formal_experiments_repeated':0}
    if (target/'result.json').exists():receipt['result']=json.loads((target/'result.json').read_text(encoding='utf-8'))
    a.out.write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'exit_code':result.returncode,'seconds':receipt['seconds'],'stderr':result.stderr[-3000:]}))
    raise SystemExit(result.returncode)


if __name__=='__main__':main()
