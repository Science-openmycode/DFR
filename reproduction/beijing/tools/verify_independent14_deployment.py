"""Verify every deployed byte, original manifest lineage and path-only relocation."""
import argparse
import hashlib
import importlib
import json
from pathlib import Path
import platform
import time


def sha(p):
    with Path(p).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def strip_paths(obj):
    if isinstance(obj, dict):
        return {k: strip_paths(v) for k, v in obj.items() if k != 'path'}
    if isinstance(obj, list):
        return [strip_paths(v) for v in obj]
    return obj


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--binding', type=Path, required=True)
    p.add_argument('--binding-sha256', required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    if a.out.exists():
        raise FileExistsError(a.out)
    start = time.perf_counter()
    if sha(a.binding) != a.binding_sha256:
        raise ValueError('Binding changed')
    meta = json.loads(a.binding.read_text(encoding='utf-8'))
    root = Path(meta['remote_root']).resolve()
    if root != Path.cwd().resolve() or not str(root).lower().startswith('d:\\mtr\\'):
        raise ValueError('Wrong isolated server working directory')
    for item in meta['files']:
        f = root / item['path']
        if not f.resolve().is_relative_to(root) or sha(f) != item['sha256']:
            raise ValueError('Deployed file mismatch: ' + str(f))
    for group in meta['groups']:
        original = json.loads((root / group['original']).read_text(encoding='utf-8'))
        relocated = json.loads((root / group['manifest']).read_text(encoding='utf-8'))
        if sha(root / group['original']) != group['original_sha256'] or sha(root / group['manifest']) != group['relocated_sha256']:
            raise ValueError('Manifest lineage changed')
        if strip_paths(original) != strip_paths(relocated):
            raise ValueError('Non-path content changed')
        for path in group['paths']:
            f = Path(path['relocated'])
            if not f.resolve().is_relative_to(root) or sha(f) != path['sha256']:
                raise ValueError('Path binding mismatch')
    dependencies = {}
    for name in ('psutil', 'numpy', 'pandas', 'geopandas', 'shapely', 'networkx', 'pyogrio'):
        module = importlib.import_module(name)
        dependencies[name] = getattr(module, '__version__', 'unknown')
    report = dict(passed=True, groups=len(meta['groups']), files=len(meta['files']),
                  binding_sha256=sha(a.binding), dependencies=dependencies, python=platform.python_version(),
                  seconds=time.perf_counter()-start, policy=meta['policy'])
    a.out.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
