"""Independently rebuild public geometry from converted IDs and compare native points."""
import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import pickle
import time


def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def compact(points):
    result=[]
    for x,y in points:
        point=(round(float(x),7),round(float(y),7))
        if not result or result[-1]!=point:result.append(point)
    return result


def main():
    import shapefile
    from pyproj import CRS,Transformer
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('coordinates','routes','network','report'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();started=time.perf_counter()
    if a.report.exists():raise FileExistsError(a.report)
    manifest=json.loads((a.routes.parent/'route_manifest.json').read_text(encoding='utf-8'))
    if sha(a.routes)!=manifest['output_sha256'] or sha(a.coordinates)!=manifest['native_sha256'] or sha(a.network)!=manifest['public_network_sha256']:
        raise ValueError('Conversion lineage changed')
    with a.coordinates.open('rb') as stream:arrays=pickle.load(stream)
    with gzip.open(a.routes,'rb') as stream:routes=pickle.load(stream)
    if len(arrays)!=len(routes):raise ValueError('Slot count changed')
    wanted={edge for row in routes for edge in row['cpath']}
    lookup={};reader=shapefile.Reader(str(a.network))
    names=[f[0] for f in reader.fields[1:]];at=names.index('id')
    transform=Transformer.from_crs(CRS.from_wkt(a.network.with_suffix('.prj').read_text()),4326,always_xy=True)
    for record in reader.iterShapeRecords():
        edge=int(record.record[at])
        if edge not in wanted:continue
        if edge in lookup:raise ValueError('Public IDs not unique')
        xx,yy=transform.transform(*zip(*record.shape.points))
        lookup[edge]=compact(zip(yy,xx))
    if set(lookup)!=wanted:raise ValueError('Missing public IDs')
    counts=Counter();bad=[]
    for i,(array,row) in enumerate(zip(arrays,routes)):
        if row['source_index']!=i:raise ValueError('Slot identity changed')
        if not row['accepted']:
            counts['excluded_representation:'+row['reason']]+=1;continue
        reconstructed=[]
        for edge in row['cpath']:
            points=lookup[edge]
            if reconstructed and points and reconstructed[-1]!=points[0]:raise ValueError('Public geometry is not consecutive')
            reconstructed.extend(points[1:] if reconstructed else points)
        if compact(array)!=compact(reconstructed):bad.append(i)
        else:counts['exact_delivered_geometry_roundtrip']+=1
        if i%1000==0:print('ROUNDTRIP_CHECKED',i,flush=True)
    result={'passed':not bad,'slot_count':len(routes),'counts':dict(counts),'mismatched_slots':bad,
        'protocol':'reconstruct full declared public polylines from converted IDs; compare original native coordinates at frozen DPMM 7-decimal node identity precision',
        'not_nearest_matching':True,'not_rerouting':True,'inputs_sha256':{str(x.resolve()):sha(x) for x in (a.coordinates,a.routes,a.network)},'seconds':time.perf_counter()-started}
    a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result),flush=True)
    if bad:raise ValueError('Geometry representation differs from delivered native arrays; no road scoring allowed')


if __name__=='__main__':main()
