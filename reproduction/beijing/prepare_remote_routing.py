"""Export only saved synthetic M outputs, public resources and routing code."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

ROOT = Path(__file__).resolve().parent


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', type=Path, required=True)
    p.add_argument('--out-dir', type=Path, required=True)
    p.add_argument('--archive', type=Path, required=True)
    a = p.parse_args()
    if a.out_dir.exists() or a.archive.exists():
        p.error('export directory and archive must be new')
    c = json.loads(a.config.read_text(encoding='utf-8'))
    base = ROOT / c['paths']['output'] / c['batch']
    audit = json.loads((base/'measurements_verified.json').read_text(encoding='utf-8'))
    if audit['dataset']['dataset_id'] != c['frozen_dataset_id']:
        raise ValueError('Wrong verified dataset')
    files = []

    def copy(source, relative):
        source = Path(source).resolve()
        destination = a.out_dir / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        if sha(source) != sha(destination):
            raise ValueError('Copy changed content')
        files.append({'path': relative, 'absolute': False, 'sha256': sha(source)})

    a.out_dir.mkdir(parents=True)
    copy(ROOT/'run.py', 'run.py')
    for name in ('public_match_adapter.py', 'nearest_adapter.py'):
        copy(ROOT/'algorithms/routers'/name, 'algorithms/routers/'+name)
    legacy = ROOT / c['paths']['legacy']
    copy(legacy/'evaluation/evaluation/metric_suites/road_route.py', 'legacy/evaluation/evaluation/metric_suites/road_route.py')
    copy(ROOT/'deployment/remote_routing_20261016/RUN_REMOTE_ROUTE.ps1', 'RUN_REMOTE_ROUTE.ps1')
    copy(ROOT/c['paths']['edge_cache'], 'public_context/edge_cache.pkl.gz')
    copy(ROOT/c['paths']['prepared']/'bbox.json', 'public_context/bbox.json')
    copy(ROOT/c['paths']['stmatch'], 'matcher/stmatch.exe')
    copy((ROOT/c['paths']['stmatch']).parent/'FMMLIB.dll', 'matcher/FMMLIB.dll')
    copy(base/'measurements_verified.json', 'measurements_verified.json')
    for method in audit['methods']:
        source = base/'measurements'/method['method']
        if sha(source/'measurement.pkl') != method['measurement_sha256']:
            raise ValueError('Changed synthetic M output')
        for name in ('measurement.pkl', 'measurement_manifest.json'):
            copy(source/name, 'measurements/'+method['method']+'/'+name)
    network = ROOT / c['paths']['network']
    for suffix in ('.shp','.dbf','.shx','.prj','.cpg'):
        files.append({'path': 'D:/MTR/network/network'+suffix, 'absolute': True,
                      'sha256': sha(network.with_suffix(suffix))})
    for name in ('gdal204.dll','boost_serialization.dll'):
        files.append({'path':'D:/MTR/runtime/'+name, 'absolute': True,
                      'sha256':sha(ROOT/c['paths']['runtime']/name)})
    binding = {'dataset_id': c['frozen_dataset_id'], 'slots': c['slots'],
               'batch': c['batch'], 'files': files,
               'scope': 'PRIVATE_RESEARCH_ROUTING; synthetic M and public resources only; no raw or real-road reference copied'}
    (a.out_dir/'routing_bindings.json').write_text(json.dumps(binding, indent=2), encoding='utf-8')
    with zipfile.ZipFile(a.archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=3) as z:
        for file in sorted(a.out_dir.rglob('*')):
            if file.is_file():
                z.write(file, file.relative_to(a.out_dir))
    print(json.dumps({'archive':str(a.archive), 'bytes':a.archive.stat().st_size,
                      'sha256':sha(a.archive), 'files':len(files), 'dataset_id':c['frozen_dataset_id']}, indent=2))


if __name__ == '__main__':
    main()
