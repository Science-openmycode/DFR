"""Independently compare frozen Porto views to original ZIP records, bounded memory."""
import argparse
import csv
import gzip
import hashlib
import itertools
import json
import pickle
from pathlib import Path
import sys
import time
import zipfile
import numpy as np
from dataset_contract import validate_dataset
from start_porto import rows, sha


class ListConsumer(pickle._Unpickler):
    dispatch=pickle._Unpickler.dispatch.copy()
    def __init__(self,stream,callback):
        super().__init__(stream);self.callback=callback;self.root=None;self.count=0
    def load_empty_list(self):
        super().load_empty_list()
        if self.root is None:self.root=self.stack[-1]
    dispatch[pickle.EMPTY_LIST[0]]=load_empty_list
    def load_append(self):
        if len(self.stack)>=2 and self.stack[-2] is self.root:
            self.callback(self.stack.pop());self.count+=1
        else:super().load_append()
    dispatch[pickle.APPEND[0]]=load_append


def consume(path,callback):
    with (gzip.open(path,'rb') if str(path).endswith('.gz') else Path(path).open('rb')) as f:
        if f.read(3)!=b'\x80\x03]':raise ValueError('Expected explicitly framed Porto list')
        f.seek(0);reader=ListConsumer(f,callback)
        if reader.load()!=[] or f.read(1):raise ValueError('Invalid list or trailing data')
        return reader.count


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dataset',type=Path,required=True)
    p.add_argument('--archive',type=Path,required=True)
    p.add_argument('--graph',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();started=time.monotonic()
    if a.out.exists():p.error('Output exists')
    identity=validate_dataset(a.dataset,verify_hashes=True)
    meta=json.loads((a.dataset/'canonical_manifest.json').read_text())
    if sha(a.archive)!=meta['original_source_sha256'] or sha(a.graph/'manifest.json')!=meta['graph_manifest_sha256']:
        raise ValueError('Source binding mismatch')
    source_ids=json.loads((a.dataset/'source_indices.json').read_text());keep=set(source_ids)
    mapping=json.loads((a.graph/'road_mapping.json').read_text())
    import pyogrio
    network=pyogrio.read_dataframe(a.graph/'network.shp',columns=['id','source','target'],read_geometry=False)
    ends={int(r.id):(int(r.source),int(r.target)) for r in network.itertuples()}
    with zipfile.ZipFile(a.archive) as z:
        origins={int(r['geo_id']):json.loads(r['coordinates'])[0] for r in rows(z,'porto_roadmap_edge/porto_roadmap_edge.geo')}
    def original():
        global_index=0
        with zipfile.ZipFile(a.archive) as z:
            for split in ('train','eval','test'):
                for row in rows(z,f'porto/porto_{split}.csv',';'):
                    if global_index in keep:yield global_index,json.loads(row['path']),json.loads(row['tlist'])
                    global_index+=1
    checks={}; coordinate_hashes=[]; expected=iter(original())
    def check_coordinate(coords):
        _,path,_=next(expected)
        values=np.asarray([[origins[e][1],origins[e][0]] for e in path],dtype='<f8')
        if not np.array_equal(coords,values):raise ValueError('Coordinate source mismatch')
        coordinate_hashes.append(hashlib.sha256(coords.tobytes()).hexdigest())
    checks['coordinates_source_exact']=consume(a.dataset/'trajectories.pkl',check_coordinate)
    if next(expected,None) is not None:raise ValueError('Missing coordinates')
    expected=iter(original())
    def check_road(record):
        index,path,_=next(expected)
        opath=[mapping[str(e)]['edges'][0] for e in path]
        cpath=[edge for road,_ in itertools.groupby(path) for edge in mapping[str(road)]['edges']]
        if record['source_index']!=index or record['opath']!=opath or record['cpath']!=cpath:
            raise ValueError('Road sequence source mismatch')
        if any(ends[x][1]!=ends[y][0] for x,y in zip(cpath,cpath[1:])):raise ValueError('Disconnected frozen road sequence')
    checks['roads_source_exact']=consume(a.dataset/'road_records.pkl.gz',check_road)
    if next(expected,None) is not None:raise ValueError('Missing roads')
    expected=iter(original())
    def check_time(times):
        _,_,source=next(expected)
        if not np.array_equal(times,np.asarray(source,dtype='<f8')):raise ValueError('Time source mismatch')
    checks['timestamps_source_exact']=consume(a.dataset/'start_road_timestamps.pkl.gz',check_time)
    if next(expected,None) is not None:raise ValueError('Missing timestamps')
    def check_saved(path,indices):
        index_iter=iter(indices)
        def item(coords):
            index=next(index_iter)
            if hashlib.sha256(coords.tobytes()).hexdigest()!=coordinate_hashes[index]:raise ValueError('Saved coordinate view differs')
        count=consume(path,item)
        if next(index_iter,None) is not None:raise ValueError('Missing split entries')
        return count
    checks['gzip_coordinates_exact']=check_saved(a.dataset/'trajectories.pkl.gz',range(len(source_ids)))
    for split in ('train','test'):
        indices=json.loads((a.dataset/f'{split}_split.json').read_text())['indices']
        checks[split+'_source_exact']=check_saved(a.dataset/f'{split}.pkl',indices)
    if any(checks[k]!=identity['count'] for k in ('coordinates_source_exact','roads_source_exact','timestamps_source_exact','gzip_coordinates_exact')):
        raise ValueError('Full population count mismatch')
    result=dict(status='VERIFIED',**identity,checks=checks,elapsed_seconds=time.monotonic()-started,
                argv=[sys.executable,*sys.argv],code_sha256=sha(__file__),
                scope='all frozen source records, road identities/continuity, processed times, coordinates, split files and input hashes')
    a.out.write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2))


if __name__=='__main__':main()
