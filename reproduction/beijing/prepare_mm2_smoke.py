"""Prepare artificial public-geometry tracks; never read private trajectories."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import pickle

from pyproj import Transformer
from shapely import wkt

ROOT=Path(__file__).resolve().parent

def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--network',type=Path,default=ROOT/'resources/network/network.shp',
                        help='Public SHP for the same edge namespace as the installed MM2 network')
    args=parser.parse_args()
    out=args.out.resolve()
    if out.exists():raise FileExistsError(out)
    binding=json.loads((ROOT/'resources/mm2/binding.json').read_text())
    for relative,expected in binding['files'].items():
        if sha(ROOT/relative)!=expected:raise ValueError('Changed public MM2 resource: '+relative)
    transform=Transformer.from_crs(32650,4326,always_xy=True).transform
    tracks=[];ids=[]
    with (ROOT/'resources/mm2/network/edges.csv').open(encoding='utf-8',newline='') as stream:
        for row in csv.DictReader(stream):
            line=wkt.loads(row['geometry'])
            if line.geom_type!='LineString' or line.length<30:continue
            points=[line.interpolate(fraction,normalized=True) for fraction in (.2,.5,.8)]
            lonlat=[transform(point.x,point.y) for point in points]
            tracks.append([[lat,lon] for lon,lat in lonlat]);ids.append(row['id'])
            if len(tracks)==2:break
    if len(tracks)!=2:raise ValueError('Insufficient public geometry for fixture')
    tracks.append([])
    out.mkdir(parents=True)
    measurement=out/'measurement';measurement.mkdir()
    with (measurement/'measurement.pkl').open('wb') as stream:pickle.dump(tracks,stream)
    meta={'classification':'ARTIFICIAL_PUBLIC_GEOMETRY_TEST_NOT_FORMAL_RESULTS',
          'public_edge_ids':ids,'private_trajectories_read':False,'records':3,
          'measurement_sha256':sha(measurement/'measurement.pkl'),
          'resource_binding_sha256':sha(ROOT/'resources/mm2/binding.json')}
    (measurement/'measurement_manifest.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
    prepared=out/'unused_prepared';prepared.mkdir()
    paths={'prepared':str(prepared),'output':str(out/'unused_results'),'legacy':str(ROOT/'legacy'),
           'edge_cache':str(ROOT/'resources/edge_cache/edge_cache.pkl.gz'),
           'network':str(args.network.resolve()),
           'mm2':str(ROOT/'resources/mm2/map_matching_2.exe'),
           'mm2_network':str(ROOT/'resources/mm2/network')}
    (out/'config.json').write_text(json.dumps({'dataset':'artificial_public_geometry',
        'batch':'not_formal_results','paths':paths},indent=2),encoding='utf-8')
    print(json.dumps(meta))

if __name__=='__main__':main()
