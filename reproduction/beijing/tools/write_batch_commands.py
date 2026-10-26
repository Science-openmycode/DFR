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
        line=line.replace('resources/mtnet/time_binding.json','"'+str(Path(time_binding).resolve()).replace('\\','/')+'"')
        line=line.replace('resources/mtnet/original_timestamp_reference.pkl','"'+str(Path(raw_reference).resolve()).replace('\\','/')+'"')
        def bind(m):
            old=m.group(1)
            if old not in configs:
                c=json.loads((ROOT/old).read_text(encoding='utf-8'))
                for key in IDENTITY:
                    if key in base:c[key]=copy.deepcopy(base[key])
                c['paths'].update(copy.deepcopy(base['paths']))
                c['paths']['output']=output_prefix.rstrip('/')
                c['routing_inputs']={};c['releases']={}
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
        target.write_text(content,encoding='utf-8')
        written.append(dict(path=target.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(target.read_bytes()).hexdigest()))
    record=dict(status='PLAN_ONLY_NOT_EXECUTED',dataset_id=identity['dataset_id'],
        source_config=str(Path(config).resolve()),documents=written,configs=configs,
        excluded='Saved-result replot and privacy attack require separately bound input protocols; never copied as new results')
    (out/'manifest.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    return record

def main():
    import sys
    sys.path.insert(0,str(ROOT))
    p=argparse.ArgumentParser(description=__doc__)
    for key in ['config','out','time-binding','raw-reference']:p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args();print(json.dumps(generate(a.config,a.out,a.time_binding,a.raw_reference),ensure_ascii=True,indent=2))
if __name__=='__main__':main()
