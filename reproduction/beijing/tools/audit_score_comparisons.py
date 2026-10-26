"""Audit saved scores and every historical candidate without changing any metric/output."""
import argparse
import csv
import gzip
import importlib.util
import json
import math
import os
from pathlib import Path
import pickle

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--batch',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    if a.out.exists():raise FileExistsError(a.out)
    source=Path(os.environ.get('DFR_LEGACY_ROOT', str(ROOT/'legacy')))/'evaluation/route_metric_core.py'
    spec=importlib.util.spec_from_file_location('audited_core',source)
    core=importlib.util.module_from_spec(spec);spec.loader.exec_module(core)
    # A deliberately tiny exact example, not new real-data measurements.
    pairs={1:(0,1),2:(1,2),3:(1,3)}
    cache=dict(edge_nodes=pairs,outdegree={0:1,1:2,2:0,3:0},
               labels24={i:i for i in range(4)},labels96={i:i for i in range(4)},
               labels384={i:i for i in range(4)})
    real=[((0,1),(1,2)),((0,1),(1,3))]
    identical=core.evaluate_routes(real,real,cache)
    half_empty=core.evaluate_routes(real+[(),()],real,cache)
    altered=dict(cache,labels96={i:0 for i in range(4)})
    label_test=core.evaluate_routes(real,real,altered)
    changed_route=[((0,1),(1,2)),((0,1),(1,2))]
    label_before=core.evaluate_routes(changed_route,real,cache)
    label_after=core.evaluate_routes(changed_route,real,altered)
    assert identical['BTF']==1 and half_empty['BTF']==.5
    assert identical['RoadYield']==1 and half_empty['RoadYield']==.5
    for key in ('RC-CPC','EdgeCPC','TurnCPC'):
        assert identical[key]==half_empty[key]
        assert label_before[key]==label_after[key]
    assert label_before['BTF']==label_after['BTF']
    candidates=[]
    roots=[(ROOT/'data_results/simple_runs/corrected_20261013/scores','corrected-SPRT-only'),
           (ROOT/'local_batches/beijing_full_17123_batch_001_20261011/simple_evaluation_20261013','historical-preserved-not-protocol-equivalent'),
           (ROOT/'../retired_wrong_baseline_versions_20261013/local_batches/beijing_full_17123_batch_001_20261011/simple_evaluation_20261013','RETIRED_WRONG_BASELINE_NOT_VALID_COMPARATOR')]
    for folder,label in roots:
        for file in folder.rglob('metrics.json'):
            values=json.loads(file.read_text(encoding='utf-8'))
            mf=file.parent/'manifest.json'
            if 'BTF' not in values or not mf.exists():continue
            meta=json.loads(mf.read_text(encoding='utf-8'))
            candidates.append(dict(label=label,path=str(file.resolve()),values=values,manifest=meta))
    checked=[];long=[];public_edges=None
    for mf in sorted((a.batch/'scores').glob('*/*/manifest.json')):
        meta=json.loads(mf.read_text(encoding='utf-8'))
        file=Path(meta['outputs']['metrics_json']['path'])
        score=json.loads(file.read_text(encoding='utf-8'))
        if public_edges is None:
            public_edges=core.load_pickle(Path(meta['inputs']['metric_cache']['path']))['edge_nodes']
        path=Path(meta['inputs']['synthetic_routes']['path'])
        with gzip.open(path,'rb') as stream:raw=pickle.load(stream)
        if len(raw)!=15730:raise ValueError('Wrong current slots')
        accepted=0
        for index,row in enumerate(raw):
            if row.get('source_index')!=index:raise ValueError('Slot order/identity changed')
            ids=row['cpath']
            if not row['accepted'] or not ids:continue
            if any(i not in public_edges for i in ids):raise ValueError('Unknown edge')
            if any(public_edges[u][1]!=public_edges[v][0] for u,v in zip(ids,ids[1:])):continue
            accepted+=1
        del raw
        independent_yield=accepted/15730
        assert math.isclose(independent_yield,score['RoadYield'],abs_tol=1e-15)
        assert accepted==meta['synthetic']['valid_routes']
        assert meta['real']['slots']==meta['real']['reference_slots']==15730
        matches=[x for x in candidates if x['manifest'].get('method')==meta['method'] and
                 (x['manifest'].get('router')==meta['router'] or
                  meta['router']=='Origin' and x['manifest'].get('router')=='Native')]
        record=dict(method=meta['method'],router=meta['router'],current_path=str(file),
                    current_values=score,slots=15730,independent_valid=accepted,
                    independent_yield=independent_yield,real_reference_slots=15730,
                    historical_candidates=[])
        for old in matches:
            om=old['manifest']; same={k:meta['inputs'][k]['sha256']==om['inputs'][k]['sha256']
                                     for k in ('real_routes','synthetic_routes','metric_cache','network')}
            entry=dict(classification=old['label'],path=old['path'],same_input_hashes=same,
                       old_real=om.get('real'),old_synthetic=om.get('synthetic'),
                       same_metric_core=meta['metric_core']['sha256']==om.get('metric_core',{}).get('sha256'),
                       comparisons={})
            for metric,value in score.items():
                before=old['values'].get(metric)
                if isinstance(value,(int,float)) and isinstance(before,(int,float)):
                    entry['comparisons'][metric]=dict(old=before,new=value,delta=value-before)
                    long.append(dict(method=meta['method'],router=meta['router'],metric=metric,
                                     old_classification=old['label'],old=before,new=value,delta=value-before,
                                     old_path=old['path'],new_path=str(file)))
            record['historical_candidates'].append(entry)
        checked.append(record)
        print('AUDITED',meta['method'],meta['router'],accepted,flush=True)
    a.out.mkdir(parents=True)
    report=dict(scope='All completed current direct-road groups, not all unfinished matrix cells',
                current_groups=len(checked),current=checked,
                semantic_tests=dict(identity=identical,half_empty=half_empty,
                                    labels96_before=label_before,labels96_after=label_after),
                limitations=['No independent full BTF recomputation on real corpus in this audit',
                             'Historical retired candidates are diagnostic only, not valid official baselines',
                             'Coordinate/physical/TSTR score families require separate source audits'])
    (a.out/'audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    with (a.out/'all_metric_differences.csv').open('w',newline='',encoding='utf-8-sig') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(long[0]) if long else ['method'])
        writer.writeheader();writer.writerows(long)
    print('DONE',len(checked),'current groups',len(long),'historical metric comparisons')


if __name__=='__main__':main()
