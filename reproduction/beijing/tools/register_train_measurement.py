"""Copy an already generated train-only DP release to the router interface."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def register(source, lineage, out_dir):
    source, lineage, out_dir = map(Path, (source, lineage, out_dir))
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    record = json.loads(lineage.read_text(encoding='utf-8'))
    if record.get('status') != 'passed' or record.get('outputs', {}).get(source.name) != digest:
        raise ValueError('source is not the recorded successful train-only release')
    if record.get('input_policy') != 'train_only_explicit_generator_input':
        raise ValueError('missing train-only policy')
    out_dir.mkdir(parents=True, exist_ok=False)
    shutil.copy2(source, out_dir / 'measurement.pkl')
    manifest = {'kind': 'measurement', 'status': 'REGISTERED', 'generation': 'not rerun',
                'source': str(source.resolve()), 'source_sha256': digest,
                'train_sha256': record['train_sha256'], 'test_sha256': record['test_sha256'],
                'lineage': str(lineage.resolve()), 'lineage_sha256': hashlib.sha256(lineage.read_bytes()).hexdigest()}
    (out_dir / 'measurement_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'lineage', 'out-dir'):
        parser.add_argument('--' + name, type=Path, required=True)
    register(**vars(parser.parse_args()))
