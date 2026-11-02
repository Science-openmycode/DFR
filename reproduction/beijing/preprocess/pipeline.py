"""Configuration-driven preprocessing; never launches a research model."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
from .dataset_contract import sha

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',type=Path,required=True)
    a=p.parse_args();config_path=a.config.resolve();c=json.loads(config_path.read_text(encoding='utf-8'))
    if c.get('schema')!='raw-road-preprocessing-v1':raise ValueError('Unknown preprocessing schema')
    def path(key):return (config_path.parent/c[key]).resolve()
    out=path('output')
    if out.exists():raise FileExistsError('Choose a new preprocessing output; no partial data are reused: '+str(out))
    adapter=c.get('adapter')
    if adapter not in ('start_porto_archive','reviewed_road_corpus','geolife_reviewed'):raise ValueError('Unsupported raw adapter')
    graph=path('public_graph') if 'public_graph' in c else out/'public_graph'
    metric=path('metric_cache') if 'metric_cache' in c else None
    if metric is not None and not metric.is_file():raise FileNotFoundError(metric)
    out.mkdir(parents=True)
    journal=out/'commands.jsonl'
    def run(name,args):
        command=[sys.executable,'-X','utf8',*map(str,args)]
        started=time.perf_counter()
        with journal.open('a',encoding='utf-8') as f:f.write(json.dumps(dict(stage=name,event='start',argv=command,cwd=str(ROOT)))+'\n')
        result=subprocess.run(command,cwd=ROOT)
        with journal.open('a',encoding='utf-8') as f:f.write(json.dumps(dict(stage=name,event='finish',returncode=result.returncode,seconds=time.perf_counter()-started))+'\n')
        if result.returncode:raise RuntimeError('Preprocessing stopped at '+name+'; evidence retained in '+str(out))
    if adapter=='start_porto_archive':
        archive=path('source')
        if 'public_graph' not in c:
            run('export_author_graph',['preprocess/start_porto_graph.py','--archive',archive,
                '--archive-sha256',sha(archive),'--out',graph,'--directed-carrier','--segment-edges'])
        g=json.loads((graph/'manifest.json').read_text(encoding='utf-8'))
        for name,digest in g['outputs'].items():
            if Path(name).name!=name or sha(graph/name)!=digest:raise ValueError('Public graph changed: '+name)
        if metric is not None:
            support=json.loads((metric.parent/'resources_manifest.json').read_text(encoding='utf-8'))
            if support['network_sha256']!=sha(graph/'network.shp') or support['outputs']['metric_cache.pkl.gz']!=sha(metric):
                raise ValueError('Metric support belongs to another public graph')
        if g['dataset']!='porto' or g['archive_sha256']!=sha(archive):raise ValueError('Author graph/source archive mismatch')
        run('raw_mapping',['preprocess/start_porto.py','--archive',archive,'--archive-sha256',sha(archive),
                         '--public-manifest',graph/'manifest.json','--public-manifest-sha256',sha(graph/'manifest.json'),'--out',out/'mapping'])
        run('freeze',['preprocess/start_porto_freeze.py','--archive',archive,'--audit',out/'mapping',
                     '--audit-sha256',sha(out/'mapping/manifest.json'),'--graph',graph,'--out',out/'frozen',
                     '--seed',str(c.get('seed',20260713))])
        run('source_verification',['preprocess/verify_start_porto.py','--dataset',out/'frozen','--archive',archive,
                                 '--graph',graph,'--out',out/'source_verification.json'])
        prepared=out/'frozen';dataset='porto'
        extras={'time_endpoints':str(prepared/'source_lineage.csv')}
    else:
        g=None
        if not (graph/'network.shp').is_file():raise FileNotFoundError('Reviewed GPS adapter requires its public graph')
        # Existing reviewed-GPS preparation stays unchanged, including its
        # explicit subset acceptance. No implicit rematching or new population.
        if c.get('accept_reviewed_subset') is not True:raise ValueError('Explicit reviewed population acceptance required')
        source=path('source')
        if adapter=='geolife_reviewed':
            if c['dataset']!='beijing' or c['bbox']!=[39.75,40.15,116.1,116.65]:
                raise ValueError('Historical GeoLife reviewed adapter requires its original public bounds')
            run('read_raw_geolife',['legacy/commands/prepare_geolife_beijing.py','--source-dir',source,
                '--out',out/'raw_coordinates.pkl','--seed',str(c.get('seed',20260713))])
            run('recover_observed_times',['preprocess/recover_raw_metadata.py','--source-dir',source,
                '--coordinates',out/'raw_coordinates.pkl','--out',out/'raw_metadata'])
            run('endpoint_metadata',['preprocess/prepare_mtnet_time_binding.py','--source-dir',source,
                '--reference',out/'raw_coordinates.pkl','--out',out/'time_binding.json'])
            source=out/'raw_coordinates.pkl'
            timestamps=out/'raw_metadata/timestamps_day_serial.pkl.gz';bindings=out/'raw_metadata/source_binding.csv'
        else:
            timestamps=path('timestamps');bindings=path('timestamp_bindings')
        run('freeze_reviewed',['preprocess/road_dataset.py','--source',source,'--network',graph/'network.shp',
            '--matcher-module',path('matcher_module'),'--timestamps',timestamps,'--timestamp-bindings',bindings,
            '--review-from',path('review'),'--accept-reviewed-subset','yes','--out',out/'road_review',
            '--dataset',c['dataset'],'--bbox',*map(str,c['bbox']),'--seed',str(c.get('seed',20260713))])
        prepared=out/'road_review/dataset';dataset=c['dataset'];extras={}
        if adapter=='geolife_reviewed':extras=dict(mtnet_time_binding=str(out/'time_binding.json'),mtnet_raw_reference=str(source))
    public=dict(prepared=str(prepared),network=str(graph/'network.shp'),**extras)
    if metric is not None:public['metric_cache']=str(metric)
    candidates=[('osm',graph/'public_ways.pkl')]
    if metric is not None:candidates.append(('edge_cache',metric.parent/'edge_cache.pkl.gz'))
    for key, candidate in candidates:
        if candidate.is_file():public[key]=str(candidate)
    bundle=dict(schema='road-experiment-bundle-v1',dataset=dataset,paths=public)
    bundle['bbox']=g['bbox'] if g else c['bbox']
    if g:bundle['routing_crs']={'input_srs':'EPSG:4326','network_srs':g['projected_crs'],'tracks_srs':g['projected_crs']}
    (out/'prepared.dataset.json').write_text(json.dumps(bundle,indent=2),encoding='utf-8')
    (out/'export.config.json').write_text(json.dumps({'dataset_bundle':'prepared.dataset.json'}),encoding='utf-8')
    run('standard_export',['preprocess/standardize_dataset.py','--config',out/'export.config.json','--out',out/'standard'])
    run('standard_verification',['preprocess/check_standard_package.py','--package',out/'standard','--out',out/'standard_verification.json'])
    final=dict(status='RAW_TO_STANDARD_COMPLETE',dataset=dataset,dataset_bundle=str(out/'standard/dataset.json'),
               config_sha256=sha(config_path),commands=str(journal),scope='Preprocessing only; not all routing resources or model training')
    (out/'pipeline_result.json').write_text(json.dumps(final,indent=2),encoding='utf-8')
    print(json.dumps(final),flush=True)
