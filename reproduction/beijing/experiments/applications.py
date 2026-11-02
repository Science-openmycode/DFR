"""Evaluate the four road applications from explicitly prepared full road releases."""
import argparse
import json
from pathlib import Path
import sys
from _runner import ROOT, execute


def plan(config, out):
    sys.path.insert(0, str(ROOT))
    from evaluation.applications.engine import load_config
    cfg = load_config(config)
    script = ROOT/'evaluate_applications.py'
    resources = cfg['resources'].resolve()
    steps = []
    def add(name, stage, flags, outputs, inputs):
        steps.append(dict(name=name, command=[sys.executable, '-X', 'utf8', str(script), stage,
                         '--config', str(config.resolve()), *map(str, flags)],
                         inputs=list(map(str, [config, script, *inputs])), outputs=list(map(str, outputs))))
    add('prepare', 'prepare', ['--out', resources], [resources/'manifest.json'],
        [cfg['public_edges'], cfg['questions'], cfg['region']])
    methods = [cfg['real_method']] + [x['name'] for x in cfg['methods'] if x['name'] != cfg['real_method']]
    answers = []
    for index, name in enumerate(methods):
        answer = out/'answers'/f'{index:02d}'
        flags = ['--method', name, '--out', answer]
        item = next(x for x in cfg['methods'] if x['name'] == name)
        inputs = [item['slots'], resources/'manifest.json']
        if index:
            flags += ['--reference', answers[0]]
            inputs.append(answers[0]/'manifest.json')
        add('answer_'+str(index), 'answer', flags, [answer/'manifest.json', answer/'metrics.json'], inputs)
        answers.append(answer)
    flags = [part for a in answers for part in ('--input', a)] + ['--out', out/'summary']
    add('summary', 'summarize', flags, [out/'summary/manifest.json', out/'summary/results.csv'],
        [a/'manifest.json' for a in answers])
    return steps


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', type=Path, required=True, help='Application config from README section 05')
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--dry-run', action='store_true')
    a = p.parse_args()
    steps = plan(a.config.resolve(), a.out.resolve())
    if a.dry_run:
        print(json.dumps(steps, ensure_ascii=False, indent=2))
        return
    execute(steps, a.out/'execution_logs', ROOT)


if __name__ == '__main__':
    main()
