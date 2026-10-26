"""Bounded, streaming read of live native CSV; no process access or mutation."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import statistics
import time
from datetime import datetime, timezone


def snapshot(path, expected):
    csv.field_size_limit(64*1024*1024)
    ids = []
    durations = []
    aborted = 0
    with path.open('rb') as f:
        f.seek(0,2)
        bound = f.tell()
        f.seek(0)
        header = f.readline().decode('utf-8-sig').strip()
        assert header == 'id,aborted,duration,match,edge_ids'
        while f.tell() < bound:
            raw = f.readline(min(64*1024*1024, bound-f.tell()))
            if not raw.endswith(b'\n'):
                break
            # MM2 WKT/edge_ids have no embedded newlines under this frozen schema.
            row = next(csv.reader([raw.decode('utf-8')]))
            if len(row) != 5:
                break
            slot, _, duration, _, _ = row
            ids.append(int(slot));durations.append(float(duration))
            aborted += row[1] == 'yes'
    ordered = sorted(durations)
    quantile = lambda q: ordered[min(len(ordered)-1,int((len(ordered)-1)*q))] if ordered else None
    return dict(sample_utc=datetime.now(timezone.utc).isoformat(), path=str(path),
                handle_eof_bytes=bound, complete_rows=len(ids), expected_slots=expected,
                completed_fraction=len(ids)/expected, unique_ids=len(set(ids)),
                contiguous_prefix=ids==list(range(len(ids))), last_id=ids[-1] if ids else None,
                aborted_rows=aborted, duration_sum=sum(durations),
                duration_mean=statistics.mean(durations) if durations else None,
                duration_p50=quantile(.5), duration_p90=quantile(.9), duration_p99=quantile(.99),
                duration_max=max(durations,default=None),
                last100_mean=statistics.mean(durations[-100:]) if durations else None,
                slowest=sorted(zip(durations,ids),reverse=True)[:10],
                caveat='Complete live CSV rows are progress evidence, not final manifest acceptance')


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--interval',type=float,default=30)
    a=p.parse_args()
    if a.out.exists():raise FileExistsError(a.out)
    files=[(a.root/'results/roads_8_16_20261016/routes/DPTraj-PM/MM2-MDP/mm2_run/matches.csv',15730),
           (a.root/'results/roads_8_16_20261016/train_only/routes/DPTraj-PM/MM2-MDP/mm2_run/matches.csv',12584)]
    first=[snapshot(f,n) for f,n in files]
    time.sleep(a.interval)
    second=[snapshot(f,n) for f,n in files]
    report=dict(read_only=True,first=first,second=second,
                row_deltas=[b['complete_rows']-c['complete_rows'] for c,b in zip(first,second)],
                script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    a.out.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))


if __name__=='__main__':main()
