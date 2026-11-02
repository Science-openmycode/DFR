"""Render the saved source matrix without rerunning or altering any metric."""
import argparse
import csv
import json
import sys
import time
from collections import Counter
from pathlib import Path
import matplotlib.pyplot as plt
from figure_io import pair, read, sha, ROOT


def main():
    started=time.perf_counter()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sources', type=Path, required=True)
    p.add_argument('--previous', type=Path)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--spec',type=Path)
    p.add_argument('--github-reference',type=Path,default=ROOT/'reference_results/github/04_mr_matrix_mtr_dfr.png')
    p.add_argument('--github-sha256',default='1ce1506bd3e750798c7588ddb1eacf154760464d7d74b0becbabe7192fade4ce')
    p.add_argument('--github-commit',default='1287a73f158e242aa87f539a0643dd51ac5e018d')
    p.add_argument('--github-path',default='experiment_results/published_figures/04_mr_matrix_mtr_dfr.png')
    p.add_argument('--new-batch',action='store_true',help='Compare genuinely recomputed results; record differences instead of requiring frozen values')
    a = p.parse_args()
    if a.out.exists():
        raise FileExistsError(a.out)
    spec_path=a.spec or ROOT/'reference_results/matrix/spec_framework.json'
    spec = read(spec_path)
    receipt = read(a.sources/'manifest.json')
    assert sha(a.sources/'matrix_sources.csv') == receipt['outputs']['matrix_sources.csv']
    assert sha(spec_path) == receipt['spec_sha256']
    cells = []
    with (a.sources/'matrix_sources.csv').open(encoding='utf-8-sig', newline='') as f:
        for r in csv.DictReader(f):
            for key in ('result','manifest'):
                if r[key]:r[key]=str((ROOT/r[key]).resolve())
            if r['result']:
                assert sha(r['result']) == r['result_sha256'], r['result']
                assert sha(r['manifest']) == r['manifest_sha256'], r['manifest']
            value = None if not r['value'] else float(r['value'])
            status = r['status']
            if value is None and r['column'] == 'NextRoadNLL' and r['result']:
                ms = read(r['result']).get('metric_status', {}).get('NextRoadNLL')
                if ms == 'POSITIVE_INFINITY_ZERO_ROAD_EVIDENCE':
                    status = ms
            cells.append(dict(row=r['row'], metric=r['column'], value=value,
                              status=status, source=r['result'], sha256=r['result_sha256']))
    present={c['row'] for c in cells}
    expected=[(r,c) for r in spec['rows'] if r in present for c in spec['columns']]
    assert [(c['row'],c['metric']) for c in cells] == expected
    if spec.get('view')=='application_framework':
        sys.path.insert(0,str(ROOT))
        from evaluation.applications.framework import render
        github=a.github_reference
        assert sha(github)==a.github_sha256
        plt.rcParams.update({'font.family':'Microsoft YaHei','font.size':10,'axes.unicode_minus':False,'pdf.fonttype':42})
        report=render(cells,spec,a.out,receipt.get('population'),a.previous,github,pair)
        report.update(source_matrix_sha256=sha(a.sources/'matrix_sources.csv'),spec_sha256=sha(spec_path),
                      elapsed_seconds=time.perf_counter()-started,
                      github_commit=a.github_commit,github_path=a.github_path,github_sha256=sha(github))
        (a.out/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(dict(status='COMPLETE',shape=report['shape'],missing_applicable=0),ensure_ascii=False))
        return
    p.error('Require the current four-application framework specification')

if __name__=='__main__':
    main()
