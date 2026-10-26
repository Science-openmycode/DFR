"""Plot saved, hash-checked current-population scores; never execute an evaluator."""
import argparse
from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
REAL = '0a0b11c0fef09bf3267ffdeca9d9202bedb8bfd609cb7da5c381ed08dca4907c'
REAL_COORD = '97ab149c54fef1bad6cb3abe1848e7dfa5cceeafe312ab2084e4d0a6d26cb8e9'
TRAIN = '562389dd960b9e4179c7a7843bc39d8c5e20e8d69d72c8ecf4ba2183a49f7d1c'
TEST = '4f8a3bb46ad2ff3ec61c9f63795c880ed979dbe61df9af189489d0217111e713'
TASKS = dict(zip(['Next-cell Hit@1','Next-cell MRR','Destination Hit@5','Destination MRR','Road continuation Hit@1','Road continuation MRR','Route retrieval NDCG@5'], ['NextCellHit1','NextCellMRR','DestinationHit5','DestinationMRR','RoadContinuationHit1','RoadContinuationMRR','RouteRetrievalNDCG5']))
COORD = {'grid_density_jsd':'Grid','trip_error':'Trip','path_length_jsd':'Len','directed_road_validity':'DirValid','witness_valid':'WitnessValid'}
PHYSICAL = {'RoadRecovery','RoadSupport','TurnRecovery','TurnSupport','BackboneRecovery','BackboneSupport'}
memo = {}


def sha(path):
    path = Path(path)
    if path not in memo:
        with path.open('rb') as stream:
            memo[path] = hashlib.file_digest(stream,'sha256').hexdigest()
    return memo[path]


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def check(path, expected):
    if sha(path) != expected:
        raise ValueError('Changed result/input: '+str(path))


def row_name(method, router):
    return method if method in ('MTR-DFR','MTNet','DPMM') else method+' + '+router


def collect(batch, spec):
    cells = {}
    sources = []
    real_train_reference = None
    def add(row, metric, value, file, protocol, status=None):
        if metric not in spec['columns']:
            return
        if (row, metric) in cells:
            raise ValueError('Duplicate cell: '+str((row,metric)))
        if value is None:
            state = status or 'NA'
        else:
            value = float(value)
            state = 'ZERO' if value == 0 else 'VALID'
            if not math.isfinite(value):
                raise ValueError('Nonfinite value without explicit status')
        cells[row,metric] = dict(row=row,metric=metric,value=value,status=state,source=str(file),sha256=sha(file),protocol=protocol)
    for meta_file in sorted((batch/'scores').glob('*/*/manifest.json')):
        meta = read(meta_file)
        assert meta['inputs']['real_routes']['sha256'] == REAL
        for key in ('real_routes','synthetic_routes','metric_cache','network'):
            b = meta['inputs'][key]; check(b['path'],b['sha256'])
        out = meta['outputs']['metrics_json']; check(out['path'],out['sha256'])
        file = Path(out['path']); values = read(file)
        row = row_name(meta['method'],meta['router'])
        for metric,value in values.items():
            add(row,metric,value,file,'saved-road-evaluation-v1')
        sources.append(str(meta_file))
    # The isolated server receipts take precedence ONLY when the local copy is
    # byte-identical; a disagreement is an error, never a silent overwrite.
    coord = {}
    for folder in ('coordinate_scores_audit_v2','remote_scores_1314'):
        for meta_file in sorted((batch/folder).glob('*/*/manifest.json')):
            key = (meta_file.parent.parent.name,meta_file.parent.name)
            if key in coord:
                check(meta_file.parent/'metrics.json',sha(coord[key].parent/'metrics.json'))
            coord[key] = meta_file
    for (method,router), meta_file in coord.items():
        meta=read(meta_file); file=meta_file.parent/'metrics.json'
        assert meta['inputs']['real']['sha256']==REAL_COORD and meta['inputs']['real']['count']==15730
        for name,value in meta['outputs'].items():check(meta_file.parent/name,value)
        rev=read(meta_file.parent/'metric_revision.json')
        assert rev['protocol']=='metric-audit-v2-20261016'
        values=read(file); statuses=values.get('metric_status',{})
        for key,metric in COORD.items():
            if key in values['metrics']:
                st=statuses.get(key,'NA'); st=st.get('status','NA') if isinstance(st,dict) else st
                add(row_name(method,router),metric,values['metrics'][key],file,rev['protocol'],st)
        sources.append(str(meta_file))
    for meta_file in sorted((batch/'physical_scores').glob('*/*/manifest.json')):
        meta=read(meta_file); assert meta['inputs_sha256']['real_routes']==REAL
        file=meta_file.parent/'results.csv'; check(file,meta['results_sha256'])
        with file.open(encoding='utf-8-sig',newline='') as stream: records=list(csv.DictReader(stream))
        assert len(records)==1
        item=records[0]; row=row_name(meta_file.parent.parent.name,meta_file.parent.name)
        for metric in PHYSICAL:add(row,metric,item[metric],file,meta['protocol'])
        sources.append(str(meta_file))
    for meta_file in sorted((batch/'road_tasks').glob('*/*/manifest.json')):
        meta=read(meta_file); assert meta['real_slots']==15730 and meta['dataset_id']=='afeddd66f0c6d5281dad5980bd56a8b62ffbd87ed53cd92493761a516ff1af35'
        file=meta_file.parent/'metrics.json'; check(file,meta['result_sha256'])
        obj=read(file); row=row_name(meta_file.parent.parent.name,meta_file.parent.name)
        for metric in ('RC-NDCG','NextRoadAcc','NextRoadNLL'):
            status=obj['metric_status'].get(metric)
            add(row,metric,obj['metrics'][metric],file,'road-choice-retrospective-384',status)
        sources.append(str(meta_file))
    for meta_file in sorted((batch/'tstr_audit_v2').glob('*/*/manifest.json')):
        meta=read(meta_file); split=meta['split_binding']
        assert split['train_sha256']==TRAIN and split['test_sha256']==TEST
        assert meta['synthesis_lineage_verified'] and meta['disjoint_split_verified']
        file=meta_file.parent/'results.csv'; check(file,meta['results_sha256'])
        rev=read(meta_file.parent/'metric_revision.json'); assert rev['protocol']=='metric-audit-v2-20261016'
        with file.open(encoding='utf-8-sig',newline='') as stream: items=list(csv.DictReader(stream))
        references=[x for x in items if x['Pipeline']=='Real-train']; assert len(references)==1
        reference={metric:float(references[0][key]) for key,metric in TASKS.items()}
        if real_train_reference is None:
            real_train_reference=reference
            for metric,value in reference.items():
                add('Real-train [TSTR reference]',metric,value,file,'strict-tstr-audit-v2-relative-clipped')
        else:
            assert real_train_reference==reference, 'Inconsistent real-train reference'
        items=[x for x in items if x['Pipeline']!='Real-train']; assert len(items)==1
        row=row_name(meta_file.parent.parent.name,meta_file.parent.name)
        for key,metric in TASKS.items():add(row,metric,items[0][key],file,'strict-tstr-audit-v2-relative-clipped')
        sources.append(str(meta_file))
    return [cells.get((row,metric),dict(row=row,metric=metric,value=None,status='MISSING',source='',sha256='',protocol='')) for row in spec['rows'] for metric in spec['columns']], sources


def label(cell):
    if cell['status']=='NOT_APPLICABLE':return 'n/a'
    if cell['value'] is None:
        return '∞' if cell['status']=='POSITIVE_INFINITY_ZERO_ROAD_EVIDENCE' else ('NA' if cell['status']!='MISSING' else '—')
    value=cell['value']
    if 0<abs(value)<.001:return f'{value:.0e}'
    return f'{value:.3f}'


def draw(spec, cells, out, metrics=None, placeholder=False, title=None):
    rows=spec['rows']; metrics=metrics or spec['columns']; by={(c['row'],c['metric']):c for c in cells}
    full=len(metrics)==len(spec['columns'])
    fig,ax=plt.subplots(figsize=(36 if full else max(12,len(metrics)*1.05),14))
    fig.subplots_adjust(left=.15 if full else .23,right=.995,bottom=.255,top=.82)
    ax.set_xlim(-.5,len(metrics)-.5); ax.set_ylim(len(rows)-.5,-.5)
    ax.set_xticks(range(len(metrics)),metrics,rotation=62,fontsize=8 if full else 10,ha='right')
    ax.set_yticks(range(len(rows)),rows,fontsize=9); ax.tick_params(length=0)
    for spine in ax.spines.values():spine.set_visible(False)
    for i,row in enumerate(rows):
        for j,metric in enumerate(metrics):
            c=by[row,metric]; value=c['value']; t=0; color='#eeeeee'
            if placeholder: color=plt.cm.YlGnBu(0)
            elif value is not None:
                if metric in ('Grid','Trip','Len'): t=1-min(1,value)
                elif metric=='NextRoadNLL':t=1/(1+value)
                elif metric.endswith('Retention'):t=0 if value<=0 else min(value,1/value)
                else:t=min(1,max(0,value))
                color=plt.cm.YlGnBu(float(t))
            ax.add_patch(Rectangle((j-.5,i-.5),1,1,facecolor=color,edgecolor='#c9cfce',linewidth=.5))
            ax.text(j,i,'0' if placeholder else label(c),ha='center',va='center',fontsize=7 if full else 9,color='white' if t>.68 and not placeholder else '#17212c')
    for i in (4.5,9.5,14.5,19.5,22.5):ax.axhline(i,color='#65727c',lw=1.25)
    d=rows.index('MTR-DFR');ax.add_patch(Rectangle((-.5,d-.5),len(metrics),1,fill=False,edgecolor='#d95f59',linewidth=2))
    cursor=0
    groups=dict(spec['group_headers'])
    groups.pop('下一道路任务',None)
    groups['下一道路任务']=['NextRoadAcc','NextRoadNLL']
    groups['严格TSTR下游任务（相对保留率）']=list(TASKS.values())
    for group,cols in groups.items():
        present=[metrics.index(x) for x in cols if x in metrics]
        if not present:continue
        ax.text(sum(present)/len(present),1.03,group,ha='center',va='bottom',transform=ax.get_xaxis_transform(),fontsize=9 if len(present)<3 else 11,weight='bold')
        if min(present)>0:ax.axvline(min(present)-.5,color='#65727c',lw=1.2)
    fig.suptitle('批准布局占位稿（非成绩）' if placeholder else (title or f'当前冻结道路批次 · 27行 × {len(metrics)}列 · 已完成指标预览'),fontsize=23,weight='bold',y=.975)
    fig.text(.5,.91,'全集15730；严格TSTR训练12584 / 测试3146；ε请求值1.4；原生方法只占一行，不复制为多个R。',ha='center',fontsize=12)
    fig.text(.5,.075,'— = 未完成/未接通；NA = 已计算但未定义；0 = 实测零；∞ = 零道路证据对应的无限NLL。',ha='center',fontsize=12)
    fig.text(.5,.045,'数字为原值。深色按指标方向表示：Grid/Trip/Len越低越深，NLL用1/(1+NLL)，结构Retention越接近1越深；其余越高越深。',ha='center',fontsize=10)
    fig.text(.5,.02,spec.get('task_footer','TSTR七列为截断相对保留率，不是原始准确率；BTF仍是当前物理路口定义，含分叉处直行；不是区域分辨率BTF。'),ha='center',fontsize=10,color='#9b302b')
    if spec.get('extra_note'):
        fig.text(.5,-.005,spec['extra_note'],ha='center',fontsize=9,color='#523b35')
    fig.savefig(out.with_suffix('.png'),dpi=170,bbox_inches='tight',facecolor='white')
    fig.savefig(out.with_suffix('.pdf'),bbox_inches='tight',facecolor='white');plt.close(fig)


def pair(left,right,path,labels):
    a=Image.open(left).convert('RGB');b=Image.open(right).convert('RGB')
    width=max(a.width,b.width); a=a.resize((width,round(a.height*width/a.width)));b=b.resize((width,round(b.height*width/b.width)))
    canvas=Image.new('RGB',(2*width+40,max(a.height,b.height)+70),'white')
    canvas.paste(a,(0,70));canvas.paste(b,(width+40,70))
    pen=ImageDraw.Draw(canvas);pen.text((15,20),labels[0],fill='black');pen.text((width+55,20),labels[1],fill='black');canvas.save(path)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--batch',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    if a.out.exists():raise FileExistsError(a.out)
    spec=read(ROOT/'plotting/specs/full_27x48.json'); cells,sources=collect(a.batch.resolve(),spec)
    a.out.mkdir(parents=True)
    (a.out/'cells.json').write_text(json.dumps(cells,ensure_ascii=False,indent=2),encoding='utf-8')
    plt.rcParams.update({'font.sans-serif':['Microsoft YaHei','DejaVu Sans'],'axes.unicode_minus':False,'pdf.fonttype':42})
    draw(spec,cells,a.out/'current_full');draw(spec,cells,a.out/'approved_layout',placeholder=True)
    pair(a.out/'approved_layout.png',a.out/'current_full.png',a.out/'layout_vs_current.png',('APPROVED 27 x 45 LAYOUT - ZERO PLACEHOLDERS','CURRENT 15730 COHORT - REAL MEASURED SCORES'))
    github=ROOT.parent/'dfr_all_figure_pairs_20261007/reference/04.png'
    pair(github,a.out/'current_full.png',a.out/'github_vs_current.png',('GITHUB PINNED GSRT HISTORICAL MR FIGURE - DIFFERENT COHORT / LAYOUT','CURRENT USER-APPROVED BIG MATRIX - NOT A LIKE-FOR-LIKE REPLACEMENT'))
    for i,(group,metrics) in enumerate(spec['group_headers'].items(),1):draw(spec,cells,a.out/f'group_{i:02d}',metrics)
    counts=Counter(c['status'] for c in cells)
    report=dict(scope='SAVED_RESULT_PLOT_ONLY',no_experiments_executed=True,rows=spec['rows'],columns=spec['columns'],counts=dict(counts),sources=sources,github_commit='87be8ec856990cdec16cb4ccfb5ccc2a2c87b039',github_path='experiment_results/published_figures/04_mr_matrix_mtr_gsrt.png',github_sha256=sha(github),layout_source=str(ROOT.parent/'experiment_mockups_20261008/build_mm2_variant.py'),layout_function='wide; current frozen spec removes three rejected protocol columns',not_same_as_historical_github_experiment=True)
    (a.out/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(dict(counts=counts,out=str(a.out)),ensure_ascii=False))


if __name__=='__main__':main()
