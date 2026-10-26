"""Write explicit independent commands for a fresh batch; never execute experiments."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
METHODS = ('SPRT', 'PrivTrace', 'DPTraj-PM', 'DPStd')
ROUTERS = ('Origin', 'Nearest', 'FMM', 'STMatch', 'MM2-MDP')


def build(config, config_path, root):
    base = Path(config['paths']['output']) / config['batch']
    steps = []
    def add(name, script, flags, outputs, depends=()):
        argv = ['.venv/Scripts/python.exe', script, '--config', str(config_path), *map(str, flags)]
        steps.append(dict(id=name, command=subprocess.list2cmdline(argv),
                          outputs=list(map(str, outputs)), depends_on=list(depends)))
    for method in METHODS:
        for training in (False, True):
            suffix = 'train' if training else 'full'
            measurement = base / ('measurements_train' if training else 'measurements') / method
            mid = f'{method}/{suffix}/M'
            add(mid, 'synthesize.py', ['--method', method, '--out', measurement,
                *(['--train-only'] if training else [])], [measurement/'measurement.pkl', measurement/'measurement_manifest.json'])
            for router in ROUTERS:
                route = base / ('routes_train' if training else 'routes') / method / router
                rid = f'{method}/{suffix}/{router}/R'
                file = route / ('synthetic_coordinates.pkl' if router == 'Origin' else 'synthetic_routes.pkl.gz')
                add(rid, 'route.py', ['--method', method, '--router', router, '--input', measurement, '--out', route],
                    [file, route/'route_manifest.json'], [mid])
                if training:
                    # TSTR lineage preparation is a separate protocol, not full-corpus scoring.
                    continue
                coord = base/'coordinate_scores_audit_v2'/method/router
                add(f'{method}/{suffix}/{router}/coordinates', 'evaluate_coordinates.py',
                    ['--method', method, '--router', router, '--input', file, '--metric-protocol', 'audit-v2', '--out', coord],
                    [coord/'metrics.json', coord/'manifest.json'], [rid])
                if router == 'Origin':
                    continue
                score = base/'scores'/method/router
                sid = f'{method}/{suffix}/{router}/roads'
                add(sid, 'evaluate.py', ['--method', method, '--router', router, '--input', file, '--out', score],
                    [score/'metrics.json', score/'manifest.json'], [rid])
                physical = base/'physical_scores'/method/router
                add(f'{method}/{suffix}/{router}/physical', 'evaluate_physical.py',
                    ['--method', method, '--router', router, '--input', file, '--out', physical],
                    [physical/'results.csv', physical/'input_binding.json'], [rid])
                tasks = base/'road_tasks'/method/router
                add(f'{method}/{suffix}/{router}/road_tasks', 'evaluate_road_tasks.py',
                    ['--method', method, '--router', router, '--input', file,
                     '--score-manifest', score/'manifest.json', '--out', tasks],
                    [tasks/'metrics.json', tasks/'manifest.json'], [sid])
    return steps


def prepare(config_file, batch, out, root=ROOT, mm2_manifest=None):
    config_file = Path(config_file).resolve()
    out = Path(out).resolve()
    root = Path(root).resolve()
    if Path(batch).name != batch or batch in ('.', '..') or '/' in batch or '\\' in batch:
        raise ValueError('Batch must be one directory name')
    if out.exists():
        raise FileExistsError(out)
    if not out.is_relative_to(root):
        raise ValueError('Runbook must remain inside this deployment for portable relative commands')
    config = json.loads(config_file.read_text(encoding='utf-8-sig'))
    if config.get('dataset_policy') != 'frozen-road-only' or not config.get('frozen_dataset_id'):
        raise ValueError('A verified frozen dataset configuration is required')
    required = ('prepared', 'network', 'edge_cache', 'metric_cache', 'mm2', 'mm2_network',
                'fmm', 'stmatch', 'ubodt', 'runtime', 'legacy', 'output')
    for key in required:
        if key not in config['paths']:
            raise ValueError('Required deployment path is missing: '+key)
    for key in config['paths']:
        value = Path(config['paths'][key])
        if value.is_absolute():
            raise ValueError('Use deployment-relative paths before making a portable runbook: '+key)
        target = (root/value).resolve()
        if not target.is_relative_to(root):
            raise ValueError('Resource escapes deployment: '+key)
        if key != 'output' and not target.exists():
            raise FileNotFoundError(target)
    if (root/config['paths']['output']/batch).exists():
        raise FileExistsError('Existing experiment batch; choose a new name')
    fresh = copy.deepcopy(config)
    fresh['batch'] = batch
    fresh['methods'] = list(METHODS)
    fresh['routers'] = list(ROUTERS)
    for key in ('saved_route_inputs', 'routing_inputs', 'releases', 'tstr_releases', 'attack_releases'):
        fresh[key] = {}
    if mm2_manifest is not None:
        def sha(file):
            with Path(file).open('rb') as stream:
                return hashlib.file_digest(stream,'sha256').hexdigest()
        route = json.loads(Path(mm2_manifest).read_text(encoding='utf-8-sig'))
        if route.get('raw_source_used') is not False or not route.get('public_raw_node_connectivity_checked'):
            raise ValueError('MM2 provenance does not certify public raw-node connectivity')
        resources = (root/fresh['paths']['mm2']).parent
        binding = json.loads((resources/'binding.json').read_text(encoding='utf-8-sig'))
        for relative, expected in binding['files'].items():
            file = (root/relative).resolve()
            if not file.is_relative_to(root) or sha(file) != expected:
                raise ValueError('MM2 deployed resource differs: '+relative)
        for file, key in [(root/fresh['paths']['mm2'],'public_mm2_executable_sha256'),
                          (resources/'public_graph/inputs/public_edge_nodes.json','public_edge_nodes_sha256'),
                          (root/fresh['paths']['metric_cache'],'public_edge_cache_sha256')]:
            if sha(file) != route[key]:
                raise ValueError('MM2 provenance mismatch: '+key)
        fresh['paths']['mm2_edge_cache'] = fresh['paths']['metric_cache']
        fresh['mm2_resources_status'] = 'VERIFIED_RELOCATED_SAVED_PUBLIC_RESOURCES'
        fresh['runbook_mm2_provenance_sha256'] = sha(mm2_manifest)
    if not fresh['paths'].get('mm2_edge_cache'):
        raise ValueError('Bind mm2_edge_cache explicitly; do not infer its node namespace')
    target_config = out/'config.json'
    relative_config = target_config.relative_to(root).as_posix()
    steps = build(fresh, relative_config, root)
    lines = ['# 四个统计M：新批次独立命令清单', '',
        '在部署根目录执行。先设置当前终端编码；每条实验命令独立运行，不通过队列替换外层入口。', '',
        '```powershell', "$env:PYTHONUTF8='1'", "$env:PYTHONIOENCODING='utf-8'", '```', '',
        '全量发布用于统计/道路保真评价；训练发布只为后续严格TSTR准备，不能拿全量评分当TSTR。',
        '此清单覆盖四个统计M及五个R，不包括DFR/DPMM/MTNet原生生成、训练lineage登记、攻击、K/预算及作图。',
        '这是待执行的新批次计划，不是已完成的实验记录。M只生成一次，五个R读取同一份测量。', '']
    for step in steps:
        lines += ['## '+step['id'], '', '依赖：'+(', '.join(step['depends_on']) or '冻结输入与公共资源'), '', '```powershell']
        step['document_line'] = len(lines)+1
        lines += [step['command'], '```', '', '预期输出：'+ '、'.join('`'+p+'`' for p in step['outputs']), '']
    text = '\n'.join(lines)+'\n'
    out.mkdir(parents=True)
    target_config.write_text(json.dumps(fresh,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'COMMANDS_CN.md').write_text(text,encoding='utf-8')
    digest = hashlib.sha256((out/'COMMANDS_CN.md').read_bytes()).hexdigest()
    manifest = dict(status='PLAN_NOT_EXECUTED', source_config_sha256=hashlib.sha256(config_file.read_bytes()).hexdigest(),
                    config_sha256=hashlib.sha256(target_config.read_bytes()).hexdigest(),
                    document_sha256=digest, dataset_id=fresh['frozen_dataset_id'], batch=batch, steps=steps,
                    scope='Four statistical M; full/train M-R; full-corpus coordinate/road/physical/retrospective tasks')
    (out/'commands.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    return manifest


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',type=Path,required=True)
    p.add_argument('--batch',required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--mm2-route-manifest',type=Path,help='Previously verified public routing provenance; used only to bind resources, never to replace new outputs')
    a = p.parse_args()
    result = prepare(a.config,a.batch,a.out,mm2_manifest=a.mm2_route_manifest)
    print(json.dumps(dict(status=result['status'],commands=len(result['steps']),batch=a.batch)))


if __name__ == '__main__':
    main()
