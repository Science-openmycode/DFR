"""Stage a saved statistical M/R output for TSTR, without rerouting or scoring."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.coordinate_resource_binding import coordinate_resources
from tools.stage_routed_coordinates import stage


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',type=Path,required=True)
    p.add_argument('--routes',type=Path,required=True)
    p.add_argument('--measurement',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    c=json.loads(a.config.read_text(encoding='utf-8'))
    manifest=a.routes.parent/'route_manifest.json'
    router=json.loads(manifest.read_text(encoding='utf-8'))['router']
    cache, options=coordinate_resources(c,ROOT,router,manifest)
    result=stage(a.routes,manifest,ROOT/c['paths']['network'],a.out,
                 measurement=a.measurement,edge_cache=cache,**options)
    print(json.dumps({'record_count':result['record_count'],'coordinates':result['coordinates'],
                      'mode':'representation_only_no_new_routes'}))


if __name__=='__main__':
    main()
