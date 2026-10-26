"""Run the unchanged release-only attacks, explicitly marking empty releases NA."""
import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--legacy', type=Path, required=True)
    p.add_argument('--members', type=Path, required=True)
    p.add_argument('--nonmembers', type=Path, required=True)
    p.add_argument('--reference', type=Path, required=True)
    p.add_argument('--attack-manifest', type=Path, required=True)
    p.add_argument('--release', action='append', required=True)
    p.add_argument('--synthesis-lineage', action='append', required=True)
    p.add_argument('--bbox', nargs=4, required=True)
    p.add_argument('--seed', type=int, required=True)
    p.add_argument('--out-dir', type=Path, required=True)
    a = p.parse_args()
    if a.out_dir.exists():
        p.error('Choose a new output directory')
    sys.path.insert(0, str(a.legacy/'evaluation'))
    sys.path.insert(0, str(a.legacy/'evaluation/pipeline'))
    from experiment_contract import validate_attack_release
    from evaluate_population_linkage import load
    releases = [item.split('=', 1) for item in a.release]
    lineage = dict(item.split('=', 1) for item in a.synthesis_lineage)
    names = [name for name, _ in releases]
    if len(set(names)) != len(names) or set(lineage) != set(names):
        p.error('Each unique release requires its own lineage binding')
    verified = {name: validate_attack_release(a.attack_manifest, Path(lineage[name]), Path(source),
                a.members, a.nonmembers, a.reference) for name, source in releases}
    a.out_dir.mkdir(parents=True)
    rows, commands = [], []
    for index, (name, source) in enumerate(releases):
        try:
            load(Path(source))
            empty = False
        except ValueError as error:
            if not str(error).startswith('No coordinate trajectories found in '):
                raise
            empty = True
        if empty:
            rows.append({'method': name, 'Population-linkage AUC': None, 'GDA-MIA AUC': None,
                         'status': 'NA_NO_NONEMPTY_RELEASE_TRAJECTORY'})
            continue
        out = a.out_dir/f'cell_{index:02d}'
        command = [sys.executable, '-X', 'utf8', str(a.legacy/'evaluation/run_privacy_experiment.py'),
                   '--members', str(a.members), '--nonmembers', str(a.nonmembers),
                   '--reference', str(a.reference), '--attack-manifest', str(a.attack_manifest),
                   '--release', name+'='+source, '--synthesis-lineage', name+'='+lineage[name],
                   '--bbox', *a.bbox, '--seed', str(a.seed), '--out-dir', str(out)]
        print(f'ATTACK {index+1}/{len(releases)} {name}', flush=True)
        subprocess.run(command, check=True)
        commands.append(command)
        with (out/'results.csv').open(encoding='utf-8-sig', newline='') as f:
            row = next(csv.DictReader(f))
        row['status'] = 'VALID'
        rows.append(row)
    with (a.out_dir/'results.csv').open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['method', 'Population-linkage AUC', 'GDA-MIA AUC'], extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)
    (a.out_dir/'manifest.json').write_text(json.dumps({
        'protocol': 'train_bound_membership_attacks_v3', 'private_input_validation': verified,
        'commands': commands, 'empty_release_policy': 'NA, never invented AUC or copied score',
        'rows': rows}, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
