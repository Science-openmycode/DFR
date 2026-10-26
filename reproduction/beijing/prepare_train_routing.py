"""Export only existing train-only synthetic M releases for public routing."""
import argparse
import json
from pathlib import Path
import pickle
import shutil
import zipfile

from preprocess.dataset_contract import sha

ROOT=Path(__file__).resolve().parent


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--archive',type=Path,required=True)
    a=p.parse_args()
    if a.out.exists() or a.archive.exists():raise FileExistsError('Choose new export paths')
    c=json.loads(a.config.read_text(encoding='utf-8'))
    base=ROOT/c['paths']['output']/c['batch'];files={};a.out.mkdir(parents=True)
    for method in c['methods']:
        source=base/'measurements_train'/method
        meta=json.loads((source/'measurement_manifest.json').read_text(encoding='utf-8'))
        lineage=json.loads((source/'lineage.json').read_text(encoding='utf-8'))
        if (lineage.get('status')!='passed' or lineage.get('returncode')!=0
                or lineage['train_sha256']!=sha(ROOT/c['paths']['train'])
                or lineage['test_sha256']!=sha(ROOT/c['paths']['test'])
                or lineage.get('input_policy')!='train_only_explicit_generator_input'):
            raise ValueError('No executed train-only generation evidence')
        if (meta.get('M')!=method or meta.get('kind')!='measurement' or meta.get('epsilon')!=c['epsilon']
                or ('status' in meta and meta['status']!='VALID')
                or ('public_slot_count' in meta and meta['public_slot_count']!=c['train_slots'])):
            raise ValueError('Incomplete or wrong-size training M')
        with (source/'measurement.pkl').open('rb') as f:count=len(pickle.load(f))
        if (count!=c['train_slots'] or sha(source/'measurement.pkl')!=meta['outputs']['measurement.pkl']
                or sha(source/'measurement.pkl')!=lineage['outputs']['measurement.pkl']):
            raise ValueError('Training M content differs')
        for name in ('measurement.pkl','measurement_manifest.json'):
            dest=a.out/'train_inputs'/method/name;dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(source/name,dest);files[dest.relative_to(a.out).as_posix()]=sha(dest)
    (a.out/'train_routing_bindings.json').write_text(json.dumps(dict(dataset_id=c['frozen_dataset_id'],
        slots=c['train_slots'],files=files,scope='Only synthetic training M and public R; no original train/test coordinates exported'),indent=2),encoding='utf-8')
    shutil.copy2(ROOT/'deployment/RUN_TRAIN_STMATCH.ps1',a.out/'RUN_TRAIN_STMATCH.ps1')
    with zipfile.ZipFile(a.archive,'x',zipfile.ZIP_DEFLATED,compresslevel=3) as z:
        for file in sorted(a.out.rglob('*')):
            if file.is_file():z.write(file,file.relative_to(a.out))
    print('TRAIN_ROUTING_EXPORT',a.archive.stat().st_size,sha(a.archive))


if __name__=='__main__':main()
