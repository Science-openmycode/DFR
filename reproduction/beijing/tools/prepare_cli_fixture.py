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
    p.add_argument('--records',type=int,default=16,help='Artificial native population size; use 64 for DPMM 60-record validation')
    p.add_argument('--public-nodes',type=int,default=384,help='Multiple of 384; 768 enables multiple nodes per fine region')
    p.add_argument('--branched',action='store_true',help='Add public two-hop chords for nontrivial road-choice contexts')
    p.add_argument('--points',type=int,default=30,help='Artificial coordinates per trajectory; 21 gives MTNet 20 road edges')
    p.add_argument('--with-artificial-times',action='store_true',help='Write explicitly artificial endpoint timestamps for MTNet input checks')
    a=p.parse_args();out=a.out.resolve()
    if a.records<2: p.error('--records must be at least 2')
    count=a.records;train_count=int(count*.8)
    if a.points<2:p.error('--points must be at least 2')
    size=a.public_nodes
    if size<384 or size%384:p.error('--public-nodes must be a positive multiple of 384')
    if out.exists():raise FileExistsError(out)
    out.mkdir(parents=True)
    # 384 public endpoint regions, required by the unchanged DFR mechanism.
    theta=np.arange(size)*2*np.pi/size
    lon=116.3+.01*np.cos(theta);lat=39.9+.01*np.sin(theta)
    edges={};geometries=[]
    for node in range(size):
        for target in ((node+1)%size,(node-1)%size):
            edges[len(edges)+1]=(node,target)
            geometries.append(LineString([(lon[node],lat[node]),(lon[target],lat[target])]))
    if a.branched:
        for node in range(size):
            for target in ((node+2)%size,(node-2)%size):
                edges[len(edges)+1]=(node,target)
                geometries.append(LineString([(lon[node],lat[node]),(lon[target],lat[target])]))
    graph=gpd.GeoDataFrame({'id':list(edges),'source':[s for s,t in edges.values()],
        'target':[t for s,t in edges.values()],'osm_way':[str(i) for i in edges],
        'highway':['residential']*len(edges)},geometry=geometries,crs='EPSG:4326').to_crs('EPSG:32650')
    graph['length_m']=graph.length
    network=out/'network.shp';graph.to_file(network)
    cache={'edge_nodes':edges,'labels384':{i:i//(size//384) for i in range(size)},
        'labels96':{i:i//(size//96) for i in range(size)},'labels24':{i:i//(size//24) for i in range(size)},
        'outdegree':{i:4 if a.branched else 2 for i in range(size)},'portals':{}}
    save(out/'metric_cache.pkl.gz',cache);save(out/'edge_cache.pkl.gz',{'edge_nodes':edges})
    # Upstream DPMM encodes a link by stripping two characters from OSM IDs.
    # Use realistic multi-digit public way IDs; these are not metric edge IDs.
    save(out/'osm.pkl',[{'id':100000+i,'geometry':[{'lat':float(lat[s]),'lon':float(lon[s])},
        {'lat':float(lat[t]),'lon':float(lon[t])}],'tags':{'highway':'residential'}} for i,(s,t) in edges.items()])
    trajectories=[];roads=[]
    for i in range(count):
        nodes=[(i*19+j)%size for j in range(a.points)]
        trajectories.append(np.array([[lat[n],lon[n]] for n in nodes]))
        roads.append({'source_index':i,'accepted':True,'cpath':[2*n+1 for n in nodes[:-1]],'connected':True,'observation_share':1.0})
    prepared=out/'dataset';prepared.mkdir()
    save(prepared/'trajectories.pkl',trajectories);save(prepared/'trajectories.pkl.gz',trajectories)
    save(prepared/'road_records.pkl.gz',roads)
    save(prepared/'train.pkl',trajectories[:train_count]);save(prepared/'test.pkl',trajectories[train_count:])
    write(prepared/'train_split.json',{'indices':list(range(train_count))})
    write(prepared/'test_split.json',{'indices':list(range(train_count,count))})
    write(prepared/'source_indices.json',list(range(count)))
    write(prepared/'bbox.json',{'bbox':[39.88,39.92,116.28,116.32]})
    meta={'schema':'frozen-road-dataset-v1','status':'FROZEN','trajectory_count':count,
        'train_count':train_count,'test_count':count-train_count,'network':str(network),'network_sha256':sha(network),
        'network_sidecars':{s:sha(network.with_suffix(s)) for s in ('.shp','.shx','.dbf','.prj','.cpg')},
        'artifacts':{f.name:sha(f) for f in prepared.iterdir()},'purpose':'ARTIFICIAL_CLI_TEST_ONLY_NOT_RESEARCH_RESULTS'}
    if a.with_artificial_times:
        meta['original_source_sha256']=sha(prepared/'trajectories.pkl')
        write(out/'artificial_time_binding.json',dict(status='complete',all_coordinates_exact=True,
            reference_sha256=meta['original_source_sha256'],
            classification='ARTIFICIAL_CLI_TEST_TIMESTAMPS_NOT_OBSERVED_DATA',
            records=[dict(id=i+1,start_ts=1200000000+i*600,end_ts=1200000000+i*600+(a.points-1)*10,
                          source='artificial-cli-fixture') for i in range(count)]))
    write(prepared/'canonical_manifest.json',meta)
    # PrivTrace's unchanged domain requires >=50,000 observations.
    measurements=out/'measurement_input';measurements.mkdir()
    measurement_count=max(1700,int(np.ceil(50000/a.points)))
    save(measurements/'trajectories.pkl',[trajectories[i%count] for i in range(measurement_count)])
    write(measurements/'bbox.json',{'bbox':[39.88,39.92,116.28,116.32]})
    cfg=json.loads((ROOT/'configs/beijing.json').read_text(encoding='utf-8'))
    cfg.update(dataset='beijing',batch='cli_fixture',slots=count,train_slots=train_count,test_slots=count-train_count,
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
    # This independent coordinate fixture has 1700 inputs, not the 16-slot
    # frozen road population above. Do not claim that population contract.
    cfg['dataset_policy']='artificial-coordinate-cli-test'
    cfg.pop('frozen_dataset_id',None)
    write(out/'measurement.json',cfg)
    print('CLI_FIXTURE_READY',out,count,'native slots;',measurement_count*a.points,'observations for measurement input')

if __name__=='__main__':main()
