"""Compare parsed aggregate values to a saved reference, ignoring file formatting."""
import argparse
import json
import math
from pathlib import Path

def compare(actual,reference,*,kind):
    if kind=='budget':
        def index(payload):
            return {(r['stage'],r['metric'],float(r['epsilon'])):r for r in payload['aggregates']}
        left,right=index(actual),index(reference)
    else:
        left,right=actual['paired_summary'],reference
    stats={'numeric_values':0,'max_absolute_difference':0.0}
    def visit(a,b,path):
        if isinstance(a,dict) and isinstance(b,dict):
            if a.keys()!=b.keys():raise ValueError('Different fields at '+path)
            for key in a:visit(a[key],b[key],path+'/'+str(key))
        elif isinstance(a,list) and isinstance(b,list):
            if len(a)!=len(b):raise ValueError('Different lengths at '+path)
            for i,(x,y) in enumerate(zip(a,b)):visit(x,y,path+'/'+str(i))
        elif type(a) in (int,float) and type(b) in (int,float):
            gap=abs(a-b);stats['numeric_values']+=1
            stats['max_absolute_difference']=max(stats['max_absolute_difference'],gap)
            if not math.isclose(a,b,rel_tol=1e-12,abs_tol=1e-12):raise ValueError('Different numeric value at '+path)
        elif a!=b:raise ValueError('Different value at '+path)
    visit(left,right,'summary')
    return dict(status='PASSED',kind=kind,aggregate_groups=len(left),**stats)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--kind',choices=('budget','k'),required=True)
    for name in ('actual','reference','out'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    if a.out.exists():raise FileExistsError(a.out)
    result=compare(json.loads(a.actual.read_text(encoding='utf-8')),
                   json.loads(a.reference.read_text(encoding='utf-8')),kind=a.kind)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))

if __name__=='__main__':main()
