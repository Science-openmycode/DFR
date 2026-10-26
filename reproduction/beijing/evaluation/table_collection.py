"""Collect observed cells without silently reconciling distinct experiments."""
import csv
import hashlib
import json
import math
from pathlib import Path

TSTR = {'NextCellHit1', 'NextCellMRR', 'DestinationHit5', 'DestinationMRR',
        'RoadContinuationHit1', 'RoadContinuationMRR', 'RouteRetrievalNDCG5'}


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def collect(spec, sources):
    observed, definitions, checked = {}, {}, {}
    for source in sources:
        if source['row'] not in spec['rows']:
            raise ValueError(f"unrecognized row: {source['row']}")
        for binding in [source, *source.get('bindings', [])]:
            path = binding['path']
            if path not in checked:
                checked[path] = sha256(path)
            if checked[path] != binding['sha256']:
                raise ValueError(f'hash mismatch: {path}')
        if source['format'] == 'json':
            values = json.loads(Path(source['path']).read_text(encoding='utf-8-sig'))
            statuses = values.get('metric_status', {})
            for key in source.get('key', '').split('.'):
                if key:
                    values = values[key]
        elif source['format'] == 'csv':
            statuses = {}
            with Path(source['path']).open(encoding='utf-8-sig', newline='') as stream:
                records = list(csv.DictReader(stream))
            select = source['select']
            records = [r for r in records if all(r.get(k) == v for k, v in select.items())]
            if len(records) != 1:
                raise ValueError(f"expected one selected record: {source['path']}: {select}")
            values = records[0]
        else:
            raise ValueError(f"unknown source format: {source['format']}")
        if source.get('status_manifest'):
            manifest_path = source['status_manifest']
            if manifest_path not in {b['path'] for b in source.get('bindings', [])}:
                raise ValueError('metric status manifest lacks a verified binding')
            declared = json.loads(Path(manifest_path).read_text(encoding='utf-8-sig')).get('metric_status', {})
            for metric, status in declared.items():
                if metric in statuses and statuses[metric] != status:
                    raise ValueError(f'conflicting metric status: {metric}')
            statuses = {**declared, **statuses}
        for original, metric in source['columns'].items():
            if metric not in spec['columns']:
                continue
            if original not in values:
                raise ValueError(f"missing declared metric {original}: {source['path']}")
            scope = 'tstr' if metric in TSTR else 'full'
            if source['scope'] != scope:
                raise ValueError(f"wrong scope for {metric}: {source['scope']}")
            definition = source['protocol']
            if metric in definitions and definitions[metric] != definition:
                raise ValueError(f'mixed protocol for {metric}')
            definitions[metric] = definition
            key = (source['row'], metric)
            if key in observed:
                raise ValueError(f'duplicate cell: {key}')
            if values[original] is None:
                declared = statuses.get(original, 'MISSING')
                declared = declared.get('status', 'MISSING') if isinstance(declared, dict) else declared
                if declared not in ('NA', 'MISSING', 'INVALID', 'POSITIVE_INFINITY_ZERO_ROAD_EVIDENCE'):
                    raise ValueError(f'null score has incompatible status: {key}: {declared}')
                observed[key] = dict(row=key[0], column=metric, metric=metric, value='', status=declared,
                                     scope=scope, protocol=definition, source=source['path'], source_sha256=source['sha256'])
                continue
            value = float(values[original])
            if not math.isfinite(value):
                raise ValueError(f'non-finite observed score: {key}')
            observed[key] = dict(row=key[0], column=metric, metric=metric, value=value,
                                 status='ZERO' if value == 0 else 'VALID', scope=scope,
                                 protocol=definition, source=source['path'], source_sha256=source['sha256'])
    return [observed.get((row, metric), dict(row=row, column=metric, metric=metric,
             value='', status='MISSING', scope='tstr' if metric in TSTR else 'full',
             protocol='', source='', source_sha256=''))
            for row in spec['rows'] for metric in spec['columns']]


def save(rows, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    with (directory / 'metrics_long.csv').open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (directory / 'metrics_long.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
    missing = [r for r in rows if r['status'] == 'MISSING']
    invalid = [r for r in rows if r['status'] == 'INVALID']
    summary = {'total': len(rows), 'observed': len(rows) - len(missing), 'missing': len(missing),
               'invalid': len(invalid), 'complete': not missing and not invalid,
               'missing_by_column': {}, 'missing_by_row': {}}
    for item in missing:
        for field in ('column', 'row'):
            dest = summary['missing_by_' + field]
            dest[item[field]] = dest.get(item[field], 0) + 1
    (directory / 'coverage.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    return summary
