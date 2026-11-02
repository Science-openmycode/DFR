"""Explicit current-batch result-source matrix; no inference, plotting or scoring."""
import argparse
from collections import Counter
import csv
import hashlib
import json
import math
import time
from pathlib import Path

NATIVE = {'DPMM', 'MTNet', 'MTNet_DP_OD_coarse24', 'MTR-DFR'}
COORD = {'grid_density_jsd':'Grid', 'trip_error':'Trip', 'path_length_jsd':'Len',
         'directed_road_validity':'DirValid', 'witness_valid':'WitnessValid'}
APPLICATIONS = ('MFPOrderedRouteOverlap', 'RepresentativeRealCoverage',
                'SelectedRoadMarginalOverlap', 'IncomingExitDistributionOverlap')


def collect_applications(summary, spec, population=None):
    """Collect actual applications without renaming predictive TSTR metrics."""
    meta = json.loads((summary/'manifest.json').read_text(encoding='utf-8-sig'))
    if meta.get('scope') != 'retrospective_four_road_applications' or meta.get('status') != 'COMPLETE':
        raise ValueError('Wrong application protocol or unfinished summary')
    if population and meta['slots'] != population['count']:raise ValueError('Wrong application population')
    if population and population.get('dataset_id') and meta['dataset_id'] != population['dataset_id']:
        raise ValueError('Different application dataset')
    result=summary/'results.csv'
    if sha(result) != meta['table_sha256']:raise ValueError('Changed application results')
    with result.open(encoding='utf-8-sig',newline='') as f:records=list(csv.DictReader(f))
    if len(records)!=meta['methods'] or len({r['method'] for r in records})!=len(records):
        raise ValueError('Incomplete application methods')
    cells=[]
    for r in records:
        row='Real [application reference]' if r['method']=='Real' else r['method'].replace('__',' + ')
        if row not in spec['rows']:continue
        for metric in APPLICATIONS:
            if metric not in spec['columns']:continue
            v=float(r[metric])
            if not math.isfinite(v) or not -1e-12<=v<=1+1e-12:raise ValueError('Invalid application score')
            cells.append(dict(row=row,column=metric,value=v,status='ZERO' if v==0 else 'VALID',family='applications',
                manifest=str((summary/'manifest.json').resolve()),manifest_sha256=sha(summary/'manifest.json'),
                result=str(result.resolve()),result_sha256=sha(result),source_metric=metric,
                scope='full-release real-question application; direct overlap/coverage; not TSTR'))
    return cells


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def row_label(method, router):
    aliases={'SameEndpointRandom':'Same-endpoint random [control]',
             'EndpointShortest':'Public shortest path [control]'}
    if method in aliases:return aliases[method]
    return method if method in NATIVE else method + ' + ' + router


def collect_verified_cells(file, binding_file, spec, population):
    """Explicit same-population reuse; recheck original result files and parsed values."""
    binding=json.loads(binding_file.read_text(encoding='utf-8-sig'))
    if not population or not population.get('dataset_id'):
        raise ValueError('Verified reuse requires explicit dataset configuration')
    if (binding['dataset_id'],binding['slots'])!=(population['dataset_id'],population['count']):
        raise ValueError('Verified cells belong to a different population')
    if sha(file)!=binding['cells_sha256']:raise ValueError('Verified cell archive changed')
    records=json.loads(file.read_text(encoding='utf-8-sig'));result=[]
    inverse={v:k for k,v in COORD.items()};seen=set()
    for c in records:
        row,col=c['row'],c['metric']
        if row not in spec['rows'] or col not in spec['columns']:continue
        if col in APPLICATIONS:continue  # Applications must come from the current explicit summary.
        if (row,col) in seen:raise ValueError('Duplicate archived cell')
        seen.add((row,col))
        source=c.get('source','')
        if not source:
            if c['value'] is not None:raise ValueError('Numeric archived cell has no source')
            continue
        path=Path(source)
        if not path.is_absolute():path=(file.parent/path).resolve()
        if sha(path)!=c['sha256']:raise ValueError('Archived metric source changed: '+str(path))
        if path.suffix!='.json':raise ValueError('Verified compact cells require original metric JSON')
        obj=json.loads(path.read_text(encoding='utf-8-sig'));values=obj.get('metrics',obj)
        key=inverse.get(col,col)
        if key not in values:raise ValueError('Archived metric missing in original source: '+key)
        actual=values[key];saved=c['value']
        if not (actual==saved or (actual is not None and saved is not None and math.isclose(actual,saved,abs_tol=1e-12,rel_tol=1e-12))):
            raise ValueError('Archived score differs from parsed original: '+repr((row,col)))
        result.append(dict(row=row,column=col,value=saved,status=c['status'],family='explicit_verified_reuse',
            manifest=str(binding_file.resolve()),manifest_sha256=sha(binding_file),result=str(path.resolve()),
            result_sha256=sha(path),source_metric=key,scope='explicit same-dataset reuse; original metric re-parsed'))
    return result


def apply_framework_policy(rows,spec):
    """Mark genuine inapplicability; never turn an absent eligible result into zero."""
    if spec.get('view')!='application_framework':return rows
    optional=set(spec.get('optional_rows',[]))
    absent={m for m in optional if not any(c['row']==m and c['value'] is not None for c in rows)}
    result=[]
    for r in rows:
        if r['row'] in absent:continue
        if r['status']=='MISSING':
            m,k=r['row'],r['column']
            if k in APPLICATIONS and m=='DPMM':r=dict(r,status='EXCLUDED',scope='excluded by explicit user comparison scope')
            elif ((m.endswith(' + Origin') and k not in ('Grid','Trip','Len')) or
                  (m=='Real-vs-real [geometry reference]' and k in APPLICATIONS) or
                  (m=='Real [application reference]' and k not in APPLICATIONS)):
                r=dict(r,status='NOT_APPLICABLE')
        result.append(r)
    return result


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


def collect(batch, spec, population=None, exclusions=None, row_override=None):
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
                'remote_scores_1314', 'reference/Real-vs-real/road_scores',
                'reference/Real-vs-real/physical', 'reference/Real-vs-real/road_tasks']
    for family in families:
        root = batch / family
        direct=root/'manifest.json'
        manifests = [direct] if family.startswith('reference/') else ([direct] if direct.is_file() else [])+sorted(root.glob('*/*/manifest.json'))
        for manifest in manifests:
            if not manifest.is_file():
                continue
            meta = json.loads(manifest.read_text(encoding='utf-8-sig'))
            if family == 'coordinate_scores' and 'metric_revision' not in meta:
                # This legacy directory can coexist with separately audited
                # coordinates. Never mix its older metric definitions in v2.
                if exclusions is not None:
                    exclusions.append(dict(manifest=str(manifest),reason='legacy coordinate protocol; no audit-v2 revision'))
                continue
            reference = family.startswith('reference/') or bool(row_override and row_override.startswith('Real'))
            row = (('Real-vs-real [geometry reference]' if 'Real-vs-real [geometry reference]' in spec['rows'] else 'Real-vs-real [reference]') if reference else
                   row_label(meta.get('method',manifest.parent.parent.name), meta.get('router',manifest.parent.name)))
            if row_override and not reference:row=row_override
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
                if population.get('real_coordinate_sha256'):
                    if reference:
                        inputs=meta['inputs']
                        if (inputs['real'].get('sha256')!=inputs.get('synthetic',{}).get('sha256') or
                                inputs.get('road_routes',{}).get('sha256')!=population['real_sha256']):
                            raise ValueError('Geometry reference must compare the selected real-road view with itself')
                    elif meta['inputs']['real'].get('sha256')!=population['real_coordinate_sha256']:
                        raise ValueError('Coordinate scores use different real data')
                result = manifest.parent / 'metrics.json'
                if sha(result) != meta['outputs']['metrics.json']:
                    raise ValueError('Coordinate output SHA mismatch')
                values = json.loads(result.read_text())['metrics']
                for source, col in COORD.items():
                    if source in values:
                        add(row,col,values[source],family,manifest,result,source,meta['outputs']['metrics.json'],scope)
    return [cells.get((r,c),dict(row=r,column=c,value=None,status='MISSING',family='',
                manifest='',manifest_sha256='',result='',result_sha256='',source_metric='',
                scope='not computed or not an applicable/approved formal result'))
            for r in spec['rows'] for c in spec['columns']]


def main():
    started=time.perf_counter()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--batch',type=Path,default=[],action='append',help='Repeat for independent result roots; no implicit old-score fallback')
    p.add_argument('--spec',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--config',type=Path,help='New batch population configuration; uses its actual counts and real reference, without historical input digests')
    p.add_argument('--applications',type=Path,help='Completed four-application summary, separate from TSTR')
    p.add_argument('--verified-cells',type=Path,help='Explicit previously verified same-dataset metric archive; never auto-selected')
    p.add_argument('--verified-binding',type=Path,help='Dataset/count/hash binding for --verified-cells')
    p.add_argument('--labeled-batch',action='append',default=[],help='Explicit DISPLAY_ROW=RESULT_ROOT for an independently evaluated variant/control')
    a = p.parse_args()
    if bool(a.verified_cells)!=bool(a.verified_binding):p.error('verified-cells and verified-binding must be paired')
    if not a.batch and not a.labeled_batch and not a.verified_cells:p.error('Provide result batches or an explicit verified archive')
    if a.out.exists():
        raise FileExistsError(a.out)
    a.out.mkdir(parents=True)
    try:
        spec = json.loads(a.spec.read_text(encoding='utf-8'))
        population=None
        if a.config:
            root=Path(__file__).resolve().parents[1]
            config=json.loads(a.config.read_text(encoding='utf-8'))
            population=dict(count=config['slots'],train_count=config['train_slots'],test_count=config['test_slots'],dataset_id=config.get('frozen_dataset_id'),
                real_sha256=sha((root/config['paths']['real_routes']).resolve()))
            if config['paths'].get('real'):
                population['real_coordinate_sha256']=sha((root/config['paths']['real']).resolve())
            elif spec.get('view')=='application_framework':
                raise ValueError('Framework configuration requires paths.real for coordinate population validation')
        exclusions=[]
        groups=[collect(batch,spec,population,exclusions) for batch in a.batch]
        for value in a.labeled_batch:
            label,path=value.split('=',1)
            if label not in spec['rows']:raise ValueError('Unknown explicitly labeled result row: '+label)
            groups.append(collect(Path(path),spec,population,exclusions,row_override=label))
        if a.verified_cells:groups.append(collect_verified_cells(a.verified_cells,a.verified_binding,spec,population))
        if a.applications:
            groups.append(collect_applications(a.applications,spec,population or {'count':15730,
                'dataset_id':'afeddd66f0c6d5281dad5980bd56a8b62ffbd87ed53cd92493761a516ff1af35'}))
        rows = merge_collections(groups)
        by={(r['row'],r['column']):r for r in rows}
        rows=[by.get((r,c),dict(row=r,column=c,value=None,status='MISSING',family='',manifest='',
              manifest_sha256='',result='',result_sha256='',source_metric='',scope='not computed'))
              for r in spec['rows'] for c in spec['columns']]
        rows=apply_framework_policy(rows,spec)
        with (a.out/'matrix_sources.csv').open('w',encoding='utf-8-sig',newline='') as f:
            writer = csv.DictWriter(f,fieldnames=list(rows[0]))
            writer.writeheader();writer.writerows(rows)
        report = dict(shape=[len(spec['rows']),len(spec['columns'])],
                      elapsed_seconds=time.perf_counter()-started,
                      population=population,application_summary=str(a.applications.resolve()) if a.applications else None,
                      explicit_verified_reuse=str(a.verified_cells.resolve()) if a.verified_cells else None,
                      excluded_legacy_records=exclusions,
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
