"""I/O around the exact verified historical baseline implementations."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pickle
import shutil
import subprocess
import sys
import tempfile
import time
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
VENDOR = ROOT/'algorithms/vendor/frozen_baselines'
IDENTITIES={'SPRT':'PaperSPRTModel','PrivTrace':'official_privtrace/main.py','DPStd':'PaperDPStdModel'}


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()


def verify_sources():
    record=json.loads((VENDOR/'source_manifest.json').read_text(encoding='utf-8'))
    for rel,h in record['files'].items():
        if sha(VENDOR/rel)!=h:
            raise ValueError('Frozen baseline source changed: '+rel)
    return sha(VENDOR/'source_manifest.json')


def load_module(name):
    sys.path.insert(0,str(VENDOR))
    spec=importlib.util.spec_from_file_location(name,VENDOR/'check'/f'reproduce_{name}_paper_protocol.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    return mod


def dpstd_model(epsilon,seed,bbox):
    # The historical class assigns epsilon/4 to six separate noisy queries
    # (including OD and start counts separately). Preserve their ratio while
    # making the nominal allocation sum equal the requested experiment budget.
    return load_module('dpstd').PaperDPStdModel(bbox=bbox,epsilon=epsilon/1.5,
        grid_size=7,theta=10,max_subcells=8,maxdist_floor_m=50,max_len=100,
        point_mode='center',generator_variant='markov-init',intermediate_points=2,
        coord_sigma=0,noise_multiplier=1,budget_split='equal',seed=seed)


def official_privtrace(real,n,epsilon,seed,out):
    with tempfile.TemporaryDirectory(prefix='privtrace_fixed_') as temp:
        work=Path(temp)/'official'
        shutil.copytree(VENDOR/'official_privtrace',work)
        spec=importlib.util.spec_from_file_location('privtrace_export',VENDOR/'check/export_privtrace_dataset.py')
        exporter=importlib.util.module_from_spec(spec);spec.loader.exec_module(exporter)
        exporter.write_privtrace_format(work/'datasets/input.dat',real,6,30)
        env=dict(os.environ,PYTHONUTF8='1',PRIVTRACE_NUMPY_SEED=str(seed))
        env['PYTHONPATH']=str(ROOT/'algorithms/measurements/privtrace_compat')+os.pathsep+env.get('PYTHONPATH','')
        command=[sys.executable,'-X','utf8','main.py','--dataset_file_name=input.dat',
            f'--trajectory_number_to_generate={n}',f'--total_epsilon={epsilon}',
            '--epsilon_partition=0.2,0.4,0.4','--level1_parameter=12500','--subdividing_inner_parameter=120']
        with (out/'official_generation.log').open('w',encoding='utf-8') as log:
            process=subprocess.Popen(command,cwd=work,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace')
            for line in process.stdout:
                print(line,end='',flush=True);log.write(line);log.flush()
            if process.wait():raise RuntimeError('Official PrivTrace failed; see official_generation.log')
        syn=[]
        for line in (work/'generated_tras.txt').read_text().splitlines():
            if line.startswith('>'):
                coords=[[float(v) for v in pt.split(',')] for pt in line.split(':',1)[1].split(';') if pt.strip()]
                syn.append(np.asarray([[lat,lon] for lon,lat in coords],dtype=float).reshape(-1,2))
        return syn,{'max_points':30,'partition':[.2,.4,.4],'level1':12500,'level2':120}


def generate(method,data,out,epsilon,seed,slots,bbox,osm,test=None):
    source=verify_sources();data=Path(data);out=Path(out)
    if out.exists():raise FileExistsError(out)
    if epsilon<=0 or slots<=0:raise ValueError('epsilon and slots must be positive')
    with data.open('rb') as f:real=[np.asarray(t,dtype=float)[:,:2] for t in pickle.load(f)]
    if any(len(t)<2 for t in real):raise ValueError('Prepared input requires at least two points per trajectory')
    out.mkdir(parents=True);start=time.monotonic();np.random.seed(seed)
    if method=='SPRT':
        mod=load_module('sprt')
        ways=mod.filter_osm_ways_by_bbox(mod.load_osm_ways(str(osm)),tuple(bbox))
        centers,adj,areas,points,info=mod.build_sprt_grid_with_bounds(ways,tuple(bbox),beta=.05,road_length_unit='m')
        model=mod.PaperSPRTModel(epsilon,centers,adj,areas,tuple(bbox),alpha=1.5,cell_road_points=points).fit(real)
        syn=model.generate(slots);params={'beta':.05,'alpha':1.5,'road_length_unit':'m','grid':info}
    elif method=='DPStd':
        model=dpstd_model(epsilon,seed,tuple(bbox));model.fit(real);syn=model.generate(slots)
        params={'point_mode':'center','generator_variant':'markov-init','intermediate_points':2,'coord_sigma':0,'nominal_query_budget_each':epsilon/6,'nominal_query_count':6,'budget_note':'query allocation, not certification of trajectory DP'}
    elif method=='PrivTrace':syn,params=official_privtrace(real,slots,epsilon,seed,out)
    else:raise ValueError(method)
    if len(syn)!=slots:raise RuntimeError(f'Generator returned {len(syn)} slots, expected {slots}')
    with (out/'measurement.pkl').open('wb') as f:pickle.dump(syn,f,pickle.HIGHEST_PROTOCOL)
    manifest={'schema_version':1,'kind':'measurement','status':'VALID','M':method,'implementation':IDENTITIES[method],
        'epsilon':epsilon,'seed':seed,'public_slot_count':slots,'input_sha256':sha(data),'source_sha256':source,
        'parameters':params,'bbox':list(bbox),'outputs':{'measurement.pkl':sha(out/'measurement.pkl')},
        'elapsed_seconds':round(time.monotonic()-start,3),'classification':'RESEARCH_BASELINE_NOT_A_FORMAL_DP_RELEASE'}
    (out/'measurement_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    if test:
        lineage={'schema':'executed_train_only_generation_v1','status':'passed','generator':IDENTITIES[method],
            'input_policy':'train_only_explicit_generator_input','train_sha256':sha(data),'test_sha256':sha(test),
            'source_sha256':source,'returncode':0,'outputs':manifest['outputs'],'command':sys.argv}
        (out/'lineage.json').write_text(json.dumps(lineage,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(manifest,ensure_ascii=False),flush=True)
    return manifest


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--method',required=True,choices=list(IDENTITIES));p.add_argument('--data',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--epsilon',type=float,default=1.4)
    p.add_argument('--seed',type=int,default=42);p.add_argument('--slots',type=int,required=True)
    p.add_argument('--bbox',nargs=4,type=float,required=True);p.add_argument('--osm',type=Path,required=True)
    p.add_argument('--test',type=Path)
    generate(**vars(p.parse_args()))


if __name__=='__main__':main()
