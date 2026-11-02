import json
from collections import Counter
from pathlib import Path
import pytest
from evaluation.applications.core import author_greedy, ordered, solve, overlap
from evaluation.applications.metrics import digest
from evaluation.applications.visualization import load_summary, METRICS, combine, cell_label, cell_color, highlight_runs, organize_columns
from tools.collect_frozen_matrix import collect_applications, collect


def summary(tmp_path):
    root=tmp_path/'applications';root.mkdir()
    (root/'results.csv').write_text('method,'+','.join(METRICS)+'\nReal,1,.8,1,1\nMTR-DFR,0,.5,.5,.6\n',encoding='utf-8')
    meta=dict(status='COMPLETE',scope='retrospective_four_road_applications',methods=2,slots=10,dataset_id='fixture',
              table_sha256=digest(root/'results.csv'))
    (root/'manifest.json').write_text(json.dumps(meta));return root


def test_core_rules():
    e={'a':dict(u='s',v='x',length_m=1),'b':dict(u='x',v='d',length_m=1)}
    assert solve(Counter(a=2,b=2),'d',e)['s'][1]==('a','b')
    assert ordered(['a','b'],['b','a'],e)==.5
    assert overlap(Counter(a=1),Counter())==0
    r=[[0,0,1,0,0,1,0,1],[1,1,2,1,0,2,0,1],[2,2,3,2,0,3,0,1]]
    assert author_greedy(r,[8,7,16],1,2)==[[0,1]]
    assert author_greedy(r,[0,0,0],3,2)==[]


def test_tiny_values_are_not_labeled_zero():
    assert cell_label(.00002,'VALID')=='2e-05'
    assert cell_label(0,'ZERO')=='0'
    assert cell_label(None,'POSITIVE_INFINITY_ZERO_ROAD_EVIDENCE')=='∞'
    assert cell_color(1)==cell_color(1.0)
    assert sum(cell_color(1)[:3])<sum(cell_color(0)[:3])


def test_collection_zero_and_native_one_row(tmp_path):
    root=summary(tmp_path)
    spec=dict(rows=['MTR-DFR','Real [application reference]'],columns=METRICS)
    cells=collect_applications(root,spec,dict(count=10,dataset_id='fixture'))
    assert len(cells)==8
    assert next(c for c in cells if c['row']=='MTR-DFR' and c['column']==METRICS[0])['status']=='ZERO'


def test_wrong_city_rejected(tmp_path):
    with pytest.raises(ValueError,match='dataset'):
        collect_applications(summary(tmp_path),dict(rows=[],columns=[]),dict(count=10,dataset_id='other'))


def test_no_tstr_fallback(tmp_path):
    root=summary(tmp_path);m=json.loads((root/'manifest.json').read_text());m['scope']='strict_tstr'
    (root/'manifest.json').write_text(json.dumps(m))
    with pytest.raises(ValueError,match='TSTR'):load_summary(root)


def test_edited_scores_rejected(tmp_path):
    root=summary(tmp_path)
    with (root/'results.csv').open('a') as f:f.write('Extra,1,1,1,1\n')
    with pytest.raises(ValueError,match='changed'):load_summary(root)


def test_legacy_coordinate_record_is_excluded_not_mixed(tmp_path):
    old=tmp_path/'coordinate_scores/SPRT/Origin';old.mkdir(parents=True)
    (old/'manifest.json').write_text(json.dumps(dict(method='SPRT',router='Origin')))
    current=tmp_path/'coordinate_scores_audit_v2/SPRT/Origin';current.mkdir(parents=True)
    (current/'metrics.json').write_text(json.dumps(dict(metrics=dict(grid_density_jsd=.2))))
    meta=dict(method='SPRT',router='Origin',metric_revision=dict(protocol='metric-audit-v2-20261016'),
              inputs=dict(real=dict(count=10)),outputs={'metrics.json':digest(current/'metrics.json')})
    (current/'manifest.json').write_text(json.dumps(meta))
    excluded=[]
    cells=collect(tmp_path,dict(rows=['SPRT + Origin'],columns=['Grid']),dict(count=10),excluded)
    assert cells[0]['value']==.2 and len(excluded)==1


def test_base_matrix_preserved_and_missing_not_zero(tmp_path):
    root=summary(tmp_path);meta,rows=load_summary(root)
    cells=[dict(row='MTR-DFR',metric='BTF',value=.9,status='VALID'),
           dict(row='SPRT + Origin',metric='BTF',value=None,status='NA')]
    base=tmp_path/'cells.json';base.write_text(json.dumps(cells))
    binding=tmp_path/'binding.json';binding.write_text(json.dumps(dict(dataset_id='fixture',slots=10,cells_sha256=digest(base))))
    joined,methods,metrics,n=combine(meta,rows,base,binding)
    assert n==2 and all(c in joined for c in cells)
    c=next(c for c in joined if c['row']=='SPRT + Origin' and c['metric']==METRICS[0])
    assert c['value'] is None and c['status']=='NOT_APPLICABLE'


def test_tasks_replace_instead_of_append(tmp_path):
    root=summary(tmp_path);meta,rows=load_summary(root)
    original=[dict(row='MTR-DFR',metric=k,value=.2,status='VALID')
              for k in ['BTF','NextCellHit1','DestinationHit5','RoadContinuationHit1','RouteRetrievalNDCG5']]
    base=tmp_path/'cells.json';base.write_text(json.dumps(original))
    binding=tmp_path/'binding.json';binding.write_text(json.dumps(dict(dataset_id='fixture',slots=10,cells_sha256=digest(base))))
    joined,methods,metrics,n=combine(meta,rows,base,binding)
    assert methods==['MTR-DFR','Real [application reference]']
    assert metrics==['BTF']+METRICS and len(joined)==10 and n==1
    assert original[0] in joined
    assert not any(c['metric'].startswith('NextCell') for c in joined)


def test_missing_control_must_not_pass_complete_plot(tmp_path):
    root=summary(tmp_path);meta,rows=load_summary(root)
    base=tmp_path/'cells.json'
    base.write_text(json.dumps([dict(row='Public shortest path [control]',metric='BTF',value=.4,status='VALID')]))
    binding=tmp_path/'binding.json';binding.write_text(json.dumps(dict(dataset_id='fixture',slots=10,cells_sha256=digest(base))))
    with pytest.raises(ValueError,match='Missing application answers for controls'):
        combine(meta,rows,base,binding)


def test_real_application_reference_never_fills_geometry_reference(tmp_path):
    root=summary(tmp_path);meta,rows=load_summary(root)
    base=tmp_path/'cells.json'
    base.write_text(json.dumps([dict(row='Real-vs-real [geometry reference]',metric='BTF',value=1,status='VALID')]))
    binding=tmp_path/'binding.json';binding.write_text(json.dumps(dict(dataset_id='fixture',slots=10,cells_sha256=digest(base))))
    joined,methods,metrics,n=combine(meta,rows,base,binding)
    old=next(c for c in joined if c['row']=='Real-vs-real [geometry reference]' and c['metric']==METRICS[0])
    assert old['value'] is None and old['status']=='NOT_APPLICABLE'
    new=next(c for c in joined if c['row']=='Real [application reference]' and c['metric']==METRICS[0])
    assert new['value']==1


def test_highlight_ties_and_contiguous_runs():
    methods=['Baseline','MTR-DFR','Real [application reference]','Public shortest path [control]']
    metrics=['Grid','RoadYield','BTF','FamilyCPC','ODPF384']
    vals=[[.1,1,.4,.5,.8],[.2,1,.6,.7,.6],[0,1,1,1,1],[0,1,1,1,1]]
    cells=[dict(row=m,metric=k,value=vals[j][i],status='VALID') for j,m in enumerate(methods) for i,k in enumerate(metrics)]
    runs=highlight_runs(cells,methods,metrics)
    assert (1,1,3) in runs  # Yield tie + two following DFR best values: one box.
    assert (0,1,1) not in runs  # Do not additionally frame the tied baseline.
    assert (0,0,0) in runs and (0,4,4) in runs  # Never bridge a nonwinning row.
    assert all(j<2 for j,_,_ in runs)


def test_merged_real_reference_and_user_column_order():
    methods=['MTNet','MTR-DFR','Real-vs-real [geometry reference]',
             'Same-endpoint random [control]','Public shortest path [control]','MTNet_DP_OD_coarse24','Real [application reference]']
    metrics=['BTF',METRICS[0]]
    cells=[dict(row=m,metric=k,value=None,status='NOT_APPLICABLE') for m in methods for k in metrics]
    for c in cells:
        if c['row']=='Real-vs-real [geometry reference]' and c['metric']=='BTF':c.update(value=.9,status='VALID')
        if c['row']=='Real [application reference]' and c['metric']==METRICS[0]:c.update(value=1,status='VALID')
    result,order=organize_columns(cells,methods,metrics)
    assert order==['MTNet','MTNet_DP_OD_coarse24','Same-endpoint random [control]','Public shortest path [control]','MTR-DFR','Real']
    refs=[c for c in result if c['row']=='Real']
    assert [c['value'] for c in refs]==[.9,1]
    assert [c['reference_source'] for c in refs]==['Real-vs-real [geometry reference]','Real [application reference]']
    again,order2=organize_columns(result,order,metrics)
    assert again==result and order2==order
