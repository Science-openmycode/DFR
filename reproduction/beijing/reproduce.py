"""Run the connected experiment entries; MM2 is selected separately."""
import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT / 'configs/beijing.yaml')
    parser.add_argument('--batch')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--exclude-router', action='append', default=[])
    parser.add_argument('--only-router', choices=['Origin', 'Nearest', 'FMM', 'STMatch', 'MM2-MDP'])
    args = parser.parse_args()
    names = ['main'] if args.only_router else ['main', 'ablation', 'tstr', 'privacy_attack']
    for name in names:
        command = [sys.executable, '-X', 'utf8', str(ROOT / 'experiments' / (name + '.py')), '--config', str(args.config.resolve())]
        if args.batch:
            command += ['--batch', args.batch]
        if args.dry_run:
            command += ['--dry-run']
        if name == 'main':
            if args.only_router:
                command += ['--only-router', args.only_router]
            for router in args.exclude_router:
                command += ['--exclude-router', router]
        subprocess.run(command, check=True, cwd=ROOT)


if __name__ == '__main__':
    main()
