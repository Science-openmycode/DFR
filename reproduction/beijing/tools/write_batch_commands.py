"""Materialize the documented commands for a newly prepared batch; never execute.

Only configuration identity, input paths and output namespace change. Algorithm
options, privacy budgets, seeds and row/metric definitions are preserved.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]
DOCS=['reproduction_checked_20261024/COMMANDS_CN.md','REPRODUCE_DFR_LENGTH_20261024_CN.md',
 'REPRODUCE_NATIVE_BASELINES_20261024_CN.md','REPRODUCE_NATIVE_SCORES_20261024_CN.md',
 'REPRODUCE_TSTR_20261024_CN.md','REPRODUCE_NATIVE_TSTR_CN.md',
 'REPRODUCE_NEW_MATRIX_CN.md',
 'supplement/sweeps/k_COMMANDS_CN.md','supplement/sweeps/budget_COMMANDS_CN.md',
 'supplement/sweeps/endpoint_diagnostic_COMMANDS_CN.md']
IDENTITY=['dataset','dataset_policy','frozen_dataset_id','slots','train_slots','test_slots',
          'population','population_status','bbox','public_resources_status','road_reference_status',
          'fmm_resources_status','mm2_resources_status','matcher_compatibility']

def generate(config,out,time_binding,raw_reference):
    out=Path(out).resolve()
    if out.exists():raise FileExistsError(out)
    if not out.is_relative_to(ROOT):raise ValueError('Plan directory must be inside this checkout')
    prefix=out.relative_to(ROOT).as_posix();base=json.loads(Path(config).read_text(encoding='utf-8'))
    # New dataset validation is explicit; do not relabel old results.
    from preprocess.dataset_contract import validate_dataset
    identity=validate_dataset(ROOT/base['paths']['prepared'],ROOT/base['paths']['network'])
    if identity['dataset_id']!=base['frozen_dataset_id']:raise ValueError('Dataset binding mismatch')
    output_prefix='results/'+base['batch']+'/'
    configs={};written=[]
    def rewrite(line):
        line=re.sub(r'(?<![\w/])results[/\\]',lambda m:output_prefix,line)
        line=line.replace('--expected-slots 15730','--expected-slots '+str(base['slots']))
        if '--expected-slots 12584' in line:
            line=line.replace('--expected-slots 12584','--expected-slots '+str(base['train_slots']))
        for old,key in [('resources/dataset/road_records.pkl.gz','real_routes'),
                        ('resources/network/network.shp','network'),
                        ('resources/metric_cache/metric_cache.pkl.gz','metric_cache'),
                        ('resources/edge_cache/edge_cache.pkl.gz','edge_cache')]:
            if old in line:
                line=line.replace(old,'"'+str((ROOT/base['paths'][key]).resolve()).replace('\\','/')+'"')
        line=line.replace('resources/mtnet/time_binding.json','"'+str(Path(time_binding).resolve()).replace('\\','/')+'"')
        line=line.replace('resources/mtnet/original_timestamp_reference.pkl','"'+str(Path(raw_reference).resolve()).replace('\\','/')+'"')
        def bind(m):
            old=m.group(1)
            if old not in configs:
                c=json.loads((ROOT/old).read_text(encoding='utf-8'))
                old_output=c.get('paths',{}).get('output','results')
                for key in IDENTITY:
                    if key in base:c[key]=copy.deepcopy(base[key])
                c['paths'].update(copy.deepcopy(base['paths']))
                c['paths']['output']=(output_prefix.rstrip('/') if old_output=='results' else rewrite(old_output))
                for name in ('routing_inputs','releases','tstr_releases','attack_releases','saved_route_inputs'):
                    c[name]={}
                c['attack_resources_status']='UNBOUND'
                target=out/'configs'/old
                target.parent.mkdir(parents=True,exist_ok=True)
                target.write_text(json.dumps(c,ensure_ascii=False,indent=2),encoding='utf-8')
                configs[old]=target.relative_to(ROOT).as_posix()
            return '--config '+configs[old]
        return re.sub(r'--config ([\w./-]+\.json)',bind,line)
    out.mkdir(parents=True)
    for doc in DOCS:
        text=(ROOT/doc).read_text(encoding='utf-8-sig')
        lines=[rewrite(line) for line in text.splitlines()]
        target=out/'commands'/doc;target.parent.mkdir(parents=True,exist_ok=True)
        # record_native_execution reads the document actually containing this batch's command.
        content='\n'.join(lines)+'\n'
        content=content.replace('--document REPRODUCE_NATIVE_BASELINES_20261024_CN.md',
            '--document '+prefix+'/commands/REPRODUCE_NATIVE_BASELINES_20261024_CN.md')
        for split,old in [('full','vendor/dpmm/evidence/full_equivalence.json'),
                          ('train','vendor/dpmm/evidence/train_accelerated.json')]:
            content=content.replace(old,f'{output_prefix}dpmm_validation_{split}/validation.json')
        if doc=='REPRODUCE_NATIVE_BASELINES_20261024_CN.md':
            validations=[]
            for split,old in [('full','vendor/dpmm/evidence/full_equivalence.json'),
                              ('train','vendor/dpmm/evidence/train_accelerated.json')]:
                validation=f'{output_prefix}dpmm_validation_{split}/validation.json'
                content=content.replace(old,validation)
                validations.append('.venv/Scripts/python.exe validate_dpmm_dataset.py --config '+configs['configs/beijing.json']+
                    ' --adapter vendor/dpmm/original/check/run_dpmm_official_beijing.py --optimizer vendor/dpmm/fast_dpmm_paths.py'+
                    f' --out {output_prefix}dpmm_validation_{split} --records 60 --exact-records 60 --split {split}')
            content=content.replace('--validation-protocol accelerated-only','--validation-protocol slow-equivalence')
            content='# 新输入DPMM准备\n\n先完成以下60条参考/加速对照，再执行下面生成命令；全集和训练输入均需至少60条。相同输入已有完成记录时复用。\n\n```powershell\n'+ '\n'.join(validations)+'\n```\n\n'+content
        target.write_text(content,encoding='utf-8')
        written.append(dict(path=target.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(target.read_bytes()).hexdigest()))
    record=dict(status='PLAN_ONLY_NOT_EXECUTED',dataset_id=identity['dataset_id'],
        source_config=str(Path(config).resolve()),documents=written,configs=configs,
        excluded='Saved-result replot is separate; supplementary attacks use this batch training release map')
    (out/'manifest.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    if 'configs/beijing.json' in configs and (ROOT/'supplement/sweeps/plan.json').exists():
        from tools.write_batch_followups import write_followups
        record['followups']=write_followups(ROOT,out,base,configs['configs/beijing.json'],rewrite)
        (out/'manifest.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    return record

def main():
    import sys
    sys.path.insert(0,str(ROOT))
    p=argparse.ArgumentParser(description=__doc__)
    for key in ['config','out','time-binding','raw-reference']:p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args();print(json.dumps(generate(a.config,a.out,a.time_binding,a.raw_reference),ensure_ascii=True,indent=2))
if __name__=='__main__':main()
