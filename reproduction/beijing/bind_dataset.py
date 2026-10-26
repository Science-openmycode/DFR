"""Bind a frozen road corpus to a new experiment config; no generation or scoring."""
import argparse
import json
from pathlib import Path
from preprocess.dataset_contract import validate_dataset

ROOT=Path(__file__).resolve().parent

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dataset',type=Path,required=True)
    p.add_argument('--osm-cache',type=Path,required=True,help='Public OSM source corresponding to the frozen graph')
    p.add_argument('--out',type=Path,required=True,help='New JSON experiment configuration')
    p.add_argument('--batch',required=True)
    a=p.parse_args()
    if a.out.exists():p.error('Existing configuration is not overwritten')
    if Path(a.batch).name!=a.batch:p.error('Batch must be a single folder name')
    if not a.osm_cache.is_file():p.error('Missing public OSM cache')
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
    # Never carry prior full-corpus coordinates or train-only lineage into a new dataset batch.
    config['routing_inputs']={};config['releases']={}
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(configuration=str(a.out.resolve()),**identity,public_resources_status='PENDING'),indent=2))

if __name__=='__main__':main()
