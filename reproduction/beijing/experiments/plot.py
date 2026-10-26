"""Invoke the existing figure code on executed results, never frozen fallback data."""
import argparse
import json
from pathlib import Path
import sys
from _runner import ROOT, execute


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT / 'configs/beijing.yaml')
    parser.add_argument('--experiment', required=True, choices=['ablation', 'tstr', 'privacy_attack'])
    parser.add_argument('--batch')
    parser.add_argument('--out-dir', type=Path, help='New isolated figure directory; never overwrite a previous figure')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding='utf-8-sig'))
    batch = args.batch or config['batch']
    if Path(batch).name != batch or batch in ('.', '..'):
        parser.error('batch must be a single directory name')
    directory = (ROOT / config['paths']['output'] / batch).resolve()
    script = (ROOT / config['paths']['legacy'] / 'plotting/regenerate_figures.py').resolve()
    figure, basename = {'ablation': ('ablation', '05_ablation'), 'tstr': ('tstr', '06_strict_tstr'), 'privacy_attack': ('privacy', '03_privacy_attacks')}[args.experiment]
    outputs = args.out_dir.resolve() if args.out_dir else directory / 'figures' / figure
    results = directory / ('tstr_audit_v2' if figure == 'tstr' else figure) / 'results.csv'
    wrapper = ROOT / 'tools/plot_executed_results.py'
    steps = [{'name': 'plot_' + figure, 'command': [sys.executable, '-X', 'utf8', str(wrapper), '--script', str(script), '--figure', figure, '--results', str(results), '--out-dir', str(outputs)], 'inputs': [str(wrapper), str(script), str(results)], 'outputs': [str(outputs / (basename + '.png')), str(outputs / (basename + '.pdf'))]}]
    if args.dry_run:
        print(json.dumps(steps, ensure_ascii=False, indent=2))
        return
    execute(steps, (outputs/'execution_logs') if args.out_dir else directory / 'logs' / 'plotting', ROOT)


if __name__ == '__main__':
    main()
