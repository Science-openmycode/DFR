"""Small DPMM code-only export; bind existing unchanged server dataset and OSM."""
import json
from pathlib import Path
import shutil
import zipfile
from preprocess.dataset_contract import sha

ROOT=Path(__file__).resolve().parent


def main():
    out=ROOT/'deployment/dpmm_remote_20261017'
    archive=out.with_suffix('.zip')
    if out.exists() or archive.exists():raise FileExistsError('Choose a new isolated export')
    base=ROOT/'data_results/simple_runs/roads_8_16_20261016'
    v=json.loads((base/'dpmm_equivalence/validation.json').read_text())
    if (not v['complete'] or not v['passed'] or v['tested_records']!=60 or len(v['rows'])!=60
            or not all(x['exact_output_equal'] for x in v['rows'])):raise ValueError('Need 60/60 exact validation')
    original=ROOT.parent/'four_panel_completion_20261008/cloud_results/dpmm_full_archive/dpmm'
    files={}
    def copy(source,name):
        target=out/name;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source,target);files[name]=sha(target)
    for name in ('synthesize_dpmm.py','preprocess/dataset_contract.py','tools/dpmm_worker_bootstrap.py'):
        copy(ROOT/name,name)
    copy(ROOT.parent/'four_panel_completion_20261008/fast_dpmm_paths.py','fast_dpmm_paths.py')
    for name in ('public_utils.py','check/run_dpmm_official_beijing.py','check/official_repos/dpmm/map_matcher_traj_AStar_clean_taxi.py',
                 'check/official_repos/dpmm/Differential.py','check/official_repos/dpmm/Params.py'):
        copy(original/name,'original/'+name)
    copy(base/'dpmm_equivalence/validation.json','validation.json')
    for name in ('RUN_DPMM_REMOTE_20261017.ps1','dpmm_remote_preflight.py'):
        copy(ROOT/'deployment'/name,name)
    c=json.loads((ROOT/'configs/beijing_roads_8_16_matcher_io_v2_20261016.json').read_text(encoding='utf-8'))
    c['paths']=dict(prepared='D:/MTR/mtnet_input_remote_20261017/inputs/dataset',
        network='D:/MTR/network/network.shp',real='D:/MTR/mtnet_input_remote_20261017/inputs/dataset/trajectories.pkl',
        osm='D:/MTR/strict_tstr_mtnet_20261017/inputs/osm.pkl',output='results')
    target=out/'config.json';target.write_text(json.dumps(c,indent=2),encoding='utf-8');files['config.json']=sha(target)
    record=dict(classification='PRIVATE_RESEARCH_DPMM_EXPORT',files=files,dataset_id=c['frozen_dataset_id'],
        validation_sha256=sha(base/'dpmm_equivalence/validation.json'),workers=2,required_validation_records=60)
    (out/'deployment_binding.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED) as z:
        for p in out.rglob('*'):
            if p.is_file():z.write(p,p.relative_to(out))
    print(json.dumps(dict(files=len(files),archive_bytes=archive.stat().st_size,sha256=sha(archive))))


if __name__=='__main__':main()
