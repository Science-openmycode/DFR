"""Generate one training-only measurement, using the frozen method mapping."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from algorithms.measurements.frozen_adapter import generate,sha


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--method',required=True,choices=('SPRT','PrivTrace','DPStd','DPTraj-PM'))
    for name in ('data','test','osm','legacy','out'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--epsilon',type=float,default=1.4);p.add_argument('--seed',type=int,default=42)
    p.add_argument('--slots',type=int,required=True);p.add_argument('--bbox',nargs=4,type=float,required=True)
    a=p.parse_args()
    if sha(a.data)==sha(a.test):p.error('Train and test inputs are identical')
    if a.method!='DPTraj-PM':
        generate(a.method,a.data,a.out,a.epsilon,a.seed,a.slots,a.bbox,a.osm,a.test)
        return
    wrapper=a.legacy/'generation/baselines/algorithms/literature_baselines/entrypoints/generate.py'
    if a.out.exists():p.error('Output exists')
    command=[sys.executable,'-X','utf8',str(wrapper),'--method','dptrajpm-native','--data',str(a.data),
        '--out-dir',str(a.out),'--epsilon',str(a.epsilon),'--public-slot-count',str(a.slots),
        '--seed',str(a.seed),'--format','pkl','--bbox',*map(str,a.bbox),'--osm-cache',str(a.osm)]
    subprocess.run(command,cwd=ROOT,check=True)
    shutil.copy2(a.out/'dptrajpm-native.pkl',a.out/'measurement.pkl')
    outputs={'measurement.pkl':sha(a.out/'measurement.pkl')}
    lineage={'schema':'executed_train_only_generation_v1','status':'passed','generator':'DPTraj-PM preserved adapter',
        'input_policy':'train_only_explicit_generator_input','train_sha256':sha(a.data),'test_sha256':sha(a.test),
        'source_sha256':sha(wrapper),'returncode':0,'outputs':outputs,'command':command}
    (a.out/'lineage.json').write_text(json.dumps(lineage,indent=2),encoding='utf-8')
    (a.out/'measurement_manifest.json').write_text(json.dumps({'kind':'measurement','M':a.method,
        'epsilon':a.epsilon,'outputs':outputs,'implementation':'DPTraj-PM preserved adapter'},indent=2),encoding='utf-8')


if __name__=='__main__':main()
