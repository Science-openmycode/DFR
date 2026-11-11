"""Public bookkeeping fixtures, not trajectory generation or scientific scores."""
import csv
import json
from pathlib import Path
import pytest
from tools.collect_current_budget import collect, sha, METHOD_ROWS, METRICS

def test_six_methods_seven_budgets_preserve_existing_aggregation(tmp_path):
    runs=[]
    for method,row in METHOD_ROWS.items():
        for eps in (.2,.4,.7,1.,1.4,2.,3.):
            for seed in (range(20260719,20260724) if method=='DFR' else ['single']):
                folder=tmp_path/method/str(eps)/str(seed);folder.mkdir(parents=True)
                release=folder/'release.json';release.write_text(json.dumps({'epsilon':eps}))
                proof=folder/'proof.json';proof.write_text('{}')
                rows=[dict(row=row,column=metric,status='VALID',value=.1,
                    result=str(proof),result_sha256=sha(proof),manifest=str(proof),manifest_sha256=sha(proof)) for metric in METRICS]
                with (folder/'matrix_sources.csv').open('w',newline='',encoding='utf-8-sig') as f:
                    w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
                (folder/'manifest.json').write_text(json.dumps(dict(population=dict(dataset_id='public-fixture',count=15730),outputs={'matrix_sources.csv':sha(folder/'matrix_sources.csv')})))
                runs.append(dict(method=method,epsilon=eps,seed=seed,sources=str(folder),release_manifest=str(release)))
    plan=tmp_path/'plan.json';plan.write_text(json.dumps(runs))
    collect(plan,tmp_path/'out')
    with (tmp_path/'out/plot_data.csv').open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
    assert len(rows)==462
    assert all(float(r['value'])==.1 for r in rows)
    assert all(r['n']==('5' if r['method']=='DFR' else '1') for r in rows)
    assert all(r['sd']=='' for r in rows if r['method']!='DFR')
    (Path(runs[0]['release_manifest'])).write_text(json.dumps({'epsilon':99}))
    with pytest.raises(ValueError,match='budget differs'):collect(plan,tmp_path/'bad')
