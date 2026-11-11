"""Plot only executed four-task results; optional unchanged base-matrix context."""
import argparse
import csv
import json
import math
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import numpy as np
from .metrics import read, digest

METRICS = ['MFPOrderedRouteOverlap', 'RepresentativeRealCoverage',
           'SelectedRoadMarginalOverlap', 'IncomingExitDistributionOverlap']
LABELS = ['(a) 常走路线\n有序重合度', '(b) 代表路线\n真实行程覆盖率',
          '(c) 指定道路\n来源去向重合度', '(d) 主要路口\n出口比例重合度']


def cell_label(value, status):
    if value is not None:
        if value == 0:return '0'
        if 0 < abs(value) < .001:return f'{value:.0e}'
        return f'{value:.3f}'
    return {'POSITIVE_INFINITY_ZERO_ROAD_EVIDENCE':'∞','NOT_APPLICABLE':'n/a','MISSING':'—','EXCLUDED':'excl.'}.get(status,'NA')


def cell_color(shade):
    # Integer 1 indexes LUT entry 1; float 1.0 means the high end of the scale.
    return plt.cm.YlGnBu(float(shade))


def load_summary(folder):
    meta = read(folder/'manifest.json')
    if meta['status'] != 'COMPLETE' or meta.get('scope') != 'retrospective_four_road_applications':
        raise ValueError('Require completed four-application summary, not TSTR or old proxy scores')
    if digest(folder/'results.csv') != meta['table_sha256']:
        raise ValueError('Summary changed')
    with (folder/'results.csv').open(encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))
    if len(rows) != meta['methods'] or len({r['method'] for r in rows}) != len(rows):
        raise ValueError('Incomplete or duplicate method matrix')
    for r in rows:
        for k in METRICS:
            v = float(r[k])
            if not math.isfinite(v) or not -1e-12 <= v <= 1+1e-12:
                raise ValueError('Invalid application score')
    return meta, rows


def save(fig, out, name):
    fig.savefig(out/(name+'.png'), dpi=250, bbox_inches='tight', facecolor='white')
    fig.savefig(out/(name+'.pdf'), bbox_inches='tight', facecolor='white')
    plt.close(fig)


def display(name):
    return {'Real':'真实数据（参考）', 'MTR-DFR':'DFR（原生）', 'MTNet':'MTNet（原生）',
            'MTNet_DP_OD_coarse24':'MTNet + DPOD'}.get(name, name.replace('__', ' + '))


def heatmap(meta, rows, out, gray=False):
    values = np.array([[float(r[k]) for k in METRICS] for r in rows])
    fig, ax = plt.subplots(figsize=(10, max(5, .34*len(rows)+2)))
    fig.subplots_adjust(left=.30, right=.90, top=.88, bottom=.16)
    im = ax.imshow(values, cmap='Greys' if gray else 'Blues', vmin=0, vmax=1, aspect='auto')
    ax.set_yticks(range(len(rows)), [display(r['method']) for r in rows], fontsize=9)
    ax.set_xticks(range(4), LABELS, fontsize=9)
    ax.tick_params(length=0, pad=7)
    for i, r in enumerate(rows):
        for j in range(4):
            ax.text(j, i, f'{100*values[i,j]:.1f}', ha='center', va='center', fontsize=9,
                    color='white' if values[i,j]>.58 else '#222')
        if r['method'] == 'MTR-DFR':
            ax.add_patch(Rectangle((-.49, i-.49), 3.98, .98, fill=False, lw=1.5,
                                  edgecolor='#222' if gray else '#D55E00'))
    ax.set_xticks(np.arange(-.5, 4), minor=True); ax.set_yticks(np.arange(-.5,len(rows)), minor=True)
    ax.grid(which='minor', color='white', lw=1); ax.tick_params(which='minor', length=0)
    for s in ax.spines.values(): s.set_visible(False)
    cb = fig.colorbar(im, ax=ax, fraction=.035, pad=.025)
    cb.set_ticks([0,.25,.5,.75,1], labels=['0','25','50','75','100']); cb.set_label('重合度 / 覆盖率（%）')
    c = meta['task_counts']
    fig.suptitle('四项道路应用任务', y=.97, fontsize=17)
    fig.text(.30,.915,f"{c['od']}组OD · {c['region_trips']}条区域真实行程 · {c['roads']}条道路 · {c['incoming']}个进口",fontsize=9)
    fig.text(.30,.07,'真实数据固定题目，各合成发布回答同题；缺答贡献0。',fontsize=9)
    fig.text(.30,.035,f"代表路线最多{meta['representative_K']}条；真实参考显示实际覆盖率；每份发布对应一次观测。",fontsize=8)
    save(fig,out,'four_applications_gray' if gray else 'four_applications')


def combine(meta, app_rows, base_file, binding_file):
    binding = read(binding_file)
    if binding['dataset_id'] != meta['dataset_id'] or binding['slots'] != meta['slots'] or digest(base_file) != binding['cells_sha256']:
        raise ValueError('Base matrix belongs to a different dataset or changed')
    cells = [c for c in read(base_file) if c['metric'] in {'Grid','Trip','Len','RoadYield','BTF','FamilyCPC','ODPF384',*METRICS}]
    methods = list(dict.fromkeys(c['row'] for c in cells))
    base_metrics = list(dict.fromkeys(c['metric'] for c in cells))
    lookup = {(c['row'], c['metric']):dict(c) for c in cells}
    if len(lookup) != len(cells): raise ValueError('Duplicate base matrix cells')
    for r in app_rows:
        method = 'Real [application reference]' if r['method']=='Real' else r['method'].replace('__',' + ')
        if method not in methods: methods.append(method)
        for k in METRICS:
            if (method,k) in lookup: raise ValueError('Application metric already exists; refuse stale replacement')
            v = float(r[k]); lookup[method,k] = dict(row=method,metric=k,value=v,status='ZERO' if v==0 else 'VALID')
    all_metrics = base_metrics+METRICS
    answered={('Real [application reference]' if r['method']=='Real' else r['method'].replace('__',' + ')) for r in app_rows}
    required={m for m in methods if m.endswith('[control]')}
    if not required <= answered: raise ValueError('Missing application answers for controls: '+str(sorted(required-answered)))
    combined = []
    for method in methods:
        for k in all_metrics:
            c = lookup.get((method,k))
            if c is None:
                status='MISSING'
                if (k in METRICS and (method.endswith(' + Origin') or method.startswith('Real-'))) or (k not in METRICS and method=='Real [application reference]'):
                    status='NOT_APPLICABLE'
                if k in METRICS and method=='DPMM': status='EXCLUDED'
                c=dict(row=method,metric=k,value=None,status=status)
            combined.append(c)
    # Every original cell, including its value and status, is preserved verbatim.
    by={(c['row'],c['metric']):c for c in combined}
    if not all(by[c['row'],c['metric']]==c for c in cells): raise ValueError('Existing metric changed')
    return combined, methods, all_metrics, len(cells)


def organize_columns(cells, methods, metrics):
    """One metric-specific Real reference, with explicit per-cell provenance."""
    if any(m.endswith('[TSTR reference]') for m in methods):
        raise ValueError('Retired prediction reference is not an application reference')
    references={'Real-vs-real [geometry reference]','Real [application reference]','Real'}
    by={(c['row'],c['metric']):c for c in cells}
    tail=['MTNet','MTNet_DP_OD_coarse24','Same-endpoint random [control]',
          'Public shortest path [control]','MTR-DFR']
    ordered=[m for m in methods if m not in references and m not in tail]
    ordered += [m for m in tail if m in methods]
    result=[dict(by[m,k]) for m in ordered for k in metrics]
    if any(m in references for m in methods):
        ordered.append('Real')
        for k in metrics:
            choices=(['Real [application reference]','Real','Real-vs-real [geometry reference]']
                     if k in METRICS else ['Real-vs-real [geometry reference]','Real'])
            candidates=[by[m,k] for m in choices if (m,k) in by]
            valid=[c for c in candidates if c['value'] is not None]
            if not candidates: raise ValueError('Missing Real reference for '+k)
            source=valid[0] if valid else candidates[0]
            ref=dict(source);ref['row']='Real'
            ref['reference_source']=source.get('reference_source',source['row'])
            result.append(ref)
    return result,ordered


def highlight_runs(cells, methods, metrics):
    """Exact-score optima; ties containing DFR mark DFR only; merge adjacent rows."""
    by={(c['row'],c['metric']):c for c in cells}; selected={}
    for i,k in enumerate(metrics):
        eligible=[(j,by[m,k]['value']) for j,m in enumerate(methods)
                  if not m.upper().startswith('DPMM') and not m.startswith('Real') and not m.endswith('[control]')
                  and by[m,k]['value'] is not None and math.isfinite(by[m,k]['value'])]
        if not eligible: continue
        best=(min if k in ('Grid','Trip','Len') else max)(v for _,v in eligible)
        winners=[j for j,v in eligible if math.isclose(v,best,rel_tol=1e-12,abs_tol=1e-12)]
        if 'MTR-DFR' in methods and methods.index('MTR-DFR') in winners:
            winners=[methods.index('MTR-DFR')]
        for j in winners:selected.setdefault(j,[]).append(i)
    runs=[]
    for j,indices in selected.items():
        start=last=indices[0]
        for i in indices[1:]:
            if i==last+1:last=i
            else:runs.append((j,start,last));start=last=i
        runs.append((j,start,last))
    return runs


def matrix(cells, methods, metrics, out):
    cells,methods=organize_columns(cells,methods,metrics)
    by={(c['row'],c['metric']):c for c in cells}
    compact = len(metrics) == 11
    fig,ax=plt.subplots(figsize=(23,9) if compact else (max(16,len(methods)*.72),max(8,len(metrics)*.45+3)))
    fig.subplots_adjust(left=.16,right=.90,top=.83,bottom=.35) if compact else fig.subplots_adjust(left=.15,right=.985,top=.88,bottom=.27)
    labels={k:v.replace('\n',' ').split(') ',1)[-1] for k,v in zip(METRICS,LABELS)}
    for i,k in enumerate(metrics):
        for j,m in enumerate(methods):
            c=by[m,k]; v=c['value']; shade=0
            if v is not None:
                if k in ('Grid','Trip','Len'):shade=1-min(1,v)
                elif k=='NextRoadNLL':shade=1/(1+v)
                elif k.endswith('Retention'):shade=0 if v<=0 else min(v,1/v)
                else:shade=min(1,max(0,v))
            color=cell_color(shade) if v is not None else '#eeeeee'
            ax.add_patch(Rectangle((j-.5,i-.5),1,1,facecolor=color,edgecolor='#c9cfce',lw=.5))
            text=cell_label(v,c['status'])
            ax.text(j,i,text,ha='center',va='center',fontsize=7.5,color='white' if shade>.68 else '#17212c')
    ax.set_xlim(-.5,len(methods)-.5);ax.set_ylim(len(metrics)-.5,-.5)
    ax.set_xticks(range(len(methods)),methods,rotation=62,ha='right',fontsize=8)
    ax.set_yticks(range(len(metrics)),[labels.get(k,k) for k in metrics],fontsize=9)
    ax.tick_params(length=0)
    if compact:
        boundaries={4.5,9.5,14.5,19.5}
        for method in ['Same-endpoint random [control]','MTR-DFR','Real']:
            if method in methods: boundaries.add(methods.index(method)-.5)
        for boundary in sorted(boundaries): ax.axvline(boundary,color='#65727c',lw=1.3)
        for boundary in (2.5,3.5,6.5): ax.axhline(boundary,color='#65727c',lw=1.3)
        for title,start,end in [('统计属性\n与行程需求',0,2),('道路合法性',3,3),('路线选择\n与分布',4,6),('四项道路\n应用任务',7,10)]:
            ax.text(1.01,(start+end)/2,title,transform=ax.get_yaxis_transform(),ha='left',va='center',fontsize=10,weight='bold')
        for j,start,end in highlight_runs(cells,methods,metrics):
            ax.add_patch(Rectangle((j-.47,start-.47),.94,end-start+.94,fill=False,
                                   edgecolor='#e02020',linewidth=2,zorder=5))
    else:
        ax.axhline(len(metrics)-4.5,color='#65727c',lw=1.3)
    for s in ax.spines.values():s.set_visible(False)
    fig.suptitle(f'北京冻结道路批次 · {len(metrics)}项指标 × {len(methods)}组方法',fontsize=21,weight='bold',y=.97)
    fig.text(.5,.89 if compact else .92,'全集15730；末四行已替换为四项道路应用，其余指标保持原值。',ha='center',fontsize=11)
    if 'Real' in methods:
        fig.text(.5,.105,'Real：前七项沿用真实道路几何参考，后四项为真实数据回答同题；合并展示，不平均或改写分数。',ha='center',fontsize=9)
    footer=('Grid / Trip / Len 越低越好，其余越高越好；红框：算法最优，含DFR的并列仅标DFR，连续项合框（参考/控制/DPMM不参评）；n/a不适用，NA未定义，excl.排除。'
            if compact else 'Grid / Trip / Len / NextRoadNLL 越低越好；长度Retention目标为1，其余越高越好。n/a：不适用；—：缺失；NA：未定义；excl.：按要求排除。')
    fig.text(.5,.055,footer,ha='center',fontsize=9)
    save(fig,out,'framework_matrix_transposed')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--summary',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--base-cells',type=Path);p.add_argument('--base-binding',type=Path)
    p.add_argument('--sources',type=Path,help='Verified source matrix collected by README section 09; also render final framework')
    a=p.parse_args()
    if bool(a.base_cells)!=bool(a.base_binding): p.error('base-cells and base-binding must be supplied together')
    if a.sources and a.base_cells:p.error('Use sources or explicit base cells, not both')
    meta,rows=load_summary(a.summary);a.out.mkdir(parents=True,exist_ok=False)
    plt.rcParams.update({'font.family':'Microsoft YaHei','font.size':10,'axes.unicode_minus':False,'pdf.fonttype':42})
    heatmap(meta,rows,a.out);heatmap(meta,rows,a.out,True)
    common=0
    if a.sources:
        import csv as _csv
        from .framework import prepare_cells
        sm=read(a.sources/'manifest.json')
        population=sm.get('population') or {}
        if population.get('dataset_id')!=meta['dataset_id'] or population.get('count')!=meta['slots']:
            raise ValueError('Framework and application populations differ')
        if digest(a.sources/'matrix_sources.csv')!=sm['outputs']['matrix_sources.csv']:raise ValueError('Source matrix changed')
        cells=[]
        with (a.sources/'matrix_sources.csv').open(encoding='utf-8-sig',newline='') as f:
            for r in _csv.DictReader(f):
                if r.get('family')=='applications' and r['result_sha256']!=digest(a.summary/'results.csv'):
                    raise ValueError('Framework and standalone application scores differ')
                if r['result'] and (digest(Path(r['result']))!=r['result_sha256'] or digest(Path(r['manifest']))!=r['manifest_sha256']):
                    raise ValueError('Metric source changed')
                cells.append(dict(row=r['row'],metric=r['column'],value=None if not r['value'] else float(r['value']),status=r['status'],
                                  source=r['result'],sha256=r['result_sha256']))
        spec=read(Path(__file__).resolve().parents[2]/'reference_results/matrix/spec_framework.json')
        if digest(Path(__file__).resolve().parents[2]/'reference_results/matrix/spec_framework.json')!=sm['spec_sha256']:raise ValueError('Wrong framework spec')
        cells,methods=prepare_cells(cells,spec);metrics=spec['columns']
        matrix(cells,methods,metrics,a.out)
        (a.out/'cells.json').write_text(json.dumps(cells,ensure_ascii=False,indent=2),encoding='utf-8')
    elif a.base_cells:
        cells,methods,metrics,common=combine(meta,rows,a.base_cells,a.base_binding)
        cells,methods=organize_columns(cells,methods,metrics)
        matrix(cells,methods,metrics,a.out)
        (a.out/'cells.json').write_text(json.dumps(cells,ensure_ascii=False,indent=2),encoding='utf-8')
        with (a.out/'matrix.csv').open('x',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=['row','metric','value','status']);w.writeheader()
            w.writerows({k:c[k] for k in ['row','metric','value','status']} for c in cells)
    (a.out/'manifest.json').write_text(json.dumps(dict(status='COMPLETE',summary_sha256=digest(a.summary/'results.csv'),
          dataset_id=meta['dataset_id'],methods=len(rows),application_cells=4*len(rows),base_cells_unchanged=common,
          base_sha256=digest(a.base_cells) if a.base_cells else None,
          outputs={x.name:digest(x) for x in a.out.iterdir() if x.is_file()}),ensure_ascii=False,indent=2),encoding='utf-8')

