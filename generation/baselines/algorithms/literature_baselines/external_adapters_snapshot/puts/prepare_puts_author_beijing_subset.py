"""Execute the preprocessing policy in PUTS's supplied Beijing builder.

It intentionally mirrors ``build_beijing_data_full.py``: nearest road-midpoint
assignment, consecutive deduplication, and equal-index compression to at most
80 road states.  No A* bridge, MTR module, or route repair is added.
"""
from __future__ import annotations
import argparse, json, pickle
from collections import Counter
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree

def main():
 p=argparse.ArgumentParser(); p.add_argument('--real',type=Path,required=True); p.add_argument('--osm-cache',type=Path,required=True); p.add_argument('--out',type=Path,required=True); p.add_argument('--bbox',nargs=4,type=float,required=True); p.add_argument('--n',type=int,default=500); p.add_argument('--max-road-states',type=int,default=80); p.add_argument('--top-k-roads',type=int,default=8000); p.add_argument('--overwrite',action='store_true'); a=p.parse_args()
 if a.out.exists() and any(a.out.iterdir()) and not a.overwrite: raise SystemExit('output exists; pass --overwrite')
 if a.out.exists() and a.overwrite:
  import shutil; shutil.rmtree(a.out)
 a.out.mkdir(parents=True); data=a.out/'puts_input';data.mkdir()
 raw=pickle.load(a.real.open('rb')); lo_lat,hi_lat,lo_lon,hi_lon=a.bbox
 # The supplied builder retains whole raw trajectories whose observations lie
 # in the declared city area.  This makes the regional boundary explicit.
 candidates=[]
 for t in raw:
  arr=np.asarray(t,float)
  if len(arr)>=3 and np.all((arr[:,0]>=lo_lat)&(arr[:,0]<=hi_lat)&(arr[:,1]>=lo_lon)&(arr[:,1]<=hi_lon)):
   candidates.append(arr)
 if len(candidates)<a.n: raise RuntimeError(f'only {len(candidates)} in bbox, need {a.n}')
 ways=pickle.load(a.osm_cache.open('rb')); roads=[]
 for w in ways:
  pts=[(float(q['lat']),float(q['lon'])) for q in w.get('geometry',[]) if 'lat' in q and 'lon' in q]
  roads.extend((x,y) for x,y in zip(pts[:-1],pts[1:]) if x!=y)
 mids=np.asarray([[(x[0]+y[0])/2,(x[1]+y[1])/2] for x,y in roads]); tree=cKDTree(mids)
 seqs=[]; counts=Counter()
 selected=[]
 print(f'[1/3] author-style nearest-road preprocessing from {len(candidates)} regional candidates',flush=True)
 for i,t in enumerate(candidates,1):
  ids=tree.query(t,k=1)[1].tolist(); seq=[]
  for rid in ids:
   if not seq or rid!=seq[-1]:seq.append(rid)
  if len(seq)>a.max_road_states:
   step=len(seq)/a.max_road_states;seq=[seq[min(int(j*step),len(seq)-1)] for j in range(a.max_road_states)]
  if len(seq)>=2:
   selected.append(t);seqs.append(seq);counts.update(seq)
  if len(seqs)>=a.n: break
  if i%100==0: print(f'  scanned {i}/{len(candidates)}; accepted={len(seqs)}',flush=True)
 if len(seqs)<a.n: raise RuntimeError(f'only {len(seqs)} non-degenerate author-style trajectories in bbox')
 support=set(r for r,_ in counts.most_common(a.top_k_roads)); used=sorted(support); remap={r:i for i,r in enumerate(used)}
 seqs=[[remap[r] for r in s if r in remap] for s in seqs]
 if any(len(s)<2 for s in seqs): raise RuntimeError('top-K filtering removed a required trajectory')
 # This mirrors the author's helper: each road state gets a geometric point
 # from its public road segment, and opath equals the compressed road states.
 pgeom=[]
 for seq in seqs:
  old=[used[x] for x in seq]; pts=[roads[old[0]][0]]+[roads[r][1] for r in old]
  pgeom.append(';'.join(f'{lon},{lat}' for lat,lon in pts))
 n=len(seqs)
 (data/f'cpath.{n}').write_text('\n'.join(','.join(map(str,s)) for s in seqs)+'\n')
 (data/f'opath.{n}').write_text('\n'.join(','.join(map(str,s)) for s in seqs)+'\n')
 (data/f'pgeom.{n}').write_text('\n'.join(pgeom)+'\n')
 (data/'geometry.txt').write_text('\n'.join('LINESTRING ('+','.join(f'{lon} {lat}' for lat,lon in roads[r])+')' for r in used)+'\n')
 with (a.out/'accepted_raw.pkl').open('wb') as f:pickle.dump(selected,f,pickle.HIGHEST_PROTOCOL)
 stats={'method':'PUTS supplied Beijing builder preprocessing','raw_source':str(a.real),'bbox':a.bbox,'n':n,'road_support':len(used),'max_road_states':a.max_road_states,'top_k_roads':a.top_k_roads,'details':'nearest road midpoint + consecutive deduplication + equal-index compression; copied from the supplied build_beijing_data_full.py policy','not_used':['FMM','A-star bridge','MTR','PRA']}
 (a.out/'prepare_manifest.json').write_text(json.dumps(stats,indent=2));print(f'[2/3] support={len(used)}, max sequence={max(map(len,seqs))}',flush=True);print('[3/3] done',flush=True)
if __name__=='__main__':main()
