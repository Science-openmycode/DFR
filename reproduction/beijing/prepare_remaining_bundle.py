"""Export remaining experiment code once, preserving independent CLI entrypoints."""
import json
from pathlib import Path
import shutil
import zipfile
from preprocess.dataset_contract import sha

ROOT=Path(__file__).resolve().parent


def main():
    out=ROOT/'deployment/remaining_20261017_v2';archive=out.with_suffix('.zip')
    if out.exists() or archive.exists():raise FileExistsError('New isolated bundle required')
    c=json.loads((ROOT/'configs/beijing_roads_8_16_matcher_io_v2_20261016.json').read_text(encoding='utf-8'))
    base=ROOT/c['paths']['output']/c['batch'];files={}
    def copy(source,name):
        target=out/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target);files[str(name).replace('\\','/')]=sha(target)
    for f in ROOT.glob('*.py'):copy(f,f.name)
    for folder in ('algorithms','evaluation','preprocess','plotting','experiments','tools'):
        for f in (ROOT/folder).rglob('*'):
            if f.is_file() and f.suffix in ('.py','.json'):copy(f,f.relative_to(ROOT))
    legacy=(ROOT/c['paths']['legacy']).resolve()
    for folder in ('evaluation','generation/common','configs'):
        for f in (legacy/folder).rglob('*'):
            if f.is_file() and f.suffix in ('.py','.json'):copy(f,Path('legacy')/f.relative_to(legacy))
    for f in (legacy/'generation').glob('__init__.py'):copy(f,Path('legacy/generation')/f.name)
    for method in c['methods']:
        for f in (base/'measurements'/method).iterdir():
            if f.is_file():copy(f,Path('data_results/simple_runs')/c['batch']/'measurements'/method/f.name)
        for router in ('Nearest','FMM','STMatch'):
            actual='FMM_io_v2' if method=='SPRT' and router=='FMM' else router
            for name in ('synthetic_routes.pkl.gz','route_manifest.json'):
                copy(base/'routes'/method/actual/name,Path('data_results/simple_runs')/c['batch']/'routes'/method/actual/name)
    # Preserve completed native/ablation inputs for later separate commands too.
    for folder in ('ablation/MTR-DFR/arms','ablation/MTR-DFR/representations','routes/MTR-DFR','routes/MTNet'):
        for f in (base/folder).rglob('*'):
            if f.is_file():copy(f,Path('data_results/simple_runs')/c['batch']/folder/f.relative_to(base/folder))
    c['paths'].update(prepared='D:/MTR/mtnet_input_remote_20261017/inputs/dataset',
        real='D:/MTR/mtnet_input_remote_20261017/inputs/dataset/trajectories.pkl',
        real_routes='D:/MTR/mtnet_input_remote_20261017/inputs/dataset/road_records.pkl.gz',
        train='D:/MTR/mtnet_input_remote_20261017/inputs/dataset/train.pkl',
        test='D:/MTR/mtnet_input_remote_20261017/inputs/dataset/test.pkl',
        network='D:/MTR/network/network.shp',edge_cache='D:/MTR/experiments_20261016/public_context/edge_cache.pkl.gz',
        osm='D:/MTR/strict_tstr_mtnet_20261017/inputs/osm.pkl',legacy='legacy',output='data_results/simple_runs')
    target=out/'configs/beijing_roads_8_16_matcher_io_v2_20261016.json';target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(c,indent=2),encoding='utf-8');files[target.relative_to(out).as_posix()]=sha(target)
    copy(ROOT/'SERVER_REMAINING_COMMANDS_20261017_CN.md','SERVER_REMAINING_COMMANDS_20261017_CN.md')
    copy(ROOT/'deployment/observe_remaining_execution.py','observe_remaining_execution.py')
    (out/'deployment_binding.json').write_text(json.dumps(dict(files=files,dataset_id=c['frozen_dataset_id'],
        scope='Current full-corpus coordinate replays only; no DPMM duplicate; further tasks remain independently bound'),indent=2),encoding='utf-8')
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=1) as z:
        for f in out.rglob('*'):
            if f.is_file():z.write(f,f.relative_to(out))
    print(json.dumps(dict(files=len(files),bytes=archive.stat().st_size,sha256=sha(archive))))


if __name__=='__main__':main()
