from pathlib import Path
import argparse,hashlib,importlib.util,json,os,pickle,shutil,subprocess,time
import numpy as np
B=Path(__file__).resolve().parent
DATA=B/'resources/dataset/trajectories.pkl'
EXECUTABLE=B/'resources/dptraj/dptraj_grid.exe'
BBOX=[39.75,40.15,116.1,116.65]
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for x in iter(lambda:f.read(1048576),b''):h.update(x)
 return h.hexdigest()
def save(p,x):p.write_text(json.dumps(x,indent=2,ensure_ascii=False),encoding='utf-8')
def load_module(p):
 s=importlib.util.spec_from_file_location('old_adapter_readonly',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def native(data,d,grid,exe=None,epsilon=1.4):
 d.mkdir(parents=True,exist_ok=False);w=d/'author_work'
 for name in ['temp','SynData','convert_syn','testResults']:(w/'Data'/name).mkdir(parents=True)
 with (w/'Data/ori.txt').open('w',encoding='ascii') as f:
  for i,t in enumerate(data):f.write(f'#{i}:\n>0:'+ ';'.join(f'{lon:.12f},{lat:.12f}' for lat,lon in np.asarray(t)[:,:2])+';\n')
 a,b,c,e=BBOX;(w/'Data/boundary.txt').write_text(f'{c:.12f} {e:.12f} {a:.12f} {b:.12f}\n',encoding='ascii')
 cmd=[str(exe or EXECUTABLE),str(epsilon),str(grid)]
 start=time.perf_counter()
 with (d/'author_stdout.log').open('wb') as so,(d/'author_stderr.log').open('wb') as se:
  p=subprocess.run(cmd,cwd=w,env=dict(os.environ,DPTRAJ_SEED='42'),stdout=so,stderr=se)
 save(d/'author_receipt.json',dict(internal_subprocess_argv=cmd,cwd=str(w),exit_code=p.returncode,seconds=time.perf_counter()-start,executable_sha256=sha(cmd[0])))
 assert p.returncode==0,f'Native failed {p.returncode}'
 out=[]
 for line in (w/'Data/synthetic.txt').read_text('ascii').splitlines():
  if line.startswith('>'):
   pts=[list(map(float,x.split(','))) for x in line.split(':',1)[1].split(';') if x.strip()]
   out.append(np.asarray([[lat,lon] for lon,lat in pts]).reshape(-1,2))
 assert len(out)<=len(data);emitted=len(out);out.extend(np.empty((0,2)) for _ in range(len(data)-len(out)))
 with (d/'measurement.pkl').open('wb') as f:pickle.dump(out,f,pickle.HIGHEST_PROTOCOL)
 save(d/'measurement_manifest.json',dict(schema_version=1,kind='measurement',status='VALID',M='DPTraj-PM',epsilon=epsilon,seed=42,public_slot_count=len(data),input_sha256=sha(DATA),bbox=BBOX,parameters=dict(grid=[grid,grid],markov_order=2,maxLevel=3,prefix_budget_fraction=.6,maxStep=grid*grid,implementation='author-C++-archive4-grid-parameter'),outputs={'measurement.pkl':sha(d/'measurement.pkl')},native_emitted=emitted,unassigned_empty_slots=len(data)-emitted,elapsed_seconds=time.perf_counter()-start,classification='PAPER_RESEARCH_BASELINE_NOT_A_CERTIFIED_DP_RELEASE'))
 return out
def main():
 global DATA,BBOX,EXECUTABLE
 p=argparse.ArgumentParser();p.add_argument('stage',choices=['generate']);p.add_argument('--epsilon',type=float,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--config',type=Path,required=True);p.add_argument('--executable',type=Path);a=p.parse_args()
 from preprocess.dataset_config import load_config
 c=load_config(a.config,B);DATA=(B/c['paths']['real']).resolve();BBOX=c['bbox']
 EXECUTABLE=(a.executable or B/c['paths'].get('dptraj_executable',str(EXECUTABLE))).resolve()
 if not EXECUTABLE.is_file():raise FileNotFoundError(EXECUTABLE)
 grid=c.get('dptraj_pm',{}).get('grid',64)
 if type(grid) is not int or grid<2:raise ValueError('Integer grid of at least two required by existing author CLI')
 with DATA.open('rb') as f:data=pickle.load(f)
 assert len(data)==c['slots']
 syn=native(data,a.out,grid,epsilon=a.epsilon)
 counts={str(n):sum(len(t)==n for t in syn) for n in [0,1]}
 save(a.out/'native_stats.json',dict(slots=len(syn),length_0_1=counts,total_points=sum(map(len,syn)),max_points=max(map(len,syn)),median_points=float(np.median(list(map(len,syn))))))
 print('DONE',a.stage,flush=True)
if __name__=='__main__':main()
