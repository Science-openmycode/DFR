"""Explicit current-batch result-source matrix; no inference, plotting or scoring."""
import argparse
from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path

NATIVE = {'DPMM', 'MTNet', 'MTR-DFR'}
COORD = {'grid_density_jsd':'Grid', 'trip_error':'Trip', 'path_length_jsd':'Len',
         'directed_road_validity':'DirValid', 'witness_valid':'WitnessValid'}
TASKS = {'Next-cell Hit@1':'NextCellHit1', 'Next-cell MRR':'NextCellMRR',
         'Destination Hit@5':'DestinationHit5', 'Destination MRR':'DestinationMRR',
         'Road continuation Hit@1':'RoadContinuationHit1', 'Road continuation MRR':'RoadContinuationMRR',
         'Route retrieval NDCG@5':'RouteRetrievalNDCG5'}


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def row_label(method, router):
    return method if method in NATIVE else method + ' + ' + router


def metric_status(value, metric, manifest, result):
    declared = {}
    for source in (manifest, result):
        if source.suffix != '.json':
            continue
        statuses = json.loads(source.read_text(encoding='utf-8-sig')).get('metric_status', {})
        for name, status in statuses.items():
            status = status.get('status', 'MISSING') if isinstance(status, dict) else status
            if name in declared and declared[name] != status:
                raise ValueError('Conflicting metric status: ' + name)
            declared[name] = status
    if value is None:
        status = declared.get(metric, 'MISSING')
        if status not in ('NA', 'MISSING', 'INVALID', 'POSITIVE_INFINITY_ZERO_ROAD_EVIDENCE'):
            raise ValueError('Null metric has incompatible status: ' + metric)
        return status
    if not math.isfinite(float(value)):
        raise ValueError('Non-finite metric: ' + metric)
    return 'ZERO' if value == 0 else 'VALID'


def collect(batch, spec, population=None):
    population=population or dict(count=15730,train_count=12584,test_count=3146,
        real_sha256='0a0b11c0fef09bf3267ffdeca9d9202bedb8bfd609cb7da5c381ed08dca4907c')
    cells = {}
    def add(row, col, value, family, manifest, result, source_metric, expected, scope):
        if row not in spec['rows'] or col not in spec['columns']:
            return
        if sha(result) != expected:
            raise ValueError('Output SHA mismatch: ' + str(result))
        status = metric_status(value, source_metric, manifest, result)
        key = row, col
        entry = dict(row=row, column=col, value=value, status=status, family=family,
                     manifest=str(manifest.resolve()), manifest_sha256=sha(manifest),
                     result=str(result.resolve()), result_sha256=expected,
                     source_metric=source_metric, scope=scope)
        if key in cells:
            if cells[key]['status'] != status:
                raise ValueError('Conflicting parsed cell status: ' + repr(key))
            old = cells[key]['value']
            if not (old == value or (old is not None and value is not None and math.isclose(old, value, abs_tol=1e-12, rel_tol=1e-12))):
                raise ValueError('Conflicting parsed cell: ' + repr(key))
            return
        cells[key] = entry

    families = ['scores', 'road_scores', 'physical_scores', 'physical', 'road_tasks', 'coordinate_scores_audit_v2', 'coordinate_scores',
                'remote_scores_1314', 'tstr_audit_v2', 'reference/Real-vs-real/road_scores',
                'reference/Real-vs-real/physical', 'reference/Real-vs-real/road_tasks']
    for family in families:
        root = batch / family
        direct=root/'manifest.json'
        manifests = [direct] if family.startswith('reference/') else ([direct] if direct.is_file() else [])+sorted(root.glob('*/*/manifest.json'))
        for manifest in manifests:
            if not manifest.is_file():
                continue
            meta = json.loads(manifest.read_text(encoding='utf-8-sig'))
            reference = family.startswith('reference/')
            row = (('Real-vs-real [geometry reference]' if 'Real-vs-real [geometry reference]' in spec['rows'] else 'Real-vs-real [reference]') if reference else
                   row_label(meta.get('method',manifest.parent.parent.name), meta.get('router',manifest.parent.name)))
            scope = 'non-DP self-reference' if reference else 'full-release utility'
            if family in ('scores', 'road_scores') or family.endswith('/road_scores'):
                if meta['inputs']['real_routes']['sha256'] != population['real_sha256']:
                    raise ValueError('Wrong road population')
                if meta['real']['reference_slots'] != population['count'] or meta['synthetic']['slots'] != population['count']:
                    raise ValueError('Wrong road denominator')
                result = manifest.parent / 'metrics.json'
                if sha(result) != meta['outputs']['metrics_json']['sha256']:
                    raise ValueError('Road output SHA mismatch')
                for name, value in json.loads(result.read_text()).items():
                    add(row,name,value,family,manifest,result,name,meta['outputs']['metrics_json']['sha256'],scope)
            elif family in ('physical_scores','physical') or family.endswith('/physical'):
                result = manifest.parent / 'results.csv'
                if sha(result) != meta['results_sha256']:
                    raise ValueError('Physical output SHA mismatch')
                with result.open(encoding='utf-8-sig',newline='') as f:
                    rows = list(csv.DictReader(f))
                if len(rows) != 1:
                    raise ValueError('Ambiguous physical results')
                for name, value in rows[0].items():
                    if name not in ('method','RoadYield','DemandFid'):
                        add(row,name,float(value),family,manifest,result,name,meta['results_sha256'],scope+'; independently sampled ordered-OD statistic')
            elif family == 'road_tasks' or family.endswith('/road_tasks'):
                if meta['real_slots'] != population['count'] or meta['synthetic_slots'] != population['count']:
                    raise ValueError('Wrong road-task denominator')
                result = manifest.parent / 'metrics.json'
                if sha(result) != meta['result_sha256']:
                    raise ValueError('Road-task output SHA mismatch')
                values = json.loads(result.read_text())['metrics']
                for name in ('RC-NDCG','NextRoadAcc','NextRoadNLL'):
                    add(row,name,values[name],family,manifest,result,name,meta['result_sha256'],'retrospective; not strict TSTR')
            elif family in ('coordinate_scores_audit_v2','coordinate_scores','remote_scores_1314'):
                if meta['metric_revision']['protocol'] != 'metric-audit-v2-20261016' or meta['inputs']['real']['count'] != population['count']:
                    raise ValueError('Wrong coordinate protocol/population')
                result = manifest.parent / 'metrics.json'
                if sha(result) != meta['outputs']['metrics.json']:
                    raise ValueError('Coordinate output SHA mismatch')
                values = json.loads(result.read_text())['metrics']
                for source, col in COORD.items():
                    if source in values:
                        add(row,col,values[source],family,manifest,result,source,meta['outputs']['metrics.json'],scope)
            else:
                if not meta['synthesis_lineage_verified'] or not meta['disjoint_split_verified']:
                    raise ValueError('Unverified TSTR lineage')
                split = meta['split_binding']['disjoint_split']
                if (split['train_count'],split['test_count']) != (population['train_count'],population['test_count']):
                    raise ValueError('Wrong strict TSTR split')
                result = manifest.parent / 'results.csv'
                if sha(result) != meta['results_sha256']:
                    raise ValueError('TSTR output SHA mismatch')
                with result.open(encoding='utf-8-sig',newline='') as f:
                    values = list(csv.DictReader(f))
                for item in values:
                    target = 'Real-train [TSTR reference]' if item['Pipeline'] == 'Real-train' else row
                    if item['Pipeline'] not in ('Real-train', row, manifest.parent.parent.name):
                        raise ValueError('Unexpected TSTR pipeline: '+item['Pipeline'])
                    for source,col in TASKS.items():
                        add(target,col,float(item[source]),family,manifest,result,source,meta['results_sha256'],'strict TSTR; Real-train-normalized product')
    return [cells.get((r,c),dict(row=r,column=c,value=None,status='MISSING',family='',
                manifest='',manifest_sha256='',result='',result_sha256='',source_metric='',
                scope='not computed or not an applicable/approved formal result'))
            for r in spec['rows'] for c in spec['columns']]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--batch',type=Path,required=True,action='append',help='Repeat for independent new result roots; no old scores are filled in')
    p.add_argument('--spec',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--config',type=Path,help='New batch population configuration; uses its actual counts and real reference, without historical input digests')
    a = p.parse_args()
    if a.out.exists():
        raise FileExistsError(a.out)
    a.out.mkdir(parents=True)
    try:
        spec = json.loads(a.spec.read_text(encoding='utf-8'))
        population=None
        if a.config:
            root=Path(__file__).resolve().parents[1]
            config=json.loads(a.config.read_text(encoding='utf-8'))
            population=dict(count=config['slots'],train_count=config['train_slots'],test_count=config['test_slots'],
                real_sha256=sha((root/config['paths']['real_routes']).resolve()))
        rows = merge_collections([collect(batch,spec,population) for batch in a.batch])
        with (a.out/'matrix_sources.csv').open('w',encoding='utf-8-sig',newline='') as f:
            writer = csv.DictWriter(f,fieldnames=list(rows[0]))
            writer.writeheader();writer.writerows(rows)
        report = dict(shape=[len(spec['rows']),len(spec['columns'])],
                      counts=dict(Counter(r['status'] for r in rows)),
                      spec_sha256=sha(a.spec),tool_sha256=sha(__file__),
                      outputs={'matrix_sources.csv':sha(a.out/'matrix_sources.csv')},
                      limitations=['Source-output hash collection, not full remote input re-audit or independent metric arithmetic',
                                   'No plots, old results or algorithm changes; DPMM representation diagnostics excluded',
                                   'NA/ZERO/MISSING distinct; no coordinate NextRegion -> NextRoad substitution',
                                   'Ordered self-reference has independent sampling bias; not an unbiased perfect-score bound'])
        (a.out/'manifest.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
        print(json.dumps(report))
    except Exception as error:
        (a.out/'failure.json').write_text(json.dumps({'error':str(error)},indent=2),encoding='utf-8')
        raise


def merge_collections(groups):
    """Combine independent stages, rejecting conflicting measurements."""
    merged={}
    for group in groups:
        for row in group:
            key=row['row'],row['column']
            old=merged.get(key)
            if old is None or (not old['result'] and row['result']):merged[key]=row;continue
            if not row['result']:continue
            if old['value']!=row['value'] or old['status']!=row['status']:
                raise ValueError('Conflicting batches for '+repr(key))
    return list(merged.values())


if __name__ == '__main__':
    main()
