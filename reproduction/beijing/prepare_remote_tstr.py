"""Export unchanged audit-v2 scoring and hash-bound private references to the user's server."""
import argparse
import json
from pathlib import Path
import shutil
import zipfile

from preprocess.dataset_contract import sha, validate_dataset

ROOT=Path(__file__).resolve().parent


def safe_relative(name):
    value=Path(name)
    if value.is_absolute() or '..' in value.parts:
        raise ValueError('Bundle path must stay inside its root')
    return value


def parse_cell(value):
    parts=value.split('/')
    if parts in (['MTNet','Origin'],['DPMM','Origin']):return tuple(parts)
    if (len(parts)!=2 or parts[0] not in ('SPRT','PrivTrace','DPStd','DPTraj-PM')
            or parts[1] not in ('Origin','Nearest','FMM','STMatch','MM2-MDP')):
        raise ValueError('Expected a supported M/R pair')
    return tuple(parts)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--archive',type=Path,required=True)
    p.add_argument('--cells',nargs='+',default=['DPStd/FMM','DPTraj-PM/FMM'])
    a=p.parse_args()
    if a.out.exists() or a.archive.exists():raise FileExistsError('Choose new bundle paths')
    cells=[parse_cell(v) for v in a.cells]
    if len(set(cells))!=len(cells):raise ValueError('Duplicate cells')
    c=json.loads(a.config.read_text(encoding='utf-8-sig'))
    def path(k):return (ROOT/c['paths'][k]).resolve()
    identity=validate_dataset(path('prepared'))
    if identity['dataset_id']!=c['frozen_dataset_id']:raise ValueError('Wrong frozen dataset')
    split=json.loads(path('split_audit').read_text(encoding='utf-8'))
    if (split.get('status')!='passed' or not split.get('all_source_indices_used_once')
            or split['train_sha256']!=sha(path('train')) or split['test_sha256']!=sha(path('test'))
            or split['train_count']!=12584 or split['test_count']!=3146):
        raise ValueError('Wrong strict TSTR split')
    files={}
    def copy(source,name):
        target=a.out/safe_relative(name);target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source,target);files[target.relative_to(a.out).as_posix()]=sha(target)
    for file in (path('legacy')/'evaluation').rglob('*.py'):
        copy(file,Path('legacy/evaluation')/file.relative_to(path('legacy')/'evaluation'))
    for file in ('evaluate_tstr.py','evaluation/audit_v2_runner.py','evaluation/audit_metric_fixes.py'):
        copy(ROOT/file,file)
    for key in ('train','test','split_audit','osm'):
        copy(path(key),'inputs/'+{'train':'train.pkl','test':'test.pkl','split_audit':'split_audit.json','osm':'osm.pkl'}[key])
    base=path('output')/c['batch']
    for method,router in cells:
        if (base/'tstr_audit_v2'/method/router/'manifest.json').exists():
            raise ValueError('Already completed corrected cell: '+method+'/'+router)
        if method=='DPMM':
            view=base/'coordinate_views_train'/method/router
            meta=json.loads((view/'manifest.json').read_text(encoding='utf-8'))
            lineage=json.loads((view/'lineage.json').read_text(encoding='utf-8'))
            native=base/'native_train/DPMM'
            if (meta.get('schema_version')!='dpmm-evaluation-slot-staging-v1'
                    or meta.get('original_slot_count')!=12584
                    or meta.get('unchanged_released_arrays_verified') is not True
                    or meta.get('rematched') is not False
                    or meta['output']['sha256']!=sha(view/'coordinates.pkl')
                    or meta['inputs']['release']['sha256']!=sha(native/'dpmm.pkl')
                    or meta['inputs']['manifest']['sha256']!=sha(native/'dpmm.json')
                    or lineage.get('execution_sha256')!=sha(native/'new_dataset_execution.json')
                    or lineage.get('train_sha256')!=split['train_sha256']
                    or lineage.get('test_sha256')!=split['test_sha256']
                    or lineage.get('outputs',{}).get('coordinates.pkl')!=sha(view/'coordinates.pkl')):
                raise ValueError('Wrong DPMM train-only native ancestry')
            for name in ('coordinates.pkl','manifest.json'):
                copy(view/name,f'views/{method}/{router}/{name}')
            copy(view/'lineage.json',f'inputs/{method}/lineage.json')
            continue
        if method=='MTNet':
            view=base/'coordinate_views_train'/method/router
            meta=json.loads((view/'manifest.json').read_text(encoding='utf-8'))
            native=base/'native_train/MTNet/native_release/routes.pkl'
            if (meta['record_count']!=12584 or meta['coordinates']['sha256']!=sha(view/'coordinates.pkl')
                    or meta['route_source']['sha256']!=sha(native) or meta.get('rematched') is not False):
                raise ValueError('Wrong native train-only geometry ancestry')
            for name in ('coordinates.pkl','coordinates.pkl.manifest.json','manifest.json'):
                copy(view/name,f'views/{method}/{router}/{name}')
            copy(base/'native_train/MTNet/lineage.json',f'inputs/{method}/lineage.json')
            continue
        if router=='Origin':
            copy(base/'measurements_train'/method/'measurement.pkl',f'views/{method}/{router}/coordinates.pkl')
        else:
            view=base/'coordinate_views_train'/method/router
            meta=json.loads((view/'manifest.json').read_text(encoding='utf-8'))
            if (meta['record_count']!=12584 or meta['coordinates']['sha256']!=sha(view/'coordinates.pkl')
                    or meta['route_source']['sha256']!=sha(base/'measurements_train'/method/'measurement.pkl')
                    or meta['routed_artifact']['sha256']!=sha(base/'routes_train'/method/router/'synthetic_routes.pkl.gz')):
                raise ValueError('Wrong saved train geometry or ancestry')
            for name in ('coordinates.pkl','coordinates.pkl.manifest.json','manifest.json'):
                copy(view/name,f'views/{method}/{router}/{name}')
        copy(base/'measurements_train'/method/'lineage.json',f'inputs/{method}/lineage.json')
    portable=dict(c)
    portable['paths']=dict(legacy='legacy',output='results',train='inputs/train.pkl',test='inputs/test.pkl',
                           split_audit='inputs/split_audit.json',osm='inputs/osm.pkl')
    config=a.out/'config.json'
    config.write_text(json.dumps(portable,ensure_ascii=False,indent=2),encoding='utf-8')
    files['config.json']=sha(config)
    copy(ROOT/'deployment/RUN_REMOTE_TSTR_20261017.ps1','RUN_REMOTE_TSTR_20261017.ps1')
    record=dict(classification='PRIVATE_RESEARCH_EVALUATION_NOT_DP_RELEASE',dataset_id=identity['dataset_id'],cells=a.cells,
                files=files,original_config_sha256=sha(a.config),train_count=12584,test_count=3146)
    (a.out/'deployment_binding.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
    with zipfile.ZipFile(a.archive,'x',zipfile.ZIP_DEFLATED,compresslevel=1) as z:
        for file in sorted(a.out.rglob('*')):
            if file.is_file():z.write(file,file.relative_to(a.out))
    print(json.dumps(dict(archive_sha256=sha(a.archive),bytes=a.archive.stat().st_size,files=len(files))))


if __name__=='__main__':main()
