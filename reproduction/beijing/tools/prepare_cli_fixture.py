"""Make explicitly artificial, small CLI inputs; never use for paper results."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import pickle
import sys
import numpy as np
import geopandas as gpd
from shapely.geometry import LineString

ROOT=Path(__file__).resolve().parents[1]

def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def save(p,value):
    p.parent.mkdir(parents=True,exist_ok=True)
    with (gzip.open(p,'wb') if p.suffix=='.gz' else p.open('wb')) as f:pickle.dump(value,f,pickle.HIGHEST_PROTOCOL)

def write(p,value):
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value,indent=2),encoding='utf-8')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--runtime',type=Path,required=True)
    a=p.parse_args();out=a.out.resolve()
    if out.exists():raise FileExistsError(out)
    out.mkdir(parents=True)
    # 384 public endpoint regions, required by the unchanged DFR mechanism.
    theta=np.arange(384)*2*np.pi/384
    lon=116.3+.01*np.cos(theta);lat=39.9+.01*np.sin(theta)
    edges={};geometries=[]
    for node in range(384):
        for target in ((node+1)%384,(node-1)%384):
            edges[len(edges)+1]=(node,target)
            geometries.append(LineString([(lon[node],lat[node]),(lon[target],lat[target])]))
    graph=gpd.GeoDataFrame({'id':list(edges),'source':[s for s,t in edges.values()],
        'target':[t for s,t in edges.values()],'osm_way':[str(i) for i in edges],
        'highway':['residential']*len(edges)},geometry=geometries,crs='EPSG:4326').to_crs('EPSG:32650')
    graph['length_m']=graph.length
    network=out/'network.shp';graph.to_file(network)
    cache={'edge_nodes':edges,'labels384':{i:i for i in range(384)},
        'labels96':{i:i//4 for i in range(384)},'labels24':{i:i//16 for i in range(384)},
        'outdegree':{i:2 for i in range(384)},'portals':{}}
    save(out/'metric_cache.pkl.gz',cache);save(out/'edge_cache.pkl.gz',{'edge_nodes':edges})
    save(out/'osm.pkl',[{'id':i,'geometry':[{'lat':float(lat[s]),'lon':float(lon[s])},
        {'lat':float(lat[t]),'lon':float(lon[t])}],'tags':{'highway':'residential'}} for i,(s,t) in edges.items()])
    trajectories=[];roads=[]
    for i in range(16):
        nodes=[(i*19+j)%384 for j in range(30)]
        trajectories.append(np.array([[lat[n],lon[n]] for n in nodes]))
        roads.append({'source_index':i,'accepted':True,'cpath':[2*n+1 for n in nodes[:-1]],'connected':True,'observation_share':1.0})
    prepared=out/'dataset';prepared.mkdir()
    save(prepared/'trajectories.pkl',trajectories);save(prepared/'trajectories.pkl.gz',trajectories)
    save(prepared/'road_records.pkl.gz',roads)
    save(prepared/'train.pkl',trajectories[:12]);save(prepared/'test.pkl',trajectories[12:])
    write(prepared/'train_split.json',{'indices':list(range(12))})
    write(prepared/'test_split.json',{'indices':list(range(12,16))})
    write(prepared/'source_indices.json',list(range(16)))
    write(prepared/'bbox.json',{'bbox':[39.88,39.92,116.28,116.32]})
    meta={'schema':'frozen-road-dataset-v1','status':'FROZEN','trajectory_count':16,
        'train_count':12,'test_count':4,'network':str(network),'network_sha256':sha(network),
        'network_sidecars':{s:sha(network.with_suffix(s)) for s in ('.shp','.shx','.dbf','.prj','.cpg')},
        'artifacts':{f.name:sha(f) for f in prepared.iterdir()},'purpose':'ARTIFICIAL_CLI_TEST_ONLY_NOT_RESEARCH_RESULTS'}
    write(prepared/'canonical_manifest.json',meta)
    # PrivTrace's unchanged domain requires >=50,000 observations.
    measurements=out/'measurement_input';measurements.mkdir()
    save(measurements/'trajectories.pkl',[trajectories[i%16] for i in range(1700)])
    write(measurements/'bbox.json',{'bbox':[39.88,39.92,116.28,116.32]})
    cfg=json.loads((ROOT/'configs/beijing.json').read_text(encoding='utf-8'))
    cfg.update(dataset='beijing',batch='cli_fixture',slots=16,train_slots=12,test_slots=4,
        frozen_dataset_id=sha(prepared/'canonical_manifest.json'),bbox=[39.88,39.92,116.28,116.32],
        public_resources_status='EDGE_METRIC_READY',epsilon=1.4,seed=42,threads=2)
    cfg.pop('measurement_bbox',None)
    cfg['paths'].update(prepared=str(prepared),real=str(prepared/'trajectories.pkl'),
        real_routes=str(prepared/'road_records.pkl.gz'),metric_real_routes=str(prepared/'road_records.pkl.gz'),
        train=str(prepared/'train.pkl'),test=str(prepared/'test.pkl'),network=str(network),metric_network=str(network),
        metric_cache=str(out/'metric_cache.pkl.gz'),source_cache=str(out/'metric_cache.pkl.gz'),
        edge_cache=str(out/'edge_cache.pkl.gz'),osm=str(out/'osm.pkl'),runtime=str(a.runtime.resolve()))
    write(out/'native.json',cfg)
    cfg['paths']['prepared']=str(measurements)
    write(out/'measurement.json',cfg)
    print('CLI_FIXTURE_READY',out,'16 native slots; 51000 observations for measurement input')

if __name__=='__main__':main()
