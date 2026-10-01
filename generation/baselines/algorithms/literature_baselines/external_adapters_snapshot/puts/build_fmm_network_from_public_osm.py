"""Build a directed FMM network from a public, already-filtered OSM way cache."""
from __future__ import annotations
import argparse
import pickle
from pathlib import Path
import geopandas as gpd
import networkx as nx
from pyproj import Transformer
from shapely.geometry import LineString

def main() -> None:
    p=argparse.ArgumentParser(); p.add_argument('--osm-cache',type=Path,required=True); p.add_argument('--out',type=Path,required=True); a=p.parse_args()
    ways=pickle.load(a.osm_cache.open('rb')); to_utm=Transformer.from_crs('EPSG:4326','EPSG:32650',always_xy=True)
    nodes={}; rows=[]; next_node=1; next_edge=1
    def nid(value):
        nonlocal next_node
        key=str(value)
        if key not in nodes: nodes[key]=next_node; next_node+=1
        return nodes[key]
    def add(points, start, end, highway):
        nonlocal next_edge
        xy=[to_utm.transform(lon,lat) for lat,lon in points]; line=LineString(xy)
        if line.length:
            rows.append({'id':next_edge,'source':nid(start),'target':nid(end),'length_m':float(line.length),'highway':str(highway)[:30],'geometry':line}); next_edge+=1
    for way in ways:
        tags=way.get('tags',{}); pts=[(float(x['lat']),float(x['lon'])) for x in way.get('geometry',[]) if 'lat' in x and 'lon' in x]; ids=way.get('nodes',[])
        if len(pts)<2 or len(ids)<2: continue
        oneway=str(tags.get('oneway','')).lower()
        if oneway not in {'-1','reverse'}: add(pts,ids[0],ids[-1],tags.get('highway','road'))
        if oneway not in {'yes','true','1'}: add(list(reversed(pts)),ids[-1],ids[0],tags.get('highway','road'))
    graph=nx.DiGraph(); graph.add_edges_from((x['source'],x['target']) for x in rows)
    largest=max(nx.weakly_connected_components(graph),key=len); rows=[x for x in rows if x['source'] in largest and x['target'] in largest]
    a.out.parent.mkdir(parents=True,exist_ok=True); gpd.GeoDataFrame(rows,geometry='geometry',crs='EPSG:32650').to_file(a.out,index=False)
    print(f'wrote {len(rows):,} directed public OSM edges to {a.out}',flush=True)
if __name__=='__main__': main()
