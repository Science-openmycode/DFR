"""Report all missing dependencies and resources together, without starting experiments."""
import argparse
import hashlib
import importlib
import importlib.metadata
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parent
def matcher_dependencies(paths):
    missing=[]
    if 'mm2_network' in paths:
        mapping=(ROOT/paths['mm2_network']).parent/'public_graph/inputs/public_edge_nodes.json'
        if not mapping.is_file():missing.append(f'missing MM2 public node mapping: {mapping}')
    if sys.platform=='win32':
        for key in ('fmm','stmatch'):
            if key in paths:
                library=(ROOT/paths[key]).parent/'FMMLIB.dll'
                if not library.is_file():missing.append(f'missing {key} runtime: {library}')
        if any(key in paths for key in ('fmm','stmatch')):
            for name in ('gdal204.dll','boost_serialization.dll'):
                library=ROOT/paths.get('runtime','resources/runtime')/name
                if not library.is_file():missing.append(f'missing matcher runtime: {library}')
    return missing
MODULES={'numpy':'numpy','pandas':'pandas','scipy':'scipy','networkx':'networkx','shapely':'shapely','geopandas':'geopandas','pyogrio':'pyogrio','sklearn':'scikit-learn','matplotlib':'matplotlib','utm':'utm','rdp':'rdp','cvxpy':'cvxpy'}
MODULES.update({'requests':'requests','osmnx':'osmnx','paramiko':'paramiko','psutil':'psutil','shapefile':'pyshp'})
def check(config,verify_hashes=True):
    errors=[];versions={};c=json.loads(config.read_text(encoding='utf-8'))
    errors.extend(matcher_dependencies(c['paths']))
    for module,package in MODULES.items():
        try:importlib.import_module(module);versions[package]=importlib.metadata.version(package)
        except Exception as e:errors.append(f'dependency {module}: {e}')
    for key,value in c['paths'].items():
        p=Path(value)
        if p.is_absolute() or '..' in p.parts:errors.append(f'nonportable path {key}: {value}')
        if key!='output' and not (ROOT/p).exists():errors.append(f'missing {key}: {value}')
    try:
        from preprocess.dataset_contract import validate_dataset
        ident=validate_dataset(ROOT/c['paths']['prepared'],ROOT/c['paths']['network'])
        if ident['dataset_id']!=c['frozen_dataset_id']:errors.append('dataset identity mismatch')
    except Exception as e:errors.append(f'dataset: {e}')
    if verify_hashes:
        for binding in ('resources/binding.json','resources/mm2/binding.json','resources/mtnet/binding.json'):
            try:
                b=json.loads((ROOT/binding).read_text())
                for rel,expected in b['files'].items():
                    with (ROOT/rel).open('rb') as f:actual=hashlib.file_digest(f,'sha256').hexdigest()
                    if actual!=expected:errors.append('hash mismatch: '+rel)
            except Exception as e:errors.append(f'{binding}: {e}')
    try:
        from algorithms.measurements.frozen_adapter import verify_sources, load_module
        verify_sources()
        for method in ('sprt','dpstd'):
            try:load_module(method)
            except Exception as e:errors.append(f'baseline import {method}: {e}')
    except Exception as e:errors.append(f'frozen baseline sources: {e}')
    return {'passed':not errors,'errors':errors,'python':sys.version,'versions':versions,'scope':'resources/imports only; not an experiment success claim'}
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',type=Path,default=ROOT/'configs/beijing.json');p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    if a.out.exists():raise FileExistsError(a.out)
    result=check(a.config);a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result));raise SystemExit(0 if result['passed'] else 2)
if __name__=='__main__':main()
