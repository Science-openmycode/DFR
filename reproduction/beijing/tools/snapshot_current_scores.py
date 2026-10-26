"""Read and hash-check saved current-batch scores; never generate or evaluate trajectories."""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    if args.out.exists():
        raise FileExistsError(args.out)
    memo={}
    def digest(file):
        file=Path(file).resolve()
        if file not in memo:
            with file.open('rb') as stream:
                memo[file]=hashlib.file_digest(stream,'sha256').hexdigest()
        return memo[file]
    rows=[]
    expected_real='0a0b11c0fef09bf3267ffdeca9d9202bedb8bfd609cb7da5c381ed08dca4907c'
    for file in sorted((args.batch/'scores').glob('*/*/manifest.json')):
        meta=json.loads(file.read_text(encoding='utf-8'))
        if meta['inputs']['real_routes']['sha256']!=expected_real:
            raise ValueError('Wrong real road reference: '+str(file))
        for key in ('real_routes','synthetic_routes','metric_cache','network'):
            binding=meta['inputs'][key]
            if digest(binding['path'])!=binding['sha256']:
                raise ValueError('Changed input: '+key+' '+str(file))
        score=meta['outputs']['metrics_json']
        if digest(score['path'])!=score['sha256']:
            raise ValueError('Changed score: '+str(file))
        values=json.loads(Path(score['path']).read_text(encoding='utf-8'))
        rows.append(dict(method=meta['method'],router=meta['router'],
                         metrics=values,manifest=str(file.resolve()),
                         result_sha256=score['sha256'],hash_verified=True))
    counts={}
    for name in ('scores','coordinate_scores','physical_scores','road_tasks','tstr'):
        counts[name]=len(list((args.batch/name).glob('*/*/manifest.json')))
    report=dict(created_at_utc=datetime.now(timezone.utc).isoformat(),
                classification='LOCAL_RESEARCH_STATUS_NOT_A_DP_RELEASE',
                population=15730,road_reference_sha256=expected_real,
                direct_road_groups_verified=len(rows),manifest_counts=counts,
                count_note='Overlapping families; non-road counts are file inventory, not a new full audit.',
                rows=rows)
    args.out.mkdir(parents=True)
    (args.out/'scores.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    fields=['method','router','RoadYield','BTF','RC-CPC','EdgeCPC','TurnCPC','EdgeRecall','EdgePrecision','EdgeF1','TurnF1']
    with (args.out/'scores.csv').open('w',newline='',encoding='utf-8-sig') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(method=row['method'],router=row['router'],
                                 **{key:row['metrics'].get(key) for key in fields[2:]}))
    print(json.dumps(dict(verified=len(rows),manifest_counts=counts,out=str(args.out))))


if __name__=='__main__':
    main()
