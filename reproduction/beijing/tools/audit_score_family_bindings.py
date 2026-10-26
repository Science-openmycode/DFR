"""Read-only source/result hash audit across saved evaluation families, no generation or rescoring."""
import argparse
import hashlib
import json
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    if args.out.exists():raise FileExistsError(args.out)
    memo={};records=[]
    def sha(file):
        file=Path(file).resolve()
        if file not in memo:
            with file.open('rb') as stream:memo[file]=hashlib.file_digest(stream,'sha256').hexdigest()
        return memo[file]
    def check(file,expected):
        if sha(file)!=expected:raise ValueError('SHA256 differs: '+str(file))
    expected_real='97ab149c54fef1bad6cb3abe1848e7dfa5cceeafe312ab2084e4d0a6d26cb8e9'
    for family in ('coordinate_scores','physical_scores','road_tasks','tstr'):
        for file in sorted((args.batch/family).glob('*/*/manifest.json')):
            meta=json.loads(file.read_text(encoding='utf-8'));checks=0
            try:
                if family=='coordinate_scores':
                    real=meta['inputs']['real']
                    if real['sha256']!=expected_real or real['count']!=15730:raise ValueError('Wrong real population')
                    for binding in meta['inputs'].values():
                        if isinstance(binding,dict) and binding.get('path') and binding.get('sha256'):
                            check(binding['path'],binding['sha256']);checks+=1
                    for name,digest in meta['outputs'].items():check(file.parent/name,digest);checks+=1
                elif family=='physical_scores':
                    binding=json.loads((file.parent/'input_binding.json').read_text())
                    if binding['real_slots']!=15730 or binding['synthetic_slots']!=15730 or binding['valid_real_slots']!=15730:
                        raise ValueError('Wrong road population')
                    command=binding['command']
                    for flag,key in (('--real-routes','real_routes'),('--synthetic-routes','synthetic_routes'),('--edge-cache','edge_cache'),('--network','network')):
                        path=command[command.index(flag)+1];check(path,meta['inputs_sha256'][key]);checks+=1
                    check(file.parent/'results.csv',meta['results_sha256']);checks+=1
                elif family=='road_tasks':
                    if meta['real_slots']!=15730 or meta['synthetic_slots']!=15730:raise ValueError('Wrong road task population')
                    for path,digest in meta['inputs'].items():check(path,digest);checks+=1
                    check(file.parent/'metrics.json',meta['result_sha256']);checks+=1
                else:
                    split=meta['split_binding']
                    if split['disjoint_split']['train_count']!=12584 or split['disjoint_split']['test_count']!=3146:
                        raise ValueError('Wrong TSTR split')
                    if not meta['synthesis_lineage_verified'] or not meta['disjoint_split_verified']:
                        raise ValueError('Unverified TSTR lineage')
                    for path,digest in meta['scoring_inputs_sha256'].items():check(path,digest);checks+=1
                    check(meta['result'],meta['results_sha256']);checks+=1
                records.append(dict(family=family,manifest=str(file),status='HASH_AND_POPULATION_VERIFIED',checks=checks))
            except Exception as error:
                records.append(dict(family=family,manifest=str(file),status='FAILED',checks_before_failure=checks,error=str(error)))
    summary={family:{status:sum(r['family']==family and r['status']==status for r in records)
                     for status in ('HASH_AND_POPULATION_VERIFIED','FAILED')}
             for family in ('coordinate_scores','physical_scores','road_tasks','tstr')}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(dict(summary=summary,records=records,
        limitation='Hash/population provenance only; not an independent reimplementation of all metric arithmetic.'),ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary))
    for row in records:
        if row['status']=='FAILED':print(json.dumps(row,ensure_ascii=False))


if __name__=='__main__':main()
