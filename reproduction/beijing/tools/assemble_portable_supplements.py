"""Maintainer-only assembly: copy exact saved dependencies; never execute experiments."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]


def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def assemble(source):
    inventory=[]
    def copy(src,rel):
        src=Path(src); dst=ROOT/rel
        if not src.is_file():raise FileNotFoundError(src)
        digest=sha(src)
        if dst.exists() and sha(dst)!=digest:
            backup=ROOT/'supplement/previous_code'/rel
            if backup.exists() and sha(backup)!=sha(dst):raise ValueError('Backup conflict '+str(dst))
            backup.parent.mkdir(parents=True,exist_ok=True)
            if not backup.exists():shutil.copy2(dst,backup)
        dst.parent.mkdir(parents=True,exist_ok=True)
        if not dst.exists() or sha(dst)!=digest:shutil.copy2(src,dst)
        assert sha(dst)==digest
        inventory.append({'path':dst.relative_to(ROOT).as_posix(),'sha256':digest,'source':str(src)})
        return dst.relative_to(ROOT).as_posix()
    def directory(src,rel):
        for p in Path(src).rglob('*'):
            if p.is_file() and '__pycache__' not in p.parts:
                copy(p,Path(rel)/p.relative_to(src))
    for name in ['evaluation/run_bound_ordered_attack.py','evaluation/vendor/evaluate_ordered_interface_linkage.py',
                 'tools/plot_executed_results.py','experiments/plot.py',
                 'plotting/render_verified_matrix.py','plotting/plot_current_frozen.py']:
        copy(source/name,name)
    directory(source/'repairs/k_partition_20261020/algorithm','repairs/k_partition_20261020/algorithm')
    original=json.loads((source/'repairs/closure_repair_20261023/complete_config.json').read_text(encoding='utf-8'))
    config=json.loads((ROOT/'configs/beijing.json').read_text(encoding='utf-8'))
    config.pop('unsupported_stages',None)
    config['paths']['mm2_edge_cache']=config['paths']['metric_cache']
    for key in ['members','nonmembers','reference','attack_manifest']:
        p=Path(original['paths'][key]);p=p if p.is_absolute() else source/p
        config['paths'][key]=copy(p,Path('resources/attacks')/p.name)
    for section in ['tstr_releases','attack_releases']:
        config[section]={}
        for i,(name,item) in enumerate(original[section].items()):
            target={}
            for key,value in item.items():
                p=Path(value);p=p if p.is_absolute() else source/p
                target[key]=copy(p,Path('reference_results/train_releases')/f'{i:02d}'/p.name)
                sidecar=p.with_name(p.name+'.manifest.json')
                if sidecar.exists():copy(sidecar,Path(target[key]+'.manifest.json'))
            config[section][name]=target
    config['attack_resources_status']='PREPARED_CURRENT_TRAIN_SPLIT'
    config['batch']='portable_supplement'
    (ROOT/'configs/portable_supplement.json').write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8')
    for batch,sub in [('closure_tstr_cli_20261023','tstr_audit_v2'),('closure_attack_cli_20261023','privacy')]:
        for name in ['results.csv','manifest.json']:
            copy(source/'data_results/simple_runs'/batch/sub/name,Path('reference_results')/sub/name)
    matrix=source/'data_results/simple_runs/roads_8_16_20261016/source_matrix_final_controls_20261019'
    dest=ROOT/'reference_results/matrix';dest.mkdir(parents=True,exist_ok=True)
    directory(matrix,'supplement/original_matrix_records')
    with (matrix/'matrix_sources.csv').open(encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f);fields=reader.fieldnames; rows=list(reader)
    for row in rows:
        for key in ['result','manifest']:
            if row.get(key):
                p=Path(row[key]);p=p if p.is_absolute() else source/p
                digest=sha(p)
                if digest!=row[key+'_sha256']:raise ValueError('Source score changed')
                row[key]=copy(p,Path('reference_results/matrix_inputs')/digest/p.name)
    with (dest/'matrix_sources.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)
    copy(matrix/'spec.json','reference_results/matrix/spec.json')
    meta=json.loads((matrix/'manifest.json').read_text(encoding='utf-8'))
    meta['portable_source_manifest_sha256']=sha(matrix/'manifest.json')
    meta['outputs']['matrix_sources.csv']=sha(dest/'matrix_sources.csv')
    meta['relocation_only_values_unchanged']=True
    (dest/'manifest.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
    directory(source/'plotting/output/roads_8_16_20261016/final_controls_20261019','reference_results/matrix_previous')
    copy(source.parent/'dfr_all_figure_pairs_20261007/reference/04.png','reference_results/github/04.png')
    copy(source/'data_results/budget35_20261020/summary_20261020/summary.json','reference_results/budget/summary.json')
    copy(source/'plotting/budget_paper_20261020/render.py','supplement/budget/render.py')
    copy(source/'plotting/budget_paper_20261020/github_readme_profile.png','supplement/budget/github_readme_profile.png')
    directory(source/'data_results/budget35_20261020/figures_20261020','reference_results/budget/previous')
    copy(source/'data_results/budget35_20261020/paper_budget_reference.png','reference_results/budget/paper_budget_reference.png')
    directory(source/'repairs/k_extension_20261023/summary','reference_results/k')
    (ROOT/'supplement/assembly_inventory.json').write_text(json.dumps(inventory,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'files':len(inventory),'bytes':sum((ROOT/r['path']).stat().st_size for r in inventory),'experiments_run':0}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True)
    assemble(p.parse_args().source.resolve())
