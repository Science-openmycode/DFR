"""Run the validated DPMM accelerator on the current frozen dataset, not old inputs."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

from preprocess.dataset_contract import validate_dataset, sha
from preprocess.dpmm_population import population_input
from tools.dpmm_worker_bootstrap import initialize, process

ROOT=Path(__file__).resolve().parent


def prior_evidence_path(validation, prior):
    """Relocate evidence without rewriting its signed/hash-bound content."""
    validation=Path(validation).resolve()
    locations=validation.with_suffix('.locations.json')
    if not locations.exists():
        path=Path(prior['path'])
        return path if path.is_absolute() else validation.parent/path
    mapping=json.loads(locations.read_text(encoding='utf-8'))
    relative=Path(mapping['sha256_locations'][prior['sha256']])
    target=(validation.parent/relative).resolve()
    if relative.is_absolute() or not target.is_relative_to(validation.parent):
        raise ValueError('Evidence location must remain inside evidence directory')
    return target


def verify_equivalence(validation,adapter,optimizer,source,osm):
    v=json.loads(Path(validation).read_text(encoding='utf-8'))
    if not (v.get('passed') and v.get('complete') and v.get('tested_records',0)==60
            and v['tested_records']==v['target_records']==len(v['rows'])
            and all(r['exact_output_equal'] for r in v['rows'])
            and v.get('public_path_comparisons')
            and all(r['paths_equal'] for r in v['public_path_comparisons'])):
        raise ValueError('New-input equivalence validation is incomplete or failed')
    for file,key in [(adapter,'adapter_sha256'),(optimizer,'optimization_sha256'),
                     (source,'real_input_sha256'),(osm,'public_osm_sha256')]:
        if sha(file)!=v[key]:raise ValueError('Equivalence input changed: '+key)
    return v


def verify_accelerated_validation(validation,adapter,optimizer,source,osm,workers):
    v=json.loads(Path(validation).read_text(encoding='utf-8'))
    if not (v.get('protocol')=='accelerated-only-process-validation-v1'
            and v.get('passed') and v.get('complete') and v.get('tested_records')==60
            and v.get('target_records')==60 and v.get('slow_reference_executed') is False):
        raise ValueError('Accelerated-only validation incomplete or wrong protocol')
    rows=v.get('sixty_record_validation',{}).get('results',[])
    if len(rows)!=60 or len({r['index'] for r in rows})!=60 or {r['index'] for r in rows}!=set(v['validation_indices']):
        raise ValueError('Accelerated sixty sample is incomplete')
    completed=[r for r in v['candidates'] if r['status']=='COMPLETED']
    if not completed or not all(r.get('same_outputs_as_one_worker') for r in completed):
        raise ValueError('Parallel accelerated outputs not verified')
    if workers!=v['recommended_workers'] or workers not in {r['workers'] for r in completed}:
        raise ValueError('Worker count was not the measured selected candidate')
    for file,key in [(adapter,'adapter_sha256'),(optimizer,'optimization_sha256'),
                     (source,'input_sha256'),(osm,'public_osm_sha256'),
                     (ROOT/'tools/dpmm_worker_bootstrap.py','worker_bootstrap_sha256')]:
        if sha(file)!=v[key]:raise ValueError('Accelerated validation source changed: '+key)
    prior=v['prior_equivalence']
    if sha(prior_evidence_path(validation,prior))!=prior['sha256']:raise ValueError('Existing equivalence evidence changed')
    return v


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',type=Path,required=True)
    p.add_argument('--adapter',type=Path,required=True)
    p.add_argument('--optimizer',type=Path,required=True)
    p.add_argument('--validation',type=Path,required=True)
    p.add_argument('--out',type=Path)
    p.add_argument('--workers',type=int,default=2,
                   help='At least two workers: preserves the reference per-record deterministic seeds')
    p.add_argument('--checkpoint-every',type=int,default=100)
    p.add_argument('--check-only',action='store_true')
    p.add_argument('--public-network',type=Path,help='Explicit migrated graph path; all frozen graph hashes remain required')
    p.add_argument('--split',choices=('full','train'),default='full')
    p.add_argument('--validation-protocol',choices=('slow-equivalence','accelerated-only'),default='slow-equivalence',
                   help='Explicit user-authorized alternative; never pretend accelerator replay is a new slow-reference proof')
    p.add_argument('--memory-reserve-gib',type=float,default=0,
                   help='Optional runtime system memory floor; terminates only this invocation own workers if breached')
    a=p.parse_args()
    if a.workers<2 or a.checkpoint_every<1 or a.memory_reserve_gib<0:
        p.error('Require >=2 workers and a positive checkpoint interval')
    c=json.loads(a.config.read_text(encoding='utf-8'))
    def path(key):return (ROOT/c['paths'][key]).resolve()
    if a.public_network is not None and a.public_network.resolve()!=path('network'):
        raise ValueError('Migrated graph path must match configuration')
    identity=validate_dataset(path('prepared'),public_network=a.public_network)
    if identity['dataset_id']!=c['frozen_dataset_id']:raise ValueError('Wrong frozen dataset')
    adapter=a.adapter.resolve();optimizer=a.optimizer.resolve()
    source,input_count,source_sha=population_input(path('prepared'),identity,a.split)
    if sha(source)!=source_sha:raise ValueError('Frozen selected population changed')
    if a.validation_protocol=='accelerated-only':
        v=verify_accelerated_validation(a.validation,adapter,optimizer,source,path('osm'),a.workers)
    else:
        v=verify_equivalence(a.validation,adapter,optimizer,source,path('osm'))
    if v.get('input_count')!=input_count or v.get('population','full')!=a.split:
        raise ValueError('Validation belongs to another population')
    parameters=v['public_parameters']
    if (parameters['epsilon']!=c['epsilon'] or tuple(parameters['bbox'])!=tuple(c['bbox'])
            or parameters['zone_radius_m']!=25 or parameters['utm_zone_number']!=50
            or parameters['utm_zone_letter']!='S'):
        raise ValueError('Public parameters differ from the validated run')
    out=(a.out or path('output')/c['batch']/('native_train/DPMM' if a.split=='train' else 'native/DPMM')).resolve()
    if out.exists():raise FileExistsError(out)
    spec=importlib.util.spec_from_file_location('dfr_dpmm_parent_reference',adapter)
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    optimizer_spec=importlib.util.spec_from_file_location('dfr_dpmm_preflight_optimizer',optimizer)
    optimizer_module=importlib.util.module_from_spec(optimizer_spec);optimizer_spec.loader.exec_module(optimizer_module)
    if not callable(getattr(optimizer_module,'install_semantic_path_cache',None)):
        raise ValueError('Validated optimizer entrypoint missing')
    print('VALIDATED_NEW_INPUT_DPMM',input_count,a.workers,flush=True)
    if a.check_only:return
    out.mkdir(parents=True)
    for key,file in [('ADAPTER',adapter),('OPTIMIZER',optimizer)]:
        os.environ['DFR_DPMM_'+key]=str(file)
        os.environ['DFR_DPMM_'+key+'_SHA256']=sha(file)
    os.environ['PYTHONPATH']=str(ROOT)+os.pathsep+os.environ.get('PYTHONPATH','')
    os.environ['OMP_NUM_THREADS']='1'
    os.environ['OPENBLAS_NUM_THREADS']='1'
    # Only the process initialization boundary is rebound. Each worker calls the
    # original record routine with its original derived seed and validated cache.
    module._init_worker=initialize
    module._worker_process=process
    sys.argv=[str(adapter),'--input-pkl',str(source),'--osm-cache',str(path('osm')),
              '--bbox',*map(str,c['bbox']),'--epsilon',str(c['epsilon']),'--seed','20260714',
              '--zone-radius-m','25','--utm-zone-number','50','--utm-zone-letter','S',
              '--clean-seed-waypoint-mode','rdp','--workers',str(a.workers),
              '--checkpoint-every',str(a.checkpoint_every),'--out-dir',str(out),'--tag','dpmm']
    record=dict(status='RUNNING',dataset_id=identity['dataset_id'],input_count=input_count,
                input_sha256=sha(source),population=a.split,osm_sha256=sha(path('osm')),
                adapter_sha256=sha(adapter),optimizer_sha256=sha(optimizer),
                validation_sha256=sha(a.validation),workers=a.workers,command=sys.argv,
                validation_protocol=a.validation_protocol,
                privacy_scope='Official per-input link-level sanitization, not central trajectory DP',
                rematched=False,protocol='Unchanged record routine; exact-target cached path acceleration')
    started=time.perf_counter()
    guard=None
    if a.memory_reserve_gib:
        from tools.owned_worker_memory_guard import OwnedWorkerMemoryGuard
        guard=OwnedWorkerMemoryGuard(a.memory_reserve_gib,out/'runtime_memory.json')
        guard.start()
    try:
        module.main()
        if guard is not None and guard.exceeded.is_set():
            raise MemoryError('Runtime memory reserve breached; do not use partial release')
        result=json.loads((out/'dpmm.json').read_text(encoding='utf-8'))
        if result['input_count']!=input_count or len(result['released_input_indices'])!=result['output_count']:
            raise ValueError('Incomplete native slot ledger')
        result['official_code_parameters']['path_algorithm']='Validated NetworkX Dijkstra-compatible target-limited path cache'
        result['official_code_parameters']['public_path_cache']='Identical target paths and candidate enumeration to frozen adapter; not an upstream A* tie-identity claim'
        (out/'dpmm.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        record.update(status='DONE',outputs={name:sha(out/name) for name in ('dpmm.pkl','dpmm.json')})
    except BaseException as error:
        record.update(status='FAILED',error=str(error));raise
    finally:
        if guard is not None:
            guard.stop();record['runtime_memory_guard']=guard.stats
        record['seconds']=time.perf_counter()-started
        (out/'new_dataset_execution.json').write_text(json.dumps(record,indent=2),encoding='utf-8')


if __name__=='__main__':main()
