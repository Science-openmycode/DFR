"""Run the preserved ordered-interface attack only on unchanged aligned slots."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error('Choose a fresh output directory')
    config = json.loads(args.config.read_text(encoding='utf-8'))
    script = ROOT/'evaluation/vendor/evaluate_ordered_interface_linkage.py'
    spec = importlib.util.spec_from_file_location('original_ordered_attack', script)
    original = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(original)
    train = (ROOT/config['paths']['train']).resolve()
    raw_real = original.load_payload(train, None)
    real = original.coordinate_paths(raw_real)
    if len(real) != len(raw_real):
        raise ValueError('Original attack would drop real slots; refuse to renumber')
    del real
    args.out.mkdir(parents=True)
    report = {'scope': 'CURRENT_TRAIN_RELEASE_ORDER_ATTACK_NOT_MEMBERSHIP_AUC',
              'script_sha256': sha(script), 'config_sha256': sha(args.config),
              'train_sha256': sha(train), 'rows': [], 'command': [sys.executable, *sys.argv]}
    start = time.perf_counter()
    for i, (name, item) in enumerate(config['tstr_releases'].items()):
        source = (ROOT/item['coordinates']).resolve()
        raw = original.load_payload(source, None)
        # Preserve original positional semantics. Never silently drop empty paths.
        import numpy as np
        usable = sum(np.asarray(x).ndim == 2 and np.asarray(x).shape[0] >= 2
                     and np.asarray(x).shape[1] >= 2 for x in raw)
        row = {'method': name, 'slots': len(raw), 'usable': usable,
               'source_sha256': sha(source)}
        if usable != len(raw) or len(raw) != len(raw_real):
            row.update(status='NA_SLOT_ALIGNMENT_NOT_SUPPORTED_BY_ORIGINAL_ATTACK',
                       origin_top1=None, fingerprint_top1=None)
        else:
            cell = args.out/f'cell_{i:02d}'
            cell.mkdir()
            cfg = cell/'config.json'
            cfg.write_text(json.dumps({'candidate_group_size': 50, 'landmarks': 8,
                'seed': 20260724 + i * 101, 'methods': [{'name': name,
                'real_path': str(train), 'real_representation': 'coordinates',
                'release_path': str(source), 'release_representation': 'coordinates'}]}, indent=2), encoding='utf-8')
            command = [sys.executable, '-X', 'utf8', str(script), '--config', str(cfg.resolve()),
                       '--out', str((cell/'results').resolve())]
            tick = time.perf_counter()
            print(f'[{i+1}/{len(config["tstr_releases"])}] {name}', flush=True)
            result = subprocess.run(command, cwd=ROOT)
            row.update(child_argv=command, exit_code=result.returncode,
                       seconds=time.perf_counter()-tick)
            if result.returncode:
                row['status'] = 'FAILED'
            else:
                row.update(json.loads((cell/'results.json').read_text())['rows'][0])
                row['status'] = 'VALID'
                row['result_sha256'] = sha(cell/'results.json')
        del raw
        report['rows'].append(row)
        report['elapsed_seconds'] = time.perf_counter()-start
        (args.out/'manifest.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print({s: sum(x['status']==s for x in report['rows']) for s in {x['status'] for x in report['rows']}})
    raise SystemExit(1 if any(x['status']=='FAILED' for x in report['rows']) else 0)


if __name__ == '__main__':
    main()
