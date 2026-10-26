"""Historical timing only: never import old releases as current scores."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import statistics


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--csv',type=Path,required=True)
    p.add_argument('--manifest',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    if a.out.exists():raise FileExistsError(a.out)
    meta=json.loads(a.manifest.read_text())
    with a.csv.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
    assert digest==meta['output_sha256']
    csv.field_size_limit(64*1024*1024)
    ds=[];ids=[];aborted=0
    with a.csv.open(encoding='utf-8',newline='') as f:
        for row in csv.DictReader(f):
            ds.append(float(row['duration']));ids.append(int(row['id']));aborted+=row['aborted']=='yes'
    assert len(ds)==meta['records'] and len(set(ids))==len(ds)
    s=sorted(ds)
    result=dict(historical_only=True,not_current_scores=True,records=len(ds),aborted=aborted,
                duration_sum_seconds=sum(ds),duration_mean_seconds=statistics.mean(ds),
                duration_p50=s[(len(s)-1)//2],duration_p99=s[int((len(s)-1)*.99)],
                duration_max=max(ds),slowest=sorted(zip(ds,ids),reverse=True)[:10],
                csv_sha256=digest,
                limitation='Per-track matching durations, not whole wall clock; old network/population/platform differ')
    a.out.write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))


if __name__=='__main__':main()
