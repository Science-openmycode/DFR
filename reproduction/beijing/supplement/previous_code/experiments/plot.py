"""Invoke the existing figure code on executed results, never frozen fallback data."""
import argparse
import json
from pathlib import Path
import sys
from _runner import ROOT, execute


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT / 'configs/beijing.yaml')
    parser.add_argument('--experiment', required=True, choices=['ablation', 'tstr', 'privacy_attack'])
    parser.add_argument('--batch')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding='utf-8-sig'))
    batch = args.batch or config['batch']
    if Path(batch).name != batch or batch in ('.', '..'):
        parser.error('batch must be a single directory name')
    directory = (ROOT / config['paths']['output'] / batch).resolve()
    script = (ROOT / config['paths']['legacy'] / 'plotting/regenerate_figures.py').resolve()
    figure, basename = {'ablation': ('ablation', '05_ablation'), 'tstr': ('tstr', '06_strict_tstr'), 'privacy_attack': ('privacy', '03_privacy_attacks')}[args.experiment]
    outputs = directory / 'figures' / figure
    steps = [{'name': 'plot_' + figure, 'command': [sys.executable, '-X', 'utf8', str(script), '--figure', figure, '--data-root', str(directory), '--out-dir', str(outputs)], 'inputs': [str(script), str(directory / figure / 'results.csv')], 'outputs': [str(outputs / (basename + '.png')), str(outputs / (basename + '.pdf'))]}]
    if args.dry_run:
        print(json.dumps(steps, ensure_ascii=False, indent=2))
        return
    execute(steps, directory / 'logs' / 'plotting', ROOT)


if __name__ == '__main__':
    main()
