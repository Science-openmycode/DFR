"""Prepare explicit application commands for completed K/budget road releases.

Preparation only. No generation, matching, scoring or command execution.
The source plan is shared with collect_portable_sweeps; absolute historical
paths are accepted for replay, relative paths are resolved against this root.
"""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def prepare(plan, application_config, reference, out, kind='all'):
    from evaluation.applications.engine import load_config
    from evaluation.applications.metrics import digest
    cfg = load_config(application_config)
    rm = json.loads((reference/'manifest.json').read_text(encoding='utf-8'))
    if (rm['status'] != 'COMPLETE' or rm['dataset_id'] != cfg['dataset_id']
            or rm['questions_sha256'] != digest(cfg['questions'])
            or rm['resources_sha256'] != digest(cfg['resources']/'manifest.json')):
        raise ValueError('Reference does not use the locked main-experiment questions/resources')
    for name, value in rm['outputs'].items():
        if digest(reference/name) != value:
            raise ValueError('Changed real reference')
    cells = [c for c in json.loads(plan.read_text(encoding='utf-8'))['cells'] if c['kind'] in ('k', 'budget') and (kind == 'all' or c['kind'] == kind)]
    for selected, count in [('k', 30), ('budget', 35)]:
        if kind not in ('all', selected):
            continue
        group = [c for c in cells if c['kind'] == selected]
        if len(group) != count or len({(c['value'], c['seed']) for c in group}) != count:
            raise ValueError('Incomplete or duplicate sweep: '+selected)
        values = [24, 48, 96, 192, 384, 768] if selected == 'k' else [.2, .4, .7, 1, 1.4, 2, 3]
        if {(c['value'], c['seed']) for c in group} != {(v, s) for v in values for s in range(20260719, 20260724)}:
            raise ValueError('Unexpected sweep values/seeds: '+selected)
    # Preflight every input before creating a runnable plan.
    sources = {}
    for c in cells:
        post = ROOT/Path(c.get('post_directory', c['directory']))
        src = post/'representation/synthetic_routes.pkl.gz'
        manifest = json.loads((post/'representation/route_manifest.json').read_text(encoding='utf-8'))
        if manifest['records'] != cfg['slots'] or manifest['rematched'] is not False or manifest['output_sha256'] != digest(src):
            raise ValueError('Unaccepted saved road release: '+str(src))
        sources[c['name']] = (src.resolve(), digest(src))
    out.mkdir(parents=True, exist_ok=False)
    lines = ['# K与预算：新四项应用补评', '',
             '工作目录：reproduction/beijing；先完成第05节真实答题。仅转换已有道路表示，不训练、不生成、不重新匹配。',
             '沿用主实验锁定问题、区域、40米覆盖距离与路线预算。失败保留唯一目录；验收成功后接下一条。', '', '```powershell']
    result = []; unique = {}
    for c in cells:
        src, h = sources[c['name']]
        if h not in unique:
            b = (out/c['name']).resolve(); b.mkdir()
            real = next(m for m in cfg['methods'] if m['name'] == cfg['real_method'])
            config = b/'config.json'
            commands = [f'.venv/Scripts/python.exe prepare_application_inputs.py adapt --input "{src}" --public-edges "{cfg["public_edges"].resolve()}" --slots {cfg["slots"]} --out "{b/"slots"}"',
                        f'.venv/Scripts/python.exe configure_applications.py --questions "{cfg["questions"].resolve()}" --region "{cfg["region"].resolve()}" --public-edges "{cfg["public_edges"].resolve()}" --real-slots "{real["slots"].resolve()}" --release "{c["name"]}={b/"slots/slots.jsonl.gz"}" --slots {cfg["slots"]} --resources "{cfg["resources"].resolve()}" --coverage-distance-m {cfg["coverage_distance_m"]} --route-budget-m {cfg["route_budget_m"]} --out "{config}"',
                        f'.venv/Scripts/python.exe evaluate_applications.py answer --config "{config}" --method {c["name"]} --reference "{reference.resolve()}" --out "{b/"answers"}"']
            lines.extend(commands)
            unique[h] = dict(answer=str(b/'answers'), config=str(config), name=c['name'])
        result.append(dict(kind=c['kind'], value=c['value'], seed=c['seed'], name=c['name'],
                           source=str(src), source_sha256=h, answer=unique[h]['answer'], config=unique[h]['config'], answer_method=unique[h]['name']))
    lines += ['```', '', '成功条件：每份答案COMPLETE、完整槽位、同问题/图/来源绑定及四项有限分数；退出和耗时独立记账。']
    document = out/'COMMANDS_CN.md'; document.write_text('\n'.join(lines)+'\n', encoding='utf-8')
    (out/'plan.json').write_text(json.dumps(dict(dataset_id=cfg['dataset_id'], cells=result,
        document=str(document), document_sha256=digest(document), unique_releases=len(unique)), indent=2), encoding='utf-8')
    print('PREPARED', len(cells), 'cells;', len(unique), 'unique releases; no scoring executed')


if __name__ == '__main__':
    import sys
    sys.path.insert(0, str(ROOT))
    p = argparse.ArgumentParser(description=__doc__)
    for n in ('plan', 'application-config', 'reference', 'out'):
        p.add_argument('--'+n, type=Path, required=True)
    p.add_argument('--kind', choices=['all', 'k', 'budget'], default='all')
    a = p.parse_args(); prepare(a.plan, a.application_config, a.reference, a.out, a.kind)
