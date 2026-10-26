"""Bind an explicit executed CSV to the unchanged legacy plotting function."""
import argparse
import importlib.util
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--script', type=Path, required=True)
    parser.add_argument('--results', type=Path, required=True)
    parser.add_argument('--figure', choices=['tstr', 'ablation', 'privacy'], required=True)
    parser.add_argument('--out-dir', type=Path, required=True)
    args = parser.parse_args()
    if not args.results.is_file():
        parser.error(f'missing executed results: {args.results}')
    if args.out_dir.exists() and any(p.name != 'execution_logs' for p in args.out_dir.iterdir()):
        parser.error('output directory must be empty; existing figures are not overwritten')
    spec = importlib.util.spec_from_file_location('bound_legacy_figure', args.script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    def read_table(experiment, fallback, **kwargs):
        if experiment != args.figure:
            raise ValueError(f'unexpected experiment {experiment}')
        return module.pd.read_csv(args.results, **kwargs).drop(columns=['experiment'], errors='ignore')
    module.read_table = read_table
    module.OUT = args.out_dir.resolve()
    module.OUT.mkdir(parents=True, exist_ok=True)
    original_save = module.save
    def readable_save(fig, name):
        if args.figure == 'privacy':
            table = module.pd.read_csv(args.results)
            for ax in fig.axes:
                labels = ax.get_xticklabels()
                # A missing attack result is not a measured zero.
                if 'method' in table.columns:
                    value_columns = [c for c in table.columns if 'AUC' in c]
                    for tick, label in zip(ax.get_xticks(), labels):
                        row = table[table['method'] == label.get_text()]
                        if value_columns and len(row) == 1 and row[value_columns].isna().all(axis=None):
                            ax.text(tick, .025, 'NA', transform=ax.get_xaxis_transform(),
                                    ha='center', va='bottom', fontsize=8, color='#666666')
                if len(labels) > 8:
                    fig.set_size_inches(max(fig.get_figwidth(), .58 * len(labels)), fig.get_figheight() + 1.1)
                    for label in labels:
                        label.set_rotation(55)
                        label.set_ha('right')
                        label.set_fontsize(8)
                    fig.tight_layout()
        original_save(fig, name)
    module.save = readable_save
    getattr(module, 'plot_' + args.figure)()
    provenance = {'results_sha256': hashlib.sha256(args.results.read_bytes()).hexdigest(),
                  'renderer_sha256': hashlib.sha256(args.script.read_bytes()).hexdigest(),
                  'function': 'plot_' + args.figure, 'layout_only': True,
                  'scope': 'Executed CSV diagnostic; not a replacement for differently defined GitHub experiments'}
    (module.OUT/'figure_input.json').write_text(json.dumps(provenance, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
