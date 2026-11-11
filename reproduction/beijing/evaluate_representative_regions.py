"""Fixed ten-region MR evaluation; original author solver, no retraining."""
import sys,json,time,hashlib,argparse
from pathlib import Path
from collections import defaultdict
B=Path(__file__).resolve().parent
from evaluation.applications.engine import rows,read,prepare
from evaluation.applications.core import author_greedy
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,v):Path(p).write_text(json.dumps(v,indent=2),encoding='utf-8')
def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--inputs',type=Path,required=True,help='JSON list of method/path/optional sha256; include Real')
 p.add_argument('--public-edges',type=Path,required=True)
 p.add_argument('--regions',type=Path,default=B/'configs/application_regions/regions.json')
 p.add_argument('--resources',type=Path,required=True,help='Shared prepared public region resources')
 p.add_argument('--slots',type=int,default=15730)
 p.add_argument('--out',type=Path,required=True)
 a=p.parse_args();start=time.perf_counter();out=a.out;out.mkdir(parents=True,exist_ok=False)
 inv=read(a.inputs);assert inv and len({x['method'] for x in inv})==len(inv)
 public=a.public_edges
 nodes={str(e['edge_id']):(e['u'],e['v']) for e in rows(public)}
 def incidence(path):
  occ=defaultdict(int);n=0
  for i,r in enumerate(rows(path)):
   assert r['slot_id']==i and bool(r['edge_ids'])==r['valid'];seq=[str(e) for e in r['edge_ids']]
   assert all(e in nodes for e in seq)
   assert all(nodes[a][1]==nodes[b][0] for a,b in zip(seq,seq[1:]))
   for e in set(seq):occ[e]|=1<<i
   n+=1
  assert n==a.slots;return occ
 real=incidence(next(x['path'] for x in inv if x['method']=='Real'))
 resources=[]
 regions=read(a.regions);assert len(regions)==10
 for region in regions:
  root=a.resources/region['region_id'];d=root/'resources'
  if not d.exists():
   root.mkdir(parents=True,exist_ok=True)
   write(root/'region.json',region)
   write(root/'questions.json',{'representative':{'K':5,'distance_m':40,'real_population':region['real_population']}})
   prepare(dict(region=root/'region.json',questions=root/'questions.json',coordinate_units='metre',public_edges=public,coverage_distance_m=40,dataset_id=region.get('dataset_id','afeddd66f0c6d5281dad5980bd56a8b62ffbd87ed53cd92493761a516ff1af35')),d)
  else:assert read(root/'region.json')==region
  m=read(d/'manifest.json')
  assert m['public_edges_sha256']==sha(public) and m['region_sha256']==sha(root/'region.json')
  for name,h in m['outputs'].items():assert sha(d/name)==h
  roads=read(d/'roads.json');mapping=read(d/'mapping.json');cache=read(d/'coverage.json')
  def masks(occ):
   used=[occ[str(x['original_edge_id'])] for x in mapping];result=[]
   for ids in cache:
    bits=0
    for j in ids:bits|=used[j]
    result.append(bits)
   return result
  resources.append((region,roads,mapping,cache,masks(real)))
 answers=[]
 for item in inv:
  path=Path(item['path']);h=sha(path)
  if item.get('sha256'):assert h==item['sha256']
  item['sha256']=h;occ=incidence(path);group=[]
  for region,roads,mapping,cache,real_masks in resources:
   used=[occ[str(x['original_edge_id'])] for x in mapping];mm=[]
   for ids in cache:
    bits=0
    for j in ids:bits|=used[j]
    mm.append(bits)
   routes=author_greedy(roads,mm,5,4437.46);bits=0
   assert len(routes)<=5
   for route in routes:
    assert sum(roads[e][-1] for e in route)<=4437.46+1e-6
    assert all(roads[a][2]==roads[b][1] for a,b in zip(route,route[1:]))
    for e in route:bits|=real_masks[e]
   n=region['real_population'];assert bits.bit_count()<=n
   group.append(dict(method=item['method'],region=region['region_id'],covered=bits.bit_count(),population=n,score=bits.bit_count()/n,routes=routes,actual_routes=len(routes),input_sha256=h))
  answers.extend(group);write(out/f'answer_{len(answers)//10:02}.json',group)
  print('MR_REGION_RELEASE_COMPLETE',item['method'],len(answers),time.perf_counter()-start,flush=True)
 assert len(answers)==10*len(inv)
 write(out/'answers.json',answers);write(out/'input_bindings.json',inv)
 write(out/'manifest.json',dict(status='COMPLETE',answers=len(answers),columns=len(inv),regions=10,region_sha256=sha(a.regions),public_edges_sha256=sha(public),slots=a.slots,seconds=time.perf_counter()-start,outputs={p.name:sha(p) for p in out.glob('*.json')}))
 print('MR_REGIONS_COMPLETE',len(answers),time.perf_counter()-start,flush=True)
if __name__=='__main__':main()
