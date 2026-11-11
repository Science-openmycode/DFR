"""Read-only preflight for checked-in README steps 9--11; no research run."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from preprocess.dataset_config import load_config
from preprocess.dataset_contract import validate_dataset
from preprocess.dpmm_city import projection
from tools.prepare_experiment_configs import DOCS


def check(config, config_root, root=ROOT):
    root = Path(root).resolve()
    base = load_config(config, root)
    identity = validate_dataset(root/base['paths']['prepared'], root/base['paths']['network'])
    if identity['dataset_id'] != base['frozen_dataset_id']:
        raise ValueError('Prepared population mismatch')
    from algorithms.measurements.frozen_adapter import verify_sources
    baseline_source_manifest_sha256 = verify_sources()
    required = ['prepared', 'network', 'metric_cache', 'edge_cache', 'real', 'real_routes',
                'train', 'test', 'split_audit', 'osm', 'ubodt', 'fmm', 'stmatch', 'mm2', 'mm2_network']
    for key in required:
        if not (root/base['paths'][key]).exists():
            raise FileNotFoundError(key+': '+base['paths'][key])
    bound = load_config(Path(config_root)/'configs/beijing.json', root)
    if bound['slots'] != identity['count'] or bound['train_slots'] != identity['train_count']:
        raise ValueError('Prepared experiment slots differ')
    zone, band = projection(bound)
    if not bound['paths'].get('time_endpoints') and not all(bound['paths'].get(k) for k in ['mtnet_time_binding', 'mtnet_raw_reference']):
        raise ValueError('MTNet time source missing')
    for key in ['time_endpoints', 'mtnet_time_binding', 'mtnet_raw_reference']:
        if key in bound['paths'] and not (root/bound['paths'][key]).is_file():
            raise FileNotFoundError(bound['paths'][key])
    document_checks = []
    for doc in DOCS[:4]:
        source = root/doc
        text = source.read_text(encoding='utf-8-sig')
        commands = [line for line in text.splitlines() if line.startswith(('.venv/Scripts/python.exe ', 'powershell -NoProfile -File '))]
        for command in commands:
            for path in re.findall(r'--config (configs/experiments/[\w./-]+\.json)', command):
                c = load_config(root/path, root)
                if (c['frozen_dataset_id'], c['dataset'], c['slots']) != (base['frozen_dataset_id'], base['dataset'], identity['count']):
                    raise ValueError('Document references another population: '+path)
                for key in ['network', 'prepared', 'metric_cache', 'osm']:
                    if (root/c['paths'][key]).resolve() != (root/base['paths'][key]).resolve():
                        raise ValueError('Resource drift: '+key)
            script = command.split()[1] if command.startswith('.venv/') else command.split()[3]
            if not (root/script).is_file():
                raise FileNotFoundError(script)
        document_checks.append(dict(path=doc, commands=len(commands), sha256=hashlib.sha256(source.read_bytes()).hexdigest()))
    native = (root/DOCS[2]).read_text(encoding='utf-8')
    scores = (root/DOCS[3]).read_text(encoding='utf-8')
    assert 'vendor/dpmm/evidence/' not in native
    assert '--time-binding resources/' not in native
    assert '--expected-slots 15730' not in scores
    assert '--source-cache "$MetricCache"' in scores
    # This checks the links, not the existence of future generated releases.
    # Their successful exit/manifests remain required at actual execution time.
    for name in ('prepare_endpoint_controls.py','tools/endpoint_control_core.py',
                 'mtnet_dp_od.py','vendor/mtnet/dp_od_variant.py','tools/add_application_release.py',
                 'adatrace.py','dptraj_pm.py','evaluate_representative_regions.py',
                 'tools/collect_current_budget.py','plotting/render_mr.py',
                 'plotting/render_budget_comparison.py','reference_results/matrix/spec_current_methods.json'):
        if not (root/name).is_file():
            raise FileNotFoundError('Missing control generator: '+name)
    return dict(status='README_9_11_INPUT_AND_DOCUMENT_PREFLIGHT_PASSED', dataset=base['dataset'],
                full_slots=identity['count'], train_slots=identity['train_count'], test_slots=identity['test_count'],
                dpmm_utm_zone=zone, dpmm_utm_band=band, documents=document_checks,
                command_documents_generated=0, research_experiments_executed=0,
                baseline_source_manifest_sha256=baseline_source_manifest_sha256,
                scope='Actual prepared data/resources and static command/config handoff; not generated-release or score validation')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', type=Path, required=True)
    p.add_argument('--config-root', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    if a.out.exists():
        raise FileExistsError(a.out)
    started = time.perf_counter()
    result = check(a.config, a.config_root)
    result['seconds'] = time.perf_counter()-started
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
