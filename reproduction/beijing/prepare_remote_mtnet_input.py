"""Copy frozen MTNet input artifacts unchanged; rebind only machine-specific paths."""
import argparse
import json
from pathlib import Path
import shutil
import zipfile
from preprocess.dataset_contract import validate_dataset,sha

ROOT=Path(__file__).resolve().parent


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--archive',type=Path,required=True)
    a=p.parse_args()
    if a.out.exists() or a.archive.exists():raise FileExistsError('Choose new migration paths')
    c=json.loads(a.config.read_text(encoding='utf-8'));prepared=Path(c['paths']['prepared'])
    identity=validate_dataset(prepared)
    if identity['dataset_id']!=c['frozen_dataset_id']:raise ValueError('Wrong frozen dataset')
    original=ROOT/'../four_panel_completion_20261008/cloud_results/mtnet_full_archive/mtnet_gpu'
    files={}
    def copy(source,name):
        target=a.out/name;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source,target);files[target.relative_to(a.out).as_posix()]=sha(target)
    for file in prepared.iterdir():
        if file.is_file():copy(file,Path('inputs/dataset')/file.name)
    for file in ('prepare_mtnet_frozen.py','prepare_mtnet_deployment.py','generate_mtnet.py',
                 'preprocess/dataset_contract.py','deployment/RUN_MTNET_GPU.ps1'):
        copy(ROOT/file,Path(file))
    for file in ('prepare_beijing_nodp_fmm.py','prepare_mtnet_full_cloud.py','build_native_mtnet_inputs.py',
                 'official/data/demo/temporal_32.emb'):
        copy(original/file,Path('original')/file)
    copy(original/'mtnet_time_binding.json',Path('inputs/time_binding.json'))
    copy(ROOT/'../../results/fresh_repro_20260925/data/real_full_frozen.pkl',Path('inputs/raw_reference.pkl'))
    copy(Path(c['paths']['split_audit']),Path('inputs/split_audit.json'))
    c['paths']=dict(prepared='inputs/dataset',network='D:/MTR/network/network.shp',
        real='inputs/dataset/trajectories.pkl',real_routes='inputs/dataset/road_records.pkl.gz',
        train='inputs/dataset/train.pkl',test='inputs/dataset/test.pkl',split_audit='inputs/split_audit.json')
    config=a.out/'config.json';config.write_text(json.dumps(c,ensure_ascii=False,indent=2),encoding='utf-8')
    files['config.json']=sha(config)
    copy(ROOT/'deployment/RUN_REMOTE_MTNET_PREPARE_TRAIN_20261017.ps1',Path('RUN_REMOTE_MTNET_PREPARE_TRAIN_20261017.ps1'))
    (a.out/'deployment_binding.json').write_text(json.dumps(dict(files=files,dataset_id=identity['dataset_id'],
        classification='PRIVATE_RESEARCH_NOT_DP_RELEASE'),indent=2),encoding='utf-8')
    with zipfile.ZipFile(a.archive,'x',zipfile.ZIP_DEFLATED,compresslevel=1) as z:
        for file in sorted(a.out.rglob('*')):
            if file.is_file():z.write(file,file.relative_to(a.out))
    print(json.dumps(dict(bytes=a.archive.stat().st_size,sha256=sha(a.archive),files=len(files))))


if __name__=='__main__':main()
