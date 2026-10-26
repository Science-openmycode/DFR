"""One-time private resource import; does not generate trajectories or score data."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent
def digest(p):
    with p.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-project',type=Path,required=True)
    a=p.parse_args(); src=a.source_project.resolve()
    out=ROOT/'resources'
    if out.exists(): raise FileExistsError('Resource import never overwrites an existing directory')
    c=json.loads((src/'configs/beijing_roads_8_16_matcher_io_v2_20261016.json').read_text(encoding='utf-8'))
    t=json.loads((src/'configs/beijing_roads_8_16_tstr_20261016.json').read_text(encoding='utf-8'))
    def source(k): return (src/c['paths'][k]).resolve()
    files={}
    def copy(f,rel):
        dest=ROOT/rel;dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(f,dest)
        h=digest(dest)
        if h!=digest(f):raise ValueError('Copy hash mismatch: '+str(f))
        files[rel]=h
    prepared=source('prepared')
    for f in prepared.iterdir():
        if f.is_file():copy(f,'resources/dataset/'+f.name)
    for f in source('network').parent.glob(source('network').stem+'.*'):
        if f.is_file():copy(f,'resources/network/'+f.name)
    for k in ('osm','edge_cache','metric_cache','ubodt','fmm','stmatch'):
        copy(source(k),'resources/'+k+'/'+source(k).name)
    for f in source('runtime').iterdir():
        if f.is_file() and f.suffix.lower() in ('.dll','.exe'):
            copy(f,'resources/runtime/'+f.name)
    copy((src/t['paths']['split_audit']).resolve(),'resources/dataset/split_audit.json')
    network='resources/network/'+source('network').name
    (ROOT/'resources/dataset/network_location.json').write_text(json.dumps({'relative_path':'../network/'+source('network').name}),encoding='utf-8')
    paths=dict(legacy='legacy',output='results',prepared='resources/dataset',network=network,
        metric_network=network,runtime='resources/runtime',split_audit='resources/dataset/split_audit.json')
    for k,name in [('real','trajectories.pkl'),('real_routes','road_records.pkl.gz'),('metric_real_routes','road_records.pkl.gz'),('train','train.pkl'),('test','test.pkl')]:
        paths[k]='resources/dataset/'+name
    for k in ('osm','edge_cache','metric_cache','ubodt','fmm','stmatch'):
        paths[k]='resources/'+k+'/'+source(k).name
    paths['source_cache']=paths['metric_cache']
    paths.update(mm2='resources/mm2/map_matching_2.exe',mm2_network='resources/mm2/network')
    # MM2 new-graph assets are imported separately and hash-bound, never old config assets.
    for config,name in [(c,'beijing.json'),(t,'beijing_tstr.json')]:
        config['paths']=paths.copy();config['routing_inputs']={};config['releases']={}
        config.pop('preprocessing_review',None)
        config['unsupported_stages']={'privacy_attack':'Current member/nonmember inputs are not bound'}
        (ROOT/'configs').mkdir(exist_ok=True)
        (ROOT/'configs'/name).write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8')
    (ROOT/'resources/binding.json').write_text(json.dumps({'dataset_id':c['frozen_dataset_id'],'files':files},indent=2),encoding='utf-8')
    print(json.dumps({'copied_files':len(files),'status':'RESOURCES_IMPORTED_MM2_REQUIRES_NEW_GRAPH_BINDING'}))

if __name__=='__main__': main()
