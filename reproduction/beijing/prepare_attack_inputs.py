"""Adapt the frozen train/test split to the existing disjoint attack sampler."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
from preprocess.dataset_contract import validate_dataset

ROOT=Path(__file__).resolve().parent

def prepare(config,out,out_config,releases):
    c=json.loads(Path(config).read_text(encoding='utf-8'))
    out=Path(out).resolve();out_config=Path(out_config).resolve()
    if out.exists() or out_config.exists():raise FileExistsError('Choose new output paths')
    dataset=(ROOT/c['paths']['prepared']).resolve()
    identity=validate_dataset(dataset,ROOT/c['paths']['network'])
    if identity['dataset_id']!=c['frozen_dataset_id']:raise ValueError('Dataset identity changed')
    mapping=json.loads(Path(releases).read_text(encoding='utf-8'))
    if not mapping:raise ValueError('Register actual training-only releases first')
    for item in mapping.values():
        for key in ('coordinates','lineage'):
            path=(ROOT/item[key]).resolve()
            if not path.is_file():raise FileNotFoundError(path)
            item[key]=str(path)
    source=out/'source_split';source.mkdir(parents=True)
    for name in ('train.pkl','test.pkl'):shutil.copy2(dataset/name,source/name)
    manifest={key+'_indices':json.loads((dataset/(key+'_split.json')).read_text())['indices'] for key in ('train','test')}
    (source/'split_manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
    sampler=ROOT/'legacy/evaluation/pipeline/prepare_privacy_attack_splits.py'
    command=[sys.executable,str(sampler),'--split-dir',str(source),'--out-dir',str(out/'split'),'--attack-candidates','1000','--seed','20260715']
    subprocess.run(command,check=True,cwd=ROOT)
    for key,name in [('members','member_candidates.pkl'),('nonmembers','nonmember_candidates.pkl'),('reference','reference.pkl'),('attack_manifest','manifest.json')]:
        c['paths'][key]=str(out/'split'/name)
    c['attack_releases']=mapping;c['attack_resources_status']='PREPARED_CURRENT_TRAIN_SPLIT'
    out_config.parent.mkdir(parents=True,exist_ok=True)
    out_config.write_text(json.dumps(c,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'adapter_manifest.json').write_text(json.dumps({'dataset_id':identity['dataset_id'],'command':command,'exit_code':0,'release_map':str(Path(releases).resolve()),'note':'Private research inputs, not a DP release. Downstream evaluator verifies training lineage.'},indent=2),encoding='utf-8')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('config','out','out-config','releases'):p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args();prepare(a.config,a.out,a.out_config,a.releases)

if __name__=='__main__':main()
