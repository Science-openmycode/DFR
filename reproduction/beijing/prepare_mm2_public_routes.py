"""Batch-export all eight saved M releases and public-only MM2 routing code."""
import argparse
import json
import pickle
from pathlib import Path
import shutil
import zipfile
from preprocess.dataset_contract import sha

ROOT=Path(__file__).resolve().parent
METHODS=('SPRT','PrivTrace','DPStd','DPTraj-PM')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('config','resources','out','archive'):
        p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    if a.out.exists() or a.archive.exists():raise FileExistsError('Use new deployment paths')
    c=json.loads(a.config.read_text(encoding='utf-8'))
    resources=json.loads(a.resources.read_text(encoding='utf-8-sig'))
    prepared=(ROOT/c['paths']['prepared']).resolve()
    canonical=json.loads((prepared/'canonical_manifest.json').read_text(encoding='utf-8'))
    if sha(prepared/'canonical_manifest.json')!=c['frozen_dataset_id'] or resources['dataset_id']!=c['frozen_dataset_id']:
        raise ValueError('Wrong frozen dataset identity')
    files={}
    def copy(src,name):
        target=a.out/name;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(src,target);files[name]=sha(target)
        if files[name]!=sha(src):raise ValueError('Copy changed input')
    for name in ('run.py','route.py','experiments/separate.py','preprocess/public_routing_contract.py',
                 'algorithms/routers/mm2_mdp_adapter.py','tools/check_documented_command.py'):
        copy(ROOT/name,name)
    copy(prepared/'bbox.json','public_context/bbox.json')
    base=ROOT/c['paths']['output']/c['batch']
    for population,folder,artifact,count in (
            ('full','measurements','trajectories.pkl',canonical['trajectory_count']),
            ('train','measurements_train','train.pkl',canonical['train_count'])):
        bindings={};inputs={}
        for method in METHODS:
            source=base/folder/method
            meta=json.loads((source/'measurement_manifest.json').read_text(encoding='utf-8'))
            input_sha=meta.get('input_sha256',meta.get('prepared_sha256'))
            slot_count=meta.get('public_slot_count')
            if population=='train' and (input_sha is None or slot_count is None):
                proof=json.loads((source/'lineage.json').read_text(encoding='utf-8'))
                if (proof.get('schema')!='executed_train_only_generation_v1'
                        or proof.get('status')!='passed' or proof.get('returncode')!=0
                        or proof.get('input_policy')!='train_only_explicit_generator_input'
                        or proof.get('outputs',{}).get('measurement.pkl')!=sha(source/'measurement.pkl')):
                    raise ValueError('Legacy train M requires complete executed lineage')
                input_sha=proof['train_sha256'];slot_count=count
            if (meta.get('M')!=method or meta.get('status','VALID' if meta.get('kind')=='measurement' else None)!='VALID'
                    or slot_count!=count or meta.get('epsilon')!=c['epsilon']
                    or input_sha!=canonical['artifacts'][artifact]
                    or meta.get('outputs',{}).get('measurement.pkl')!=sha(source/'measurement.pkl')):
                raise ValueError('Unverified M release: '+population+'/'+method)
            dest=f'inputs/{folder}/{method}'
            bindings[method]={name:sha(source/name) for name in ('measurement.pkl','measurement_manifest.json')}
            for name in bindings[method]:copy(source/name,dest+'/'+name)
            with (source/'measurement.pkl').open('rb') as handle:
                if len(pickle.load(handle))!=count:raise ValueError('Saved M slot count differs')
            bindings[method]['records']=count
            if (source/'lineage.json').exists():
                copy(source/'lineage.json',dest+'/lineage.json')
                bindings[method]['lineage.json']=sha(source/'lineage.json')
            inputs[method]=dest
        cfg=dict(dataset='beijing',batch=c['batch']+('/train_only' if population=='train' else ''),
            dataset_policy='saved-dp-measurement-public-r-only',frozen_dataset_id=c['frozen_dataset_id'],
            slots=count,train_slots=canonical['train_count'],epsilon=c['epsilon'],threads=1,
            paths=dict(output='results',prepared='public_context',legacy='legacy',
                edge_cache='D:/MTR/mm2_frozen_20261018/inputs/metric_cache.pkl.gz',
                network='D:/MTR/network/network.shp',mm2='D:/MTR/mm2_frozen_20261018/map_matching_2.exe',
                mm2_network='D:/MTR/mm2_frozen_20261018/network'),routing_inputs=inputs,
            public_routing_contract=dict(schema='verified-measurement-public-routing-v1',
                dataset_id=c['frozen_dataset_id'],slots=count,population_input_sha256=canonical['artifacts'][artifact],
                measurements=bindings,public_files=resources['files']))
        target=a.out/f'configs/{population}.json';target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(json.dumps(cfg,indent=2),encoding='utf-8');files[f'configs/{population}.json']=sha(target)
    record=dict(dataset_id=c['frozen_dataset_id'],files=files,public_files=resources['files'],
        scope='ALL_FOUR_M_FULL_AND_TRAIN_PUBLIC_R_ONLY_NO_REAL_TRAJECTORIES')
    (a.out/'deployment_binding.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
    with zipfile.ZipFile(a.archive,'x',zipfile.ZIP_DEFLATED,compresslevel=1) as z:
        for f in sorted(a.out.rglob('*')):
            if f.is_file():z.write(f,f.relative_to(a.out))
    print(json.dumps(dict(bytes=a.archive.stat().st_size,sha256=sha(a.archive),files=len(files))))


if __name__=='__main__':main()
