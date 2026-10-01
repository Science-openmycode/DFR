"""Build the public 3,000-road PUTS Beijing graph cache for a fair adapter run."""
from __future__ import annotations
import argparse, pickle
from pathlib import Path

def main() -> None:
    p=argparse.ArgumentParser(); p.add_argument('--geometry',type=Path,required=True); p.add_argument('--cpath',type=Path); p.add_argument('--out',type=Path,required=True); a=p.parse_args()
    used=None
    if a.cpath:
        used=set()
        for line in a.cpath.read_text(encoding='utf-8',errors='ignore').splitlines():
            used.update(int(x) for x in line.strip().split(',') if x.strip())
    ways=[]
    for index,line in enumerate(a.geometry.read_text(encoding='utf-8',errors='ignore').splitlines()):
        if used is not None and index not in used: continue
        text=line.strip().removeprefix('LINESTRING (').removesuffix(')')
        geometry=[]
        for token in text.split(','):
            try:
                lon,lat=map(float,token.strip().split()[:2])
                # PUTS stores independently rounded segment endpoints.  Canonicalize
                # public coordinates so the MTR graph builder recovers the same
                # junctions instead of fragmenting the road graph by float noise.
                geometry.append({'lat':round(lat, 5),'lon':round(lon, 5)})
            except ValueError: continue
        if len(geometry)>=2: ways.append({'id':index,'geometry':geometry})
    if not ways: raise RuntimeError('no drawable PUTS roads')
    a.out.parent.mkdir(parents=True,exist_ok=True)
    with a.out.open('wb') as f: pickle.dump(ways,f,pickle.HIGHEST_PROTOCOL)
    print(f'wrote {len(ways)} public PUTS roads to {a.out}')
if __name__=='__main__': main()
