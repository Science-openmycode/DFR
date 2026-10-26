"""Bind and verify the existing frozen split; do not choose a new split."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

from preprocess.dataset_contract import validate_dataset

ROOT=Path(__file__).resolve().parent


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--out-config',type=Path,required=True)
    a=p.parse_args()
    if a.out.exists() or a.out_config.exists():
        p.error('Outputs must be new')
    c=json.loads(a.config.read_text(encoding='utf-8'))
    prepared=(ROOT/c['paths']['prepared']).resolve()
    identity=validate_dataset(prepared)
    if identity['dataset_id']!=c['frozen_dataset_id']:
        raise ValueError('Wrong frozen population')
    train=json.loads((prepared/'train_split.json').read_text())['indices']
    test=json.loads((prepared/'test_split.json').read_text())['indices']
    meta=dict(total_count=identity['count'],train_count=len(train),test_count=len(test),
              train_indices=train,test_indices=test,dataset_id=identity['dataset_id'])
    a.out.mkdir(parents=True)
    manifest=a.out.resolve()/'split_manifest.json'
    audit=a.out.resolve()/'split_audit.json'
    manifest.write_text(json.dumps(meta),encoding='utf-8')
    script=(ROOT/c['paths']['legacy']).resolve()/'evaluation/audit_tstr_split.py'
    command=[sys.executable,'-X','utf8',str(script),'--full-real',str(prepared/'trajectories.pkl'),
             '--split-manifest',str(manifest),'--train-real',str(prepared/'train.pkl'),
             '--test-real',str(prepared/'test.pkl'),'--out',str(audit)]
    subprocess.run(command,cwd=ROOT,check=True)
    c['paths']['split_audit']=str(audit)
    a.out_config.write_text(json.dumps(c,indent=2,ensure_ascii=False),encoding='utf-8')
    print('Existing frozen split verified; new configuration:',a.out_config)


if __name__=='__main__':
    main()
