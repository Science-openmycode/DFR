"""Add one verified release to an existing city question config, without rerunning other methods."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from evaluation.applications.engine import load_config
from evaluation.applications.metrics import digest

def extend(config,slots,name,out):
    out=Path(out);slots=Path(slots).resolve()
    if out.exists():raise FileExistsError('Use a new application config')
    c=load_config(Path(config));c.pop('config_path')
    if not name or name in {r['name'] for r in c['methods']}:raise ValueError('Duplicate/empty release name')
    m=json.loads((slots.parent/'manifest.json').read_text('utf-8-sig'))
    if m.get('status')!='COMPLETE' or m['slots']!=c['slots'] or m['public_edges_sha256']!=digest(c['public_edges']) or m['output_sha256']!=digest(slots):
        raise ValueError('Release slots, public graph or input binding differs')
    for key in ['public_edges','questions','region','resources']:c[key]=str(c[key].resolve())
    for r in c['methods']:r['slots']=str(r['slots'].resolve())
    c['methods'].append(dict(name=name,slots=str(slots),sha256=digest(slots)))
    out.parent.mkdir(parents=True,exist_ok=True)
    with out.open('x',encoding='utf-8') as f:json.dump(c,f,ensure_ascii=False,indent=2)
    return c

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ['config','slots','name','out']:p.add_argument('--'+key,required=True)
    a=p.parse_args();extend(a.config,a.slots,a.name,a.out)
    print('ADDED_APPLICATION_RELEASE',a.name,a.out)

if __name__=='__main__':main()
