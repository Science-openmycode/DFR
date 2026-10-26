"""Bind the preserved algorithm-level DFR ablation to the prepared road population."""
import argparse
import importlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

from preprocess.dataset_contract import validate_dataset, sha

ROOT=Path(__file__).resolve().parent


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',type=Path,required=True)
    p.add_argument('--out',type=Path)
    p.add_argument('--check-only',action='store_true')
    a=p.parse_args()
    c=json.loads(a.config.read_text(encoding='utf-8'))
    def path(key):return (ROOT/c['paths'][key]).resolve()
    identity=validate_dataset(path('prepared'))
    if identity['dataset_id']!=c['frozen_dataset_id']:raise ValueError('Wrong frozen dataset')
    canonical=path('prepared')/'canonical_manifest.json'
    if sha(path('network'))!=json.loads(canonical.read_text(encoding='utf-8'))['network_sha256']:
        raise ValueError('Public graph changed')
    sys.path.insert(0,str(path('legacy')/'evaluation'))
    experiment=importlib.import_module('run_ablation_experiment')
    from experiment_contract import validate_road_population
    # The old validator expects raw GPS -> common-match provenance. This input
    # is instead the frozen, already preprocessed road dataset. Validate that
    # actual contract, without forging an old matcher manifest.
    def frozen_reference(matched,source,cache,population,network):
        if (Path(matched).resolve()!=path('real_routes') or Path(source).resolve()!=path('real')
                or Path(network).resolve()!=path('network') or population!='full-corpus'):
            raise ValueError('Ablation inputs differ from the verified frozen population')
        population_record=validate_road_population(experiment.load_pickle(matched),cache,population)
        if population_record['source_slots']!=identity['count']:
            raise ValueError('Ablation population count differs')
        return dict(**population_record,dataset_id=identity['dataset_id'],
                    source_sha256=sha(source),matched_sha256=sha(matched),
                    canonical_manifest_sha256=sha(canonical),
                    classification='PRIVATE_FROZEN_ROAD_DATASET_AUDIT_NOT_FOR_RELEASE')
    experiment.validate_real_reference=frozen_reference
    out=(a.out or path('output')/c['batch']/'ablation/MTR-DFR').resolve()
    args=SimpleNamespace(real_routes=path('real_routes'),real_source=path('real'),
                         edge_cache=path('metric_cache'),network=path('network'),
                         population='full-corpus',variants=None,length_aware=True,
                         epsilon_total=str(c['epsilon']),reuse_generated=False,
                         public_slot_count=c['slots'],seed=c['seed'])
    frozen_reference(args.real_routes,args.real_source,experiment.load_pickle(args.edge_cache),
                     args.population,args.network)
    if a.check_only:
        print('VERIFIED_FROZEN_DFR_ABLATION_INPUT',identity['count']);return
    experiment.dfr(args,out)
    record=json.loads((out/'manifest.json').read_text(encoding='utf-8'))
    record.update(adapter_sha256=sha(Path(__file__)),
                  original_experiment_sha256=sha(Path(experiment.__file__)),
                  command=[sys.executable,*sys.argv])
    (out/'manifest.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
    print('DONE_DFR_ABLATION',out)


if __name__=='__main__':main()
