import json
from pathlib import Path
import pytest
from evaluation.applications.framework import prepare_cells
from evaluation.applications.visualization import METRICS
from tools.collect_frozen_matrix import collect_verified_cells,apply_framework_policy,sha,merge_collections,collect

ROOT=Path(__file__).resolve().parents[1]


def archive(tmp_path):
    metric=tmp_path/'metric.json';metric.write_text(json.dumps({'metrics':{'trip_error':.2}}))
    cells=tmp_path/'cells.json'
    cells.write_text(json.dumps([dict(row='MTR-DFR',metric='Trip',value=.2,status='VALID',source=str(metric),sha256=sha(metric))]))
    binding=tmp_path/'binding.json'
    binding.write_text(json.dumps(dict(dataset_id='same',slots=10,cells_sha256=sha(cells))))
    return cells,binding,metric


def test_explicit_archive_reads_original_score_and_rejects_wrong_population(tmp_path):
    cells,binding,metric=archive(tmp_path);spec=dict(rows=['MTR-DFR'],columns=['Trip'])
    assert collect_verified_cells(cells,binding,spec,dict(dataset_id='same',count=10))[0]['value']==.2
    with pytest.raises(ValueError,match='population'):
        collect_verified_cells(cells,binding,spec,dict(dataset_id='another',count=10))
    with pytest.raises(ValueError,match='population'):
        collect_verified_cells(cells,binding,spec,dict(dataset_id='same',count=9))
    metric.write_text('{}')
    with pytest.raises(ValueError,match='changed'):collect_verified_cells(cells,binding,spec,dict(dataset_id='same',count=10))


def test_archive_cannot_forge_number_even_with_new_archive_hash(tmp_path):
    cells,binding,metric=archive(tmp_path);obj=json.loads(cells.read_text());obj[0]['value']=.01
    cells.write_text(json.dumps(obj));b=json.loads(binding.read_text());b['cells_sha256']=sha(cells);binding.write_text(json.dumps(b))
    with pytest.raises(ValueError,match='parsed original'):
        collect_verified_cells(cells,binding,dict(rows=['MTR-DFR'],columns=['Trip']),dict(dataset_id='same',count=10))


def test_framework_refuses_missing_and_keeps_exclusions():
    spec=dict(view='application_framework',columns=['Trip',METRICS[0]])
    cells=[dict(row='MTR-DFR',metric=k,value=None,status='MISSING') for k in spec['columns']]
    with pytest.raises(ValueError,match='Missing applicable'):prepare_cells(cells,spec)
    policy=apply_framework_policy([dict(row='DPMM',column=METRICS[0],value=None,status='MISSING')],spec)
    assert policy[0]['status']=='EXCLUDED'
    policy=apply_framework_policy([dict(row='SPRT + Origin',column=METRICS[0],value=None,status='MISSING')],spec)
    assert policy[0]['status']=='NOT_APPLICABLE'


def test_framework_spec_is_exactly_retained_eleven_metrics():
    spec=json.loads((ROOT/'reference_results/matrix/spec_framework.json').read_text(encoding='utf-8'))
    assert spec['columns']==['Grid','Trip','Len','RoadYield','BTF','FamilyCPC','ODPF384']+METRICS
    assert 'Real-train [TSTR reference]' not in spec['rows']
    assert spec['missing_policy']=='error-for-applicable'


def test_readme_all_three_copies_call_the_formal_final_renderer():
    repo=ROOT.parents[1]
    files=[repo/'README.md',repo/'README_CN.md',repo/'分节命令/第09节_完整矩阵与图件.md']
    command='.venv/Scripts/python.exe plotting/render_verified_matrix.py --sources $MatrixSources --previous reference_results/applications/figures --spec reference_results/matrix/spec_framework.json --new-batch --out $MatrixFigures'
    for f in files:
        text=f.read_text(encoding='utf-8')
        assert command in text and '@ScoreInputs' in text
        assert '1215格是27×45' not in text
    assert 'check/downstream_' not in (ROOT/'evaluation/applications/framework.py').read_text()


def test_conflicting_existing_and_new_scores_are_rejected():
    a=dict(row='MTR-DFR',column='Trip',value=.2,status='VALID',result='a')
    b=dict(a,value=.1,result='b')
    with pytest.raises(ValueError,match='Conflicting'):merge_collections([[a],[b]])


def test_equal_counts_do_not_allow_another_coordinate_dataset(tmp_path):
    folder=tmp_path/'coordinate_scores_audit_v2/SPRT/FMM';folder.mkdir(parents=True)
    metric=folder/'metrics.json';metric.write_text(json.dumps(dict(metrics=dict(trip_error=.2))))
    manifest=dict(method='SPRT',router='FMM',metric_revision=dict(protocol='metric-audit-v2-20261016'),
                  inputs=dict(real=dict(count=10,sha256='other-city')),outputs={'metrics.json':sha(metric)})
    (folder/'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match='different real data'):
        collect(tmp_path,dict(rows=['SPRT + FMM'],columns=['Trip']),dict(count=10,real_coordinate_sha256='selected-city'))


def test_geometry_self_reference_uses_bound_road_view_not_raw_gps(tmp_path):
    folder=tmp_path/'coordinate_scores_audit_v2/Real/Origin';folder.mkdir(parents=True)
    metric=folder/'metrics.json';metric.write_text(json.dumps(dict(metrics=dict(trip_error=0))))
    manifest=dict(metric_revision=dict(protocol='metric-audit-v2-20261016'),
                  inputs=dict(real=dict(count=10,sha256='geometry'),synthetic=dict(sha256='geometry'),road_routes=dict(sha256='roads')),
                  outputs={'metrics.json':sha(metric)})
    meta=folder/'manifest.json';meta.write_text(json.dumps(manifest))
    spec=dict(rows=['Real-vs-real [geometry reference]'],columns=['Trip'])
    population=dict(count=10,real_sha256='roads',real_coordinate_sha256='raw-gps')
    rows=collect(tmp_path,spec,population,row_override='Real-vs-real [geometry reference]')
    assert rows[0]['value']==0
    manifest['inputs']['road_routes']['sha256']='other-city';meta.write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match='Geometry reference'):collect(tmp_path,spec,population,row_override='Real-vs-real [geometry reference]')
