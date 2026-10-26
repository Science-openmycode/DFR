"""Build one hash-bound read-only audit deployment; never run a scorer."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import tarfile


def sha(p):
    with Path(p).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def without_paths(obj):
    if isinstance(obj, dict):
        return {k: without_paths(v) for k, v in obj.items() if k != 'path'}
    if isinstance(obj, list):
        return [without_paths(v) for v in obj]
    return obj


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--batch', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--remote-root', required=True)
    a = p.parse_args()
    if a.out.exists() or a.out.with_suffix('.tar').exists():
        raise FileExistsError(a.out)
    a.out.mkdir(parents=True)
    files, groups = {}, []

    def save(src, rel, expected=None):
        src, rel = Path(src), str(rel).replace('\\', '/')
        digest = sha(src)
        if expected and digest != expected:
            raise ValueError('Source hash mismatch: ' + str(src))
        target = a.out / rel
        if target.exists():
            if sha(target) != digest:
                raise ValueError('Deployment collision: ' + rel)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target)
        files[rel] = dict(path=rel, sha256=digest, bytes=target.stat().st_size)
        return rel

    selected = sorted(a.batch.glob('scores/*/*/manifest.json'))
    selected = [s for s in selected if s.parent.name != 'MM2-MDP']
    if len(selected) != 14:
        raise ValueError('Expected exactly fourteen unaudited main groups')
    for source in selected:
        original = json.loads(source.read_text(encoding='utf-8'))
        m, r = original['method'], original['router']
        if original['representation'] != 'edge-records':
            raise ValueError('Unsupported representation')
        if original['real']['slots'] != 15730 or original['synthetic']['slots'] != 15730:
            raise ValueError('Wrong frozen population')
        if original['inputs']['real_routes']['sha256'] != '0a0b11c0fef09bf3267ffdeca9d9202bedb8bfd609cb7da5c381ed08dca4907c':
            raise ValueError('Wrong reference')
        original_rel = save(source, f'original/{m}/{r}/manifest.json')
        paths = []

        def relocate(value):
            if isinstance(value, dict):
                result = {k: relocate(v) for k, v in value.items()}
                if 'path' in value and 'sha256' in value:
                    src = Path(value['path'])
                    is_network = src.name.startswith('network.')
                    rel = ('inputs/network/' + src.name) if is_network else ('inputs/' + value['sha256'] + '/' + src.name)
                    save(src, rel, value['sha256'])
                    result['path'] = a.remote_root.rstrip('/') + '/' + rel
                    paths.append(dict(original=value['path'], relocated=result['path'], sha256=value['sha256']))
                return result
            if isinstance(value, list):
                return [relocate(v) for v in value]
            return copy.deepcopy(value)

        relocated = relocate(original)
        if without_paths(original) != without_paths(relocated):
            raise AssertionError('Non-path manifest content changed')
        rel = f'manifests/{m}/{r}.json'
        dest = a.out / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(relocated, indent=2, ensure_ascii=False), encoding='utf-8')
        files[rel] = dict(path=rel, sha256=sha(dest), bytes=dest.stat().st_size)
        groups.append(dict(method=m, router=r, original=original_rel, manifest=rel,
                           original_sha256=sha(source), relocated_sha256=sha(dest), paths=paths))
    project = Path(__file__).resolve().parents[1]
    for name in ('independent_road_arithmetic.py', 'independent_road_structure.py', 'check_documented_command.py', 'verify_independent14_deployment.py'):
        save(project / 'tools' / name, 'tools/' + name)
    skill = Path('C:/Users/ASUS/.agents/skills/scientific-agent-skills/skills/get-available-resources/scripts/detect_resources.py')
    save(skill, 'tools/detect_resources.py')
    binding = dict(schema='independent14-deployment-v1', remote_root=a.remote_root,
                   groups=groups, files=list(files.values()),
                   policy='Only manifest path fields relocated; original manifests retained; no rescore or algorithm change')
    (a.out / 'deployment_binding.json').write_text(json.dumps(binding, indent=2, ensure_ascii=False), encoding='utf-8')
    with tarfile.open(a.out.with_suffix('.tar'), 'w') as tar:
        for item in sorted(a.out.rglob('*')):
            if item.is_file():
                tar.add(item, arcname=str(item.relative_to(a.out)))
    print(json.dumps(dict(groups=len(groups), files=len(files), tar_bytes=a.out.with_suffix('.tar').stat().st_size,
                          binding_sha256=sha(a.out / 'deployment_binding.json'))))


if __name__ == '__main__':
    main()
