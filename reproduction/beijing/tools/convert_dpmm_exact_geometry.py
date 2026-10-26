"""Exact delivered-geometry lookup, not nearest matching, routing, or gap filling.

Seven decimals is the frozen DPMM graph's own node identity precision. Every
delivered directed segment must have exactly one public edge candidate. Any
ambiguous, absent or disconnected representation remains a rejected slot.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import pickle
import sqlite3
import time



def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def key(a,b):
    return ','.join(str(round(float(x),7)) for x in (*a,*b))


def resolve(sequence, db):
    route=[]; previous=None
    for a,b in zip(sequence[:-1],sequence[1:]):
        if key(a,a)==key(b,b):continue
        # Input uses lat/lon; public shapefile uses lon/lat.
        token=key((a[1],a[0]),(b[1],b[0]))
        rows=db.execute('SELECT DISTINCT edge, source, target FROM segments WHERE k=?',(token,)).fetchmany(2)
        if not rows:return [],'no_exact_public_segment'
        if len(rows)!=1:return [],'ambiguous_public_segment'
        edge,source,target=rows[0]
        if route and edge==route[-1]:continue
        if previous is not None and previous!=source:return [],'disconnected_public_representation'
        route.append(edge);previous=target
    return (route,'valid') if route else ([], 'empty_native_slot')


def main():
    import shapefile
    from pyproj import CRS, Transformer
    import psutil
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('coordinates','slot-manifest','network','out-dir'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();started=time.perf_counter()
    if a.out_dir.exists():raise FileExistsError(a.out_dir)
    if psutil.virtual_memory().available < .75*1024**3:
        raise MemoryError('Require 0.75GiB free before memory-bounded geometry conversion')
    meta=json.loads(a.slot_manifest.read_text(encoding='utf-8'))
    if not meta['unchanged_released_arrays_verified'] or sha(a.coordinates)!=meta['output']['sha256']:
        raise ValueError('Require unchanged staged native arrays')
    with a.coordinates.open('rb') as stream:arrays=pickle.load(stream)
    if len(arrays)!=meta['original_slot_count']:raise ValueError('Slot count changed')
    network_sha=sha(a.network);coordinate_sha=sha(a.coordinates)
    crs=CRS.from_wkt(a.network.with_suffix('.prj').read_text())
    transform=Transformer.from_crs(crs,4326,always_xy=True)
    a.out_dir.mkdir(parents=True)
    db=sqlite3.connect(a.out_dir/'exact_geometry_lookup.sqlite')
    db.execute('PRAGMA cache_size=-16384')
    db.execute('CREATE TABLE segments (k TEXT, edge INTEGER, source INTEGER, target INTEGER)')
    reader=shapefile.Reader(str(a.network))
    names=[f[0] for f in reader.fields[1:]];indices=[names.index(x) for x in ('id','source','target')]
    count=0
    for record in reader.iterShapeRecords():
        edge,source,target=[int(record.record[i]) for i in indices]
        raw=record.shape.points
        xx,yy=transform.transform([x[0] for x in raw],[x[1] for x in raw])
        points=list(zip(xx,yy))
        db.executemany('INSERT INTO segments VALUES (?,?,?,?)',[(key(x,y),edge,source,target) for x,y in zip(points[:-1],points[1:]) if key(x,x)!=key(y,y)])
        count+=1
        if count%50000==0:
            print('PUBLIC_EDGES_INDEXED',count,flush=True)
            if psutil.virtual_memory().available<.2*1024**3:raise MemoryError('Low system memory; stop only this converter')
    db.execute('CREATE INDEX by_segment ON segments(k)');db.commit()
    result=[];counts={}
    for index,sequence in enumerate(arrays):
        if index%1000==0:
            print('NATIVE_SLOTS_CHECKED',index,flush=True)
            if psutil.virtual_memory().available<.2*1024**3:raise MemoryError('Low system memory; stop only this converter')
        route,reason=resolve(sequence,db);counts[reason]=counts.get(reason,0)+1
        result.append({'source_index':index,'accepted':reason=='valid','cpath':route,'reason':reason})
    db.close()
    output=a.out_dir/'synthetic_routes.pkl.gz'
    with gzip.open(output,'wb') as stream:pickle.dump(result,stream,pickle.HIGHEST_PROTOCOL)
    if sha(a.coordinates)!=coordinate_sha or sha(a.network)!=network_sha:raise RuntimeError('Input changed during conversion')
    report={'classification':'NATIVE_ROAD_REPRESENTATION_ONLY','source_representation':'exact-rounded-native-directed-geometry',
        'native_sha256':coordinate_sha,'public_network_sha256':network_sha,'output_sha256':sha(output),
        'record_count':len(arrays),'reason_counts':counts,'public_edge_count':count,'rematched':False,
        'gap_filling':False,'route_selection':False,'rounding_decimals':7,
        'network_prj_sha256':sha(a.network.with_suffix('.prj')),'public_geometry_transform':'Declared public CRS to EPSG:4326; no fitted transform',
        'identity_rule':'Frozen DPMM _node_key precision; exactly one public directed segment per delivered segment; no nearest search',
        'inputs':{'coordinates':{'path':str(a.coordinates.resolve()),'sha256':coordinate_sha},'slot_manifest':{'path':str(a.slot_manifest.resolve()),'sha256':sha(a.slot_manifest)}},
        'converter_sha256':sha(Path(__file__)),'seconds':time.perf_counter()-started}
    (a.out_dir/'route_manifest.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report),flush=True)


if __name__=='__main__':main()
