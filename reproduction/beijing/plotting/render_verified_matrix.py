"""Render the saved source matrix without rerunning or altering any metric."""
import argparse
import csv
import json
from collections import Counter
from pathlib import Path
import matplotlib.pyplot as plt
from plot_current_frozen import draw, pair, read, sha, ROOT


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sources', type=Path, required=True)
    p.add_argument('--previous', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--spec',type=Path)
    p.add_argument('--github-reference',type=Path,default=ROOT/'reference_results/github/04.png')
    p.add_argument('--new-batch',action='store_true',help='Compare genuinely recomputed results; record differences instead of requiring frozen values')
    a = p.parse_args()
    if a.out.exists():
        raise FileExistsError(a.out)
    spec_path=a.spec or ROOT/'plotting/specs/full_27x48.json'
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
    assert [(c['row'],c['metric']) for c in cells] == [(r,c) for r in spec['rows'] for c in spec['columns']]
    aliases=receipt.get('row_aliases',{})
    old = {(aliases.get(c['row'],c['row']),c['metric']):c for c in read(a.previous/'cells.json')}
    changes = []
    common = 0
    for c in cells:
        o = old[c['row'],c['metric']]
        if o['value'] is not None:
            if a.new_batch and o['value']!=c['value']:
                changes.append(dict(row=c['row'],metric=c['metric'],before=o['value'],after=c['value']))
            else:
                assert o['value'] == c['value'], ('Changed existing score',o,c)
                common += 1
        elif c['value'] is not None:
            changes.append(c)
    github = a.github_reference
    assert sha(github) == '0089b6c67abf116ac5409985b83c34caa4043006676d09738a88728cc7016aaf'
    a.out.mkdir(parents=True)
    plt.rcParams.update({'font.sans-serif':['Microsoft YaHei','DejaVu Sans'],'axes.unicode_minus':False,'pdf.fonttype':42})
    complete=receipt.get('applicable_beijing_matrix_complete',False)
    title = '北京新复现批次 · 27 × 45 · 缺失项保留' if a.new_batch else ('北京冻结道路批次 · 27 × 45 · 主矩阵适用项已齐' if complete else '北京冻结道路批次 · 27 × 45 · 主体终态汇总（未完成项保留）')
    draw(spec,cells,a.out/'current_full',title=title)
    pair(github,a.out/'current_full.png',a.out/'github_vs_current.png',('GITHUB HISTORICAL ORIGINAL - DIFFERENT COHORT / LAYOUT','CURRENT APPROVED 27 x 45 MATRIX - NOT ALL EXPERIMENTS COMPLETE'))
    comparison_label='NEW REPRODUCTION BATCH - MISSING KEPT' if a.new_batch else 'OCT 19 VERIFIED CONTROL RESULTS'
    pair(a.previous/'current_full.png',a.out/'current_full.png',a.out/'previous_vs_current.png',('PREVIOUS VERIFIED MATRIX',comparison_label))
    for i,(_,metrics) in enumerate(spec['group_headers'].items(),1):
        name=f'group_{i:02d}'
        draw(spec,cells,a.out/name,metrics,title=title)
        pair(a.previous/(name+'.png'),a.out/(name+'.png'),a.out/(name+'_comparison.png'),('PREVIOUS VERIFIED METRICS',comparison_label))
    (a.out/'cells.json').write_text(json.dumps(cells,ensure_ascii=False,indent=2),encoding='utf-8')
    report=dict(counts=dict(Counter(c['status'] for c in cells)),common_numeric_unchanged=common,new_numeric=sum('before' not in c for c in changes),changed_or_added=len(changes),changes=changes,new_batch=a.new_batch,
                source_matrix_sha256=sha(a.sources/'matrix_sources.csv'),github_commit='87be8ec856990cdec16cb4ccfb5ccc2a2c87b039',
                github_path='experiment_results/published_figures/04_mr_matrix_mtr_gsrt.png',github_sha256=sha(github),
                all_experiments_complete=False,no_metrics_modified=True,
                applicable_beijing_matrix_complete=complete,row_aliases=aliases,
                remaining=receipt.get('limitations',['DPMM formal representation applicability','two current-protocol public controls','metric definition limitations retained','extensions not included']),
                files={x.name:sha(x) for x in a.out.iterdir() if x.is_file()})
    (a.out/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':
    main()
