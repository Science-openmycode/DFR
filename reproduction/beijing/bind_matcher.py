"""Bind an explicitly compiled public matcher without changing experiment inputs."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', type=Path, required=True)
    p.add_argument('--fmm', type=Path, required=True)
    p.add_argument('--stmatch', type=Path, required=True)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--original-source', type=Path, required=True)
    p.add_argument('--out-config', type=Path, required=True)
    p.add_argument('--threads', type=int, default=4)
    a = p.parse_args()
    if a.out_config.exists() or a.threads < 1:
        p.error('require a new configuration path and positive threads')
    if not a.fmm.is_file() or not a.stmatch.is_file():
        p.error('compile the matcher first')
    changed = []
    checked = 0
    for folder in ('src', 'third_party', 'cmake'):
        for old in sorted((a.original_source / folder).rglob('*')):
            if old.is_file():
                relative = old.relative_to(a.original_source)
                new = a.source / relative
                if not new.is_file():
                    raise ValueError(f'Missing source file: {relative}')
                checked += 1
                if digest(old) != digest(new):
                    changed.append(relative.as_posix())
    if changed != ['src/io/mm_writer.cpp', 'src/util/util.cpp']:
        raise ValueError(f'Unexpected source changes: {changed}')
    c = json.loads(a.config.read_text(encoding='utf-8'))
    c['matcher_compatibility'] = {
        'change': 'Windows stat -> _stat64; result writer uses input trajectory ID even for empty matches',
        'checked_files': checked, 'changed_files': changed,
        'original_source': str(a.original_source.resolve()),
        'source': str(a.source.resolve()), 'fmm_sha256': digest(a.fmm),
        'stmatch_sha256': digest(a.stmatch),
        'input_config': str(a.config.resolve()), 'input_config_sha256': digest(a.config),
    }
    c['paths']['fmm'] = str(a.fmm.resolve())
    c['paths']['stmatch'] = str(a.stmatch.resolve())
    c['threads'] = a.threads
    a.out_config.write_text(json.dumps(c, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(c['matcher_compatibility'], indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
