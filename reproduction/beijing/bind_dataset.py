"""Bind a frozen road corpus to a new experiment config; no generation or scoring."""
import argparse
import json
import hashlib
from pathlib import Path
from preprocess.dataset_contract import validate_dataset

ROOT=Path(__file__).resolve().parent

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dataset',type=Path,required=True)
    p.add_argument('--osm-cache',type=Path,required=True,help='Public OSM source corresponding to the frozen graph')
    p.add_argument('--out',type=Path,required=True,help='New JSON experiment configuration')
    p.add_argument('--batch',required=True)
    p.add_argument('--runtime',type=Path,required=True,help='Installed matching DLL directory')
    p.add_argument('--fmm',type=Path,default=ROOT/'resources/fmm/fmm.exe')
    p.add_argument('--stmatch',type=Path,default=ROOT/'resources/stmatch/stmatch.exe')
    p.add_argument('--mm2',type=Path,help='Optional MM2 executable; absent means unbound, not ready')
    p.add_argument('--mm2-network',type=Path,help='Optional MM2 public network directory')
    a=p.parse_args()
    if a.out.exists():p.error('Existing configuration is not overwritten')
    if Path(a.batch).name!=a.batch:p.error('Batch must be a single folder name')
    if not a.osm_cache.is_file():p.error('Missing public OSM cache')
    if not a.runtime.is_dir():p.error('Missing runtime directory')
    if not a.fmm.is_file() or not a.stmatch.is_file():p.error('Missing frozen matcher executable')
    if bool(a.mm2)!=bool(a.mm2_network):p.error('Provide both MM2 executable and network, or neither')
    prepared=a.dataset.resolve();identity=validate_dataset(prepared)
    meta=json.loads((prepared/'canonical_manifest.json').read_text(encoding='utf-8'))
    config=json.loads((ROOT/'configs/beijing.yaml').read_text(encoding='utf-8'))
    config.update(batch=a.batch,dataset_policy='frozen-road-only',frozen_dataset_id=identity['dataset_id'],
        slots=identity['count'],train_slots=identity['train_count'],test_slots=identity['test_count'],
        population='full-corpus',population_status='APPROVED_RELIABLY_ROAD_RECONSTRUCTABLE_COHORT',
        road_reference_status='FROZEN_PENDING_PUBLIC_RESOURCES',public_resources_status='PENDING',
        preprocessing_review=str(prepared.parent/'selection_review.json'))
    config['bbox']=json.loads((prepared/'bbox.json').read_text(encoding='utf-8'))['bbox']
    config['paths'].update(prepared=str(prepared),real=str(prepared/'trajectories.pkl'),
        real_routes=str(prepared/'road_records.pkl.gz'),metric_real_routes=str(prepared/'road_records.pkl.gz'),
        train=str(prepared/'train.pkl'),test=str(prepared/'test.pkl'),network=meta['network'],metric_network=meta['network'],
        osm=str(a.osm_cache.resolve()),edge_cache=str(prepared/'public_resources/edge_cache.pkl.gz'),
        metric_cache=str(prepared/'public_resources/metric_cache.pkl.gz'),source_cache=str(prepared/'public_resources/metric_cache.pkl.gz'),
        ubodt=str(prepared/'public_resources/ubodt.txt'),split_audit=str(prepared/'public_resources/split_audit.json'))
    config['paths'].update(runtime=str(a.runtime.resolve()),fmm=str(a.fmm.resolve()),stmatch=str(a.stmatch.resolve()))
    from experiments.separate import validate_matcher_binding
    for router in ('FMM','STMatch'):validate_matcher_binding(config,ROOT,router)
    config['fmm_resources_status']='UBODT_PENDING'
    config['mm2_resources_status']='UNBOUND'
    if a.mm2:
        if not a.mm2.is_file() or not a.mm2_network.is_dir():p.error('Missing MM2 resources')
        expected={r['path']:r['sha256'] for r in json.loads((ROOT/'external_assets.json').read_text(encoding='utf-8'))['files']}
        def digest(path):
            with path.open('rb') as handle:return hashlib.file_digest(handle,'sha256').hexdigest()
        bindings={'resources/mm2/map_matching_2.exe':a.mm2}
        bindings.update({key:a.mm2_network/Path(key).name for key in expected if key.startswith('resources/mm2/network/')})
        bindings.update({'resources/network/network'+suffix:Path(meta['network']).with_suffix(suffix) for suffix in ('.shp','.shx','.dbf','.prj','.cpg')})
        for key,file in bindings.items():
            if digest(file)!=expected[key]:raise ValueError('MM2/public graph binding mismatch: '+key)
        config['paths'].update(mm2=str(a.mm2.resolve()),mm2_network=str(a.mm2_network.resolve()))
        config['mm2_resources_status']='READY'
    # Never carry prior full-corpus coordinates or train-only lineage into a new dataset batch.
    config['routing_inputs']={};config['releases']={}
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(configuration=str(a.out.resolve()),**identity,public_resources_status='PENDING'),indent=2))

if __name__=='__main__':main()
