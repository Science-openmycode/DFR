"""Prepare and verify MM2 resources from a bound city graph, without trajectories."""
import argparse
import csv
import json
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

from preprocess.dataset_contract import validate_dataset, sha

ROOT=Path(__file__).resolve().parent


def export_osm(frame, destination):
    """One directed way per canonical edge, using MM2's established id+1 convention."""
    geographic=frame.to_crs(4326)
    # The source graph may use zero/negative node labels. OSM requires positive
    # labels; a bijective relabel preserves topology and edge IDs/geometries.
    original_nodes=sorted({int(v) for column in ('source','target') for v in frame[column]})
    node_ids={v:(v if original_nodes[0]>0 else i+1) for i,v in enumerate(original_nodes)}
    nodes={};ways=[];next_node=max(node_ids.values())+1
    for row in geographic.itertuples():
        if row.geometry.geom_type!='LineString':raise ValueError('Expected line geometry')
        coords=list(row.geometry.coords);references=[]
        for i,coord in enumerate(coords):
            if i==0:node=node_ids[int(row.source)]
            elif i==len(coords)-1:node=node_ids[int(row.target)]
            else:node=next_node;next_node+=1
            if node<=0:raise ValueError('OSM node IDs must be positive')
            xy=tuple(round(float(v),10) for v in coord[:2])
            if node in nodes and nodes[node]!=xy:raise ValueError('Node has inconsistent coordinates')
            nodes[node]=xy;references.append(node)
        ways.append((int(row.id)+1,references))
    tree=ET.Element('osm',version='0.6',generator='bound-city-public-graph')
    for node,(lon,lat) in sorted(nodes.items()):
        ET.SubElement(tree,'node',id=str(node),version='1',lat=str(lat),lon=str(lon))
    for edge,refs in ways:
        way=ET.SubElement(tree,'way',id=str(edge),version='1')
        for ref in refs:ET.SubElement(way,'nd',ref=str(ref))
        ET.SubElement(way,'tag',k='highway',v='residential')
        ET.SubElement(way,'tag',k='oneway',v='yes')
    ET.ElementTree(tree).write(destination,encoding='utf-8',xml_declaration=True)


def verify_edges(frame, edges_file):
    from shapely import wkt
    expected={int(r.id)+1:r.geometry for r in frame.itertuples()}
    seen=set();max_error=0.
    with edges_file.open(encoding='utf-8',newline='') as f:
        for row in csv.DictReader(f):
            edge=int(row['id'])
            if edge not in expected or edge in seen:raise ValueError('Unexpected/duplicate MM2 edge')
            geom=wkt.loads(row['geometry']);source=expected[edge]
            a,b=list(geom.coords),list(source.coords)
            if len(a)!=len(b):raise ValueError('MM2 altered geometry vertices')
            error=max(sum((float(x)-float(y))**2 for x,y in zip(u,v))**.5 for u,v in zip(a,b))
            if error>0.001:raise ValueError('MM2 changed geometry or direction')
            max_error=max(max_error,error);seen.add(edge)
    if seen!=set(expected):raise ValueError('MM2 omitted public edges')
    return dict(edges=len(seen),max_coordinate_error_m=max_error,tolerance_m=0.001)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for arg in ('config','executable','out','out-config'):p.add_argument('--'+arg,type=Path,required=True)
    a=p.parse_args();started=time.monotonic()
    if a.out.exists() or a.out_config.exists():p.error('Output exists')
    c=json.loads(a.config.read_text(encoding='utf-8'))
    path=lambda key:(ROOT/c['paths'][key]).resolve()
    identity=validate_dataset(path('prepared'),path('network'),verify_hashes=True)
    if identity['dataset_id']!=c['frozen_dataset_id']:raise ValueError('Dataset changed')
    expected={r['path']:r['sha256'] for r in json.loads((ROOT/'external_assets.json').read_text(encoding='utf-8'))['files']}
    if sha(a.executable)!=expected['resources/mm2/map_matching_2.exe']:raise ValueError('MM2 executable changed')
    import geopandas as gpd
    frame=gpd.read_file(path('network'))
    epsg=frame.crs.to_epsg()
    if not frame.crs.is_projected or epsg is None:raise ValueError('Explicit projected EPSG required')
    if c.get('routing_crs',{}).get('network_srs')!='EPSG:'+str(epsg):
        raise ValueError('Configured routing CRS differs from public graph')
    a.out.mkdir(parents=True);public=a.out/'public_graph/inputs';public.mkdir(parents=True)
    osm=public/'public_network.osm';export_osm(frame,osm)
    (public/'public_edge_nodes.json').write_text(json.dumps({int(r.id):[int(r.source),int(r.target)] for r in frame.itertuples()}),encoding='utf-8')
    network=a.out/'network'
    command=[str(a.executable.resolve()),'--prepare','--file',str(osm.resolve()),'--output',str(network.resolve()),
        '--osm-profile','manual','--osm-query','true','--osm-filter','true','--osm-oneway','true',
        '--srs','4326','--transform-srs',str(epsg),'--simplify','osm-aware','--remove-duplicate-nodes','off',
        '--remove-duplicate-edges','off','--remove-unconnected','off','--export-edges-csv-file','edges.csv',
        '--export-nodes-csv-file','nodes.csv']
    (a.out/'command.json').write_text(json.dumps(command,ensure_ascii=False,indent=2),encoding='utf-8')
    result=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',errors='replace')
    (a.out/'stdout.log').write_text(result.stdout,encoding='utf-8');(a.out/'stderr.log').write_text(result.stderr,encoding='utf-8')
    (a.out/'exit.json').write_text(json.dumps(dict(returncode=result.returncode,elapsed_seconds=time.monotonic()-started)),encoding='utf-8')
    if result.returncode:raise RuntimeError('MM2 preparation failed: '+str(result.returncode))
    checked=verify_edges(frame,network/'edges.csv')
    binding=dict(schema='city-mm2-public-graph-v1',dataset_id=c['frozen_dataset_id'],network_sha256=sha(path('network')),
        projected_crs='EPSG:'+str(epsg),executable_sha256=sha(a.executable),returncode=result.returncode,
        files={f.relative_to(a.out).as_posix():sha(f) for f in a.out.rglob('*') if f.is_file()},
        verification=checked,elapsed_seconds=time.monotonic()-started,outer_argv=[sys.executable,*sys.argv])
    bound=a.out/'binding.json';bound.write_text(json.dumps(binding,ensure_ascii=False,indent=2),encoding='utf-8')
    c['paths'].update(mm2=str(a.executable.resolve()),mm2_network=str(network.resolve()))
    c['mm2_resources_status']='READY';c['mm2_city_binding']=dict(path=str(bound.resolve()),sha256=sha(bound))
    c['routers']=list(dict.fromkeys([*c.get('routers',[]),'MM2-MDP']))
    a.out_config.write_text(json.dumps(c,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(binding,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
