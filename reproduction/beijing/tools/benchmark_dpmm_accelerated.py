"""Accelerator-only replay and measured process scaling; no slow reference runs."""
import argparse
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
import multiprocessing as mp
import os
from pathlib import Path
import pickle
import queue
import sys
import threading
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from preprocess.dataset_contract import validate_dataset,sha
from preprocess.dpmm_population import validation_indices


def output_digest(output):
    import numpy as np
    if output is None:return 'NONE'
    array=np.asarray(output)
    if array.ndim!=2 or array.shape[1]!=2 or not np.isfinite(array).all():
        raise ValueError('Accelerated output has invalid geometry values')
    h=hashlib.sha256()
    h.update(str(array.dtype).encode());h.update(str(array.shape).encode());h.update(array.tobytes())
    return h.hexdigest()


def sample_indices(data,count):
    import numpy as np
    order=sorted(range(len(data)),key=lambda i:(len(data[i]),i))
    result={order[-1],order[-2]}
    for k in np.linspace(0,len(order)-1,count).round().astype(int).tolist()+list(range(len(order))):
        result.add(order[k])
        if len(result)==count:break
    return sorted(result)


def initialize(config,ready,gate):
    from tools.dpmm_worker_bootstrap import initialize as init
    init(config)
    ready.put(os.getpid())
    if not gate.wait(600):raise RuntimeError('Worker start gate timed out')


def process(item):
    from tools.dpmm_worker_bootstrap import process as original
    start=time.perf_counter()
    index,output=original(item)
    return {'index':index-1,'digest':output_digest(output),
            'seconds':time.perf_counter()-start,'pid':os.getpid()}


def admissible(workers,free_bytes,parent_peak,worker_peak,reserve_bytes):
    return workers*worker_peak*1.30+parent_peak*0.25+reserve_bytes<=free_bytes


def run_pool(workers,items,config,reserve_gib):
    import psutil
    started=time.perf_counter();parent=psutil.Process();ctx=mp.get_context('spawn')
    ready=ctx.Queue();gate=ctx.Event();stop=threading.Event();low=threading.Event()
    measure={'minimum_available_gib':psutil.virtual_memory().available/2**30,
             'max_worker_private_gib':0.,'peak_tree_private_gib':0.,'peak_tree_rss_gib':0.,
             'parent_peak_private_gib':0.,'sampling_seconds':.25}
    owned={};cpu_baseline={}
    def monitor():
        while not stop.is_set():
            free=psutil.virtual_memory().available/2**30
            measure['minimum_available_gib']=min(measure['minimum_available_gib'],free)
            rss=private=0.
            for child in [parent,*parent.children(recursive=True)]:
                try:
                    m=child.memory_info();v=getattr(m,'private',m.rss)/2**30
                    rss+=m.rss/2**30;private+=v
                    if child.pid==parent.pid:
                        measure['parent_peak_private_gib']=max(measure['parent_peak_private_gib'],v)
                    elif child.name().lower().startswith('python'):
                        owned[child.pid]=child
                        measure['max_worker_private_gib']=max(measure['max_worker_private_gib'],v)
                except (psutil.NoSuchProcess,psutil.AccessDenied):pass
            measure['peak_tree_private_gib']=max(measure['peak_tree_private_gib'],private)
            measure['peak_tree_rss_gib']=max(measure['peak_tree_rss_gib'],rss)
            if free<reserve_gib:
                low.set();gate.set()
                for child in list(owned.values()):
                    try:child.terminate()
                    except (psutil.NoSuchProcess,psutil.AccessDenied):pass
                break
            stop.wait(.25)
    thread=threading.Thread(target=monitor,daemon=True);thread.start()
    executor=None
    try:
        executor=ProcessPoolExecutor(max_workers=workers,mp_context=ctx,
                  initializer=initialize,initargs=(config,ready,gate))
        futures=[executor.submit(process,item) for item in items]
        pids=set()
        while len(pids)<workers:
            if low.is_set():raise MemoryError('System memory reserve breached during startup')
            if time.perf_counter()-started>600:raise TimeoutError('Pool startup exceeded 600 seconds')
            try:pids.add(ready.get(timeout=1))
            except queue.Empty:
                for f in futures:
                    if f.done():f.result()
        startup=time.perf_counter()-started
        for pid in pids:
            t=psutil.Process(pid).cpu_times();cpu_baseline[pid]=t.user+t.system
        compute_start=time.perf_counter();gate.set()
        results=[f.result() for f in futures]
        compute=time.perf_counter()-compute_start
        cpu=0.
        for pid in pids:
            t=psutil.Process(pid).cpu_times();cpu+=t.user+t.system-cpu_baseline[pid]
        return {'workers':workers,'startup_seconds':startup,'compute_seconds':compute,
                'throughput_records_per_second':len(items)/compute,
                'compute_cpu_seconds':cpu,'mean_busy_cores':cpu/compute,
                'worker_pids':sorted(pids),'results':results,'memory':measure,
                'status':'COMPLETED'}
    finally:
        gate.set()
        if executor is not None:executor.shutdown(wait=True,cancel_futures=True)
        stop.set();thread.join(timeout=2);ready.close()


def main():
    import numpy as np
    import psutil
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('config','adapter','optimizer','public-network','prior-equivalence','out'):
        p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--workers',type=int,nargs='+',required=True)
    p.add_argument('--sample-size',type=int,default=24)
    p.add_argument('--reserve-gib',type=float,default=2.)
    a=p.parse_args()
    if a.out.exists():raise FileExistsError(a.out)
    if a.workers!=sorted(set(a.workers)) or a.workers[0]!=1 or min(a.workers)<1:
        p.error('Sorted unique candidates starting at one are required')
    if a.sample_size<12 or a.reserve_gib<2:p.error('Insufficient sample or memory reserve')
    c=json.loads(a.config.read_text(encoding='utf-8'))
    prepared=Path(c['paths']['prepared']);identity=validate_dataset(prepared,public_network=a.public_network)
    if identity['dataset_id']!=c['frozen_dataset_id']:raise ValueError('Frozen dataset changed')
    source=prepared/'train.pkl';osm=Path(c['paths']['osm'])
    prior=json.loads(a.prior_equivalence.read_text(encoding='utf-8'))
    if not (prior.get('complete') and prior.get('passed') and prior.get('tested_records')==60
            and len(prior['rows'])==60 and all(r['exact_output_equal'] for r in prior['rows'])
            and prior['adapter_sha256']==sha(a.adapter)
            and prior['optimization_sha256']==sha(a.optimizer)
            and prior['public_osm_sha256']==sha(osm)):
        raise ValueError('Existing full sixty equivalence evidence is incomplete or source mismatched')
    with source.open('rb') as stream:data=pickle.load(stream)
    if len(data)!=identity['train_count']:raise ValueError('Wrong train population')
    selected=sample_indices(data,a.sample_size);sixty=validation_indices(data,50,60)
    cfg=dict(bbox=tuple(c['bbox']),osm_cache=str(osm),zone_radius_m=25,
             utm_zone_number=50,utm_zone_letter='S',epsilon=c['epsilon'],
             clean_seed_waypoint_mode='rdp',max_waypoints=None,seed=20260714)
    for key,file in [('ADAPTER',a.adapter.resolve()),('OPTIMIZER',a.optimizer.resolve())]:
        os.environ['DFR_DPMM_'+key]=str(file);os.environ['DFR_DPMM_'+key+'_SHA256']=sha(file)
    a.out.mkdir(parents=True)
    report={'protocol':'accelerated-only-process-validation-v1','slow_reference_executed':False,
            'dataset_id':identity['dataset_id'],'population':'train','input_count':len(data),
            'input_sha256':sha(source),'adapter_sha256':sha(a.adapter),'optimization_sha256':sha(a.optimizer),
            'public_osm_sha256':sha(osm),'public_network_sha256':sha(a.public_network),
            'tool_sha256':sha(Path(__file__)),'public_parameters':cfg,
            'worker_bootstrap_sha256':sha(ROOT/'tools/dpmm_worker_bootstrap.py'),
            'prior_equivalence':{'path':str(a.prior_equivalence.resolve()),'sha256':sha(a.prior_equivalence),
                'scope':'Existing complete full-input sixty semantic equivalence evidence; not relabeled as train or this server'},
            'benchmark_indices':selected,'validation_indices':sixty,
            'logical_processors':psutil.cpu_count(),'physical_processors':psutil.cpu_count(logical=False),
            'candidates':[],'complete':False,'passed':False,
            'limitation':'Accelerator replay, process invariance and binding; not a new slow-reference equivalence proof. Timing uses same fixed sample, not full-corpus runtime guarantee.'}
    def save():
        temp=a.out/'progress.tmp'
        temp.write_text(json.dumps(report,indent=2),encoding='utf-8')
        temp.replace(a.out/'validation.json')
    save();baseline=None;worker_peak=parent_peak=0.
    for workers in a.workers:
        free=psutil.virtual_memory().available
        if workers>psutil.cpu_count() or (worker_peak and not admissible(workers,free,parent_peak,worker_peak,a.reserve_gib*2**30)):
            report['candidates'].append({'workers':workers,'status':'SKIPPED_MEMORY_OR_CPU_LIMIT',
                'available_gib':free/2**30,'observed_worker_peak_gib':worker_peak/2**30})
            save();continue
        print('ACCELERATOR_BENCHMARK_START',workers,flush=True)
        try:run=run_pool(workers,[(i+1,np.asarray(data[i],dtype=float)) for i in selected],cfg,a.reserve_gib)
        except BaseException as error:
            report['candidates'].append({'workers':workers,'status':'FAILED','error':repr(error)})
            save();raise
        signatures={r['index']:r['digest'] for r in run['results']}
        if baseline is None:baseline=signatures
        if signatures!=baseline:raise ValueError('Changing process count changed accelerated outputs')
        run['same_outputs_as_one_worker']=True
        report['candidates'].append(run)
        worker_peak=max(worker_peak,run['memory']['max_worker_private_gib']*2**30)
        parent_peak=max(parent_peak,run['memory']['parent_peak_private_gib']*2**30)
        save();print('ACCELERATOR_BENCHMARK_DONE',workers,run['compute_seconds'],run['memory'],flush=True)
    completed=[r for r in report['candidates'] if r['status']=='COMPLETED']
    eligible=[r for r in completed if r['workers']>=2]
    if not eligible:raise MemoryError('No safe >=2-worker candidate completed; do not start generation')
    best=min(eligible,key=lambda r:r['compute_seconds'])
    report['recommended_workers']=best['workers']
    report['selection']='Lowest measured fixed-sample compute wall time among safely tested candidates; 30% worker-private-memory headroom and >=2GiB system reserve. Not absolute hardware limit.'
    # Validate all sixty, including the ten longest, using only the accelerated code.
    print('ACCELERATOR_SIXTY_START',best['workers'],flush=True)
    final=run_pool(best['workers'],[(i+1,np.asarray(data[i],dtype=float)) for i in sixty],cfg,a.reserve_gib)
    for row in final['results']:
        if row['index'] in baseline and baseline[row['index']]!=row['digest']:
            raise ValueError('Accelerated sixty replay differs from benchmark output')
    if len(final['results'])!=60 or {r['index'] for r in final['results']}!=set(sixty):
        raise ValueError('Incomplete accelerated-only validation')
    report['sixty_record_validation']=final
    report.update(complete=True,passed=True,tested_records=60,target_records=60)
    save();print('ACCELERATOR_ONLY_VALIDATED',best['workers'],flush=True)


if __name__=='__main__':main()
