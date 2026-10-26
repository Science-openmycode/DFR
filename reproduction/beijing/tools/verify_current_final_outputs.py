"""Read-only final output integrity inventory; never synthesize, route or rescore."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import time


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def verify_outputs(manifest):
    meta = json.loads(manifest.read_text(encoding='utf-8'))
    checks = []
    def check(name, expected):
        path = manifest.parent / name
        if not path.is_file():
            raise ValueError('Missing final output: ' + str(path))
        actual = digest(path)
        if actual != expected:
            raise ValueError('Final output hash differs: ' + str(path))
        checks.append({'path': str(path), 'sha256': actual})
    for key, binding in meta.get('outputs', {}).items():
        if isinstance(binding, str):
            check(key, binding)
        elif isinstance(binding, dict) and binding.get('path') and binding.get('sha256'):
            check(binding['path'].replace('\\', '/').rsplit('/', 1)[-1], binding['sha256'])
        else:
            raise ValueError('Unrecognized output binding: ' + key)
    if 'result_sha256' in meta:
        check('metrics.json', meta['result_sha256'])
    if 'results_sha256' in meta:
        check('results.csv', meta['results_sha256'])
    if 'metric_revision' in meta:
        revision = meta['metric_revision']
        check('metric_revision.json', revision['manifest_sha256'])
        if revision['protocol'] != 'metric-audit-v2-20261016':
            raise ValueError('Unexpected revised metric protocol')
    if not checks:
        raise ValueError('No recognized final-output hash binding')
    return checks


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--batch', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    if a.out.exists():
        raise FileExistsError(a.out)
    started = time.perf_counter()
    families = ('coordinate_scores_audit_v2', 'remote_scores_1314', 'tstr_audit_v2', 'scores',
                'physical_scores', 'road_tasks', 'ablation/MTR-DFR/direct_scores',
                'ablation/MTR-DFR/physical', 'ablation/MTR-DFR/road_tasks',
                'ablation/MTR-DFR/coordinate_scores_audit_v2',
                'representation_diagnostics/DPMM')
    records = []
    for family in families:
        for manifest in sorted((a.batch / family).rglob('manifest.json')):
            # Audit only terminal per-cell manifests, not ancillary nested model data.
            depth = len(manifest.relative_to(a.batch / family).parts)
            if depth != (2 if family.startswith('ablation/') else 3):
                if not (family == 'representation_diagnostics/DPMM' and depth == 2):
                    continue
            row = {'family': family, 'manifest': str(manifest),
                   'manifest_sha256': digest(manifest)}
            try:
                row['checks'] = verify_outputs(manifest)
                row['status'] = 'FINAL_OUTPUT_HASHES_VERIFIED'
            except (OSError, ValueError, KeyError) as error:
                row.update(status='FAILED', error=str(error))
            records.append(row)
    counts = Counter((r['family'], r['status']) for r in records)
    summary = {f: {s: counts[f, s] for s in ('FINAL_OUTPUT_HASHES_VERIFIED', 'FAILED')}
               for f in families}
    coordinate_cells = {}
    for row in records:
        if row['family'] not in ('coordinate_scores_audit_v2', 'remote_scores_1314'):
            continue
        manifest = Path(row['manifest'])
        key = manifest.parent.parent.name + '/' + manifest.parent.name
        result = manifest.parent / 'metrics.json'
        if result.is_file():
            values = json.loads(result.read_text(encoding='utf-8'))
            if key in coordinate_cells and coordinate_cells[key] != values:
                raise ValueError('Duplicate coordinate cell differs: ' + key)
            coordinate_cells[key] = values
    report = {'summary': summary, 'records': records,
              'unique_coordinate_cells': len(coordinate_cells),
              'duplicate_coordinate_comparison': 'parsed metrics compared, not byte hashes alone',
              'tool_sha256': digest(Path(__file__)),
              'seconds': time.perf_counter() - started,
              'limitation': 'Final output hashes only. Not full remote input/source provenance, independent metric arithmetic, DP proof, or experiment completion. Families overlap; do not sum as independent experiments. DPMM representation diagnostics are not approved formal table scores.'}
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary))
    if any(r['status'] == 'FAILED' for r in records):
        raise ValueError('Final output integrity failures; preserve report and investigate')


if __name__ == '__main__':
    main()
