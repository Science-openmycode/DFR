"""Select a dataset once for the shared README preparation workflow.

This module prepares inputs and command documents, never runs a research model.
Direct historical entrypoints do not consult this selector and remain usable.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from .dataset_contract import sha, validate_dataset
from .dataset_config import load_config

ROOT=Path(__file__).resolve().parents[1]
DEFAULT='configs/datasets/beijing.workflow.json'


def selection(root=ROOT, environ=None):
    environ=os.environ if environ is None else environ
    filename=(root/environ.get('DFR_DATASET_CONFIG',DEFAULT)).resolve()
    config=json.loads(filename.read_text(encoding='utf-8-sig'))
    if config.get('schema')!='readme-dataset-workflow-v1':raise ValueError('Unsupported dataset selection schema')
    if not re.fullmatch(r'[a-z][a-z0-9_-]*',config.get('dataset','')):raise ValueError('Invalid dataset name')
    if config.get('adapter') not in ('geolife','start_porto_archive','standard_bundle'):raise ValueError('Unsupported input adapter')
    if config.get('adapter')=='start_porto_archive' and config['dataset']!='porto':raise ValueError('START Porto adapter requires Porto data')
    return filename,config


class Workflow:
    def __init__(self,root=ROOT,environ=None):
        self.root=Path(root).resolve();self.profile,self.c=selection(self.root,environ)
        self.adapter=self.c['adapter'];self.control=self.root/'data/workflow'
        self.raw=self.root/'data/raw';self.public=self.root/'data/public'
        self.accepted=self.root/'data/road_accepted'
        self.standard=(self.path('source') if self.adapter=='standard_bundle' else self.accepted/'standard')

    def path(self,key):return (self.root/self.c[key]).resolve()

    def guard(self):
        self.control.mkdir(parents=True,exist_ok=True)
        lock=self.control/'selection.json'
        identity=dict(dataset=self.c['dataset'],profile=str(self.profile),profile_sha256=sha(self.profile))
        if lock.exists():
            if json.loads(lock.read_text())!=identity:
                raise ValueError('This checkout already has another dataset selection. Use a separate clean checkout; old results are not overwritten.')
        else:lock.write_text(json.dumps(identity,indent=2),encoding='utf-8')

    def invoke(self,label,args):
        argv=[sys.executable,'-X','utf8',*map(str,args)]
        journal=self.control/'commands.jsonl';start=time.monotonic()
        with journal.open('a',encoding='utf-8') as f:f.write(json.dumps(dict(event='STARTED',stage=label,argv=argv,cwd=str(self.root)))+'\n')
        rc=subprocess.run(argv,cwd=self.root).returncode
        with journal.open('a',encoding='utf-8') as f:f.write(json.dumps(dict(event='FINISHED' if rc==0 else 'FAILED',stage=label,returncode=rc,seconds=time.monotonic()-start))+'\n')
        if rc:raise SystemExit(rc)

    def run(self,stage,review_only=False,accept=False,dry_run=False):
        if dry_run:
            print(json.dumps(dict(dataset=self.c['dataset'],adapter=self.adapter,stage=stage,profile=str(self.profile),standard=str(self.standard),review_only=review_only,accept=accept),indent=2));return
        self.guard()
        name=stage+('_review' if review_only else '_accept' if accept else '')
        receipt=self.control/(name+'.json')
        if receipt.exists():
            old=json.loads(receipt.read_text())
            for filename,digest in old['outputs'].items():
                if sha(Path(filename))!=digest:raise ValueError('Previously prepared output changed: '+filename)
            print('ALREADY_VERIFIED',name,self.c['dataset']);return
        started=time.monotonic()
        outputs=getattr(self,stage)(review_only=review_only,accept=accept)
        receipt.write_text(json.dumps(dict(status='COMPLETE',dataset=self.c['dataset'],stage=name,seconds=time.monotonic()-started,outputs={str(p.resolve()):sha(p) for p in outputs}),indent=2),encoding='utf-8')
        print('PREPARATION_COMPLETE',name,self.c['dataset'])

    def fetch(self,**kwargs):
        if self.adapter=='geolife':
            archive=self.path('archive');source=self.path('source')
            if not source.is_dir():
                self.invoke('fetch_geolife',['preprocess/fetch_geolife.py','--archive',archive,'--extract-to',self.path('extract_to')])
            if not source.is_dir():raise FileNotFoundError(source)
            return [archive] if archive.is_file() else [self.profile]
        source=self.path('source')
        if self.adapter=='standard_bundle':
            if not (source/'dataset.json').is_file():raise FileNotFoundError(source/'dataset.json')
            return [source/'dataset.json']
        if not source.is_file():raise FileNotFoundError('Place the original START Porto_data.zip at '+str(source)+' or change only source in the selected profile')
        return [source]

    def public_graph(self,**kwargs):
        if self.adapter=='standard_bundle':return [self.standard/'dataset.json']
        if self.adapter=='start_porto_archive':
            archive=self.path('source')
            self.invoke('export_start_public_graph',['preprocess/start_porto_graph.py','--archive',archive,'--archive-sha256',sha(archive),'--out',self.public,'--directed-carrier','--segment-edges'])
            return [self.public/'manifest.json',self.public/'network.shp']
        if self.c.get('public_source'):
            source=self.path('public_source');self.public.mkdir(parents=True,exist_ok=False)
            (self.public/'network').mkdir();(self.public/'osm').mkdir()
            for suffix in ('.shp','.shx','.dbf','.prj','.cpg'):
                p=source.with_suffix(suffix)
                if p.exists():shutil.copy2(p,self.public/'network'/('network'+suffix))
            shutil.copy2(self.path('osm_source'),self.public/'osm/osm_cache_beijing_drivable_full.pkl')
        else:self.invoke('install_public_graph',['preprocess/install_public_roads.py','--out',self.public])
        return [self.public/'network/network.shp',self.public/'osm/osm_cache_beijing_drivable_full.pkl']

    def read(self,**kwargs):
        if self.adapter=='standard_bundle':return [self.standard/'dataset.json']
        self.raw.mkdir(parents=True,exist_ok=True)
        if self.adapter=='start_porto_archive':
            archive=self.path('source');manifest=self.public/'manifest.json'
            self.invoke('read_start_trajectories',['preprocess/start_porto.py','--archive',archive,'--archive-sha256',sha(archive),'--public-manifest',manifest,'--public-manifest-sha256',sha(manifest),'--out',self.raw/'start_mapping'])
            return [self.raw/'start_mapping/manifest.json']
        self.invoke('read_geolife',['legacy/commands/prepare_geolife_beijing.py','--source-dir',self.path('source'),'--out',self.raw/'real_full_frozen.pkl','--seed',self.c.get('seed',20260713),'--train-fraction','0.8','--bbox',*self.c['bbox']])
        self.invoke('read_observed_times',['preprocess/recover_raw_metadata.py','--source-dir',self.path('source'),'--coordinates',self.raw/'real_full_frozen.pkl','--out',self.raw/'metadata'])
        self.invoke('read_endpoint_times',['preprocess/prepare_mtnet_time_binding.py','--source-dir',self.path('source'),'--reference',self.raw/'real_full_frozen.pkl','--out',self.raw/'mtnet_time_binding.json'])
        return [self.raw/'real_full_frozen.pkl',self.raw/'mtnet_time_binding.json',self.raw/'metadata/source_binding.csv']

    def roads(self,review_only=False,accept=False):
        if self.adapter=='standard_bundle':
            if not review_only and not accept:raise ValueError('Choose --review-only or --accept-reviewed-subset yes')
            check=self.control/'standard_input_verification.json'
            if not check.exists():self.invoke('verify_standard_input',['preprocess/check_standard_package.py','--package',self.standard,'--out',check])
            return [self.standard/'dataset.json',check]
        if not review_only and not accept:raise ValueError('Read the review before explicitly accepting it')
        if self.adapter=='start_porto_archive':
            mapping=self.raw/'start_mapping';manifest=mapping/'manifest.json'
            if review_only:
                print(manifest.read_text(encoding='utf-8'));return [manifest]
            prepared=self.accepted/'dataset';self.accepted.mkdir(parents=True,exist_ok=True)
            self.invoke('freeze_start',['preprocess/start_porto_freeze.py','--archive',self.path('source'),'--audit',mapping,'--audit-sha256',sha(manifest),'--graph',self.public,'--out',prepared,'--seed',self.c.get('seed',20260713)])
            self.invoke('verify_start_source',['preprocess/verify_start_porto.py','--dataset',prepared,'--archive',self.path('source'),'--graph',self.public,'--out',self.accepted/'source_verification.json'])
            network=self.public/'network.shp';osm=self.public/'public_ways.pkl'
            extras=dict(time_endpoints=str(prepared/'source_lineage.csv'))
        else:
            template=json.loads((self.root/'configs/preprocess_beijing_8_16.json').read_text())
            template['paths'].update(source=str(self.raw/'real_full_frozen.pkl'),timestamps=str(self.raw/'metadata/timestamps_day_serial.pkl.gz'))
            template['paths']['timestamp-bindings']=str(self.raw/'metadata/source_binding.csv')
            template['parameters'].update(dataset=self.c['dataset'],bbox=self.c['bbox'],seed=self.c.get('seed',20260713))
            generated=self.control/'road_preprocessing.json';generated.write_text(json.dumps(template,indent=2),encoding='utf-8')
            review=self.path('review_from') if self.c.get('review_from') else self.root/'data/road_review'
            if review_only:
                if self.c.get('review_from'):
                    if not (review/'selection_review.json').is_file():raise FileNotFoundError(review/'selection_review.json')
                    print('Using explicitly supplied existing review:',review);return [review/'selection_review.json']
                self.invoke('review_geolife_roads',['prepare_roads.py','--config',generated,'--out',review,'--review-only'])
                return [review/'selection_review.json']
            self.invoke('accept_geolife_roads',['prepare_roads.py','--config',generated,'--out',self.accepted,'--review-from',review,'--accept-reviewed-subset','yes'])
            prepared=self.accepted/'dataset';network=self.public/'network/network.shp';osm=self.public/'osm/osm_cache_beijing_drivable_full.pkl'
            extras=dict(mtnet_time_binding=str(self.raw/'mtnet_time_binding.json'),mtnet_raw_reference=str(self.raw/'real_full_frozen.pkl'))
        import geopandas as gpd
        epsg=gpd.read_file(network).crs.to_epsg()
        if epsg is None:raise ValueError('Public graph needs a known CRS')
        canonical=json.loads((prepared/'canonical_manifest.json').read_text())
        bbox=json.loads((prepared/'bbox.json').read_text())['bbox']
        bundle=dict(schema='road-experiment-bundle-v1',dataset=self.c['dataset'],paths=dict(prepared=str(prepared),network=str(network),osm=str(osm),**extras),bbox=bbox,routing_crs=dict(input_srs='EPSG:4326',network_srs='EPSG:'+str(epsg),tracks_srs='EPSG:'+str(epsg)))
        if self.adapter=='start_porto_archive':
            bundle['dfr_author_roads']=dict(manifest=str(self.public/'manifest.json'),sha256=sha(self.public/'manifest.json'))
        bundlefile=self.control/'prepared.dataset.json';bundlefile.write_text(json.dumps(bundle,indent=2),encoding='utf-8')
        config=self.control/'export.json';config.write_text(json.dumps(dict(dataset_bundle=str(bundlefile))),encoding='utf-8')
        self.invoke('standard_export',['preprocess/standardize_dataset.py','--config',config,'--out',self.standard])
        self.invoke('standard_verification',['preprocess/check_standard_package.py','--package',self.standard,'--out',self.control/'standard_verification.json'])
        return [self.standard/'dataset.json',self.standard/'export_report.json',self.control/'standard_verification.json']

    def bind(self,**kwargs):
        import geopandas as gpd
        c=load_config(self._bundle_config(),self.root)
        network=Path(c['paths']['network']);osm=Path(c['paths']['osm'])
        target=self.root/'configs/local_new.json'
        self.invoke('bind_dataset',['bind_dataset.py','--dataset',c['paths']['prepared'],'--network',network,'--osm-cache',osm,'--runtime',self.root/'data/fmm-runtime/Library/bin','--out',target,'--batch',self.c.get('batch','local_new')])
        bound=json.loads(target.read_text());epsg=gpd.read_file(network).crs.to_epsg()
        if epsg is None:raise ValueError('Unknown network CRS')
        bound.update(dataset=self.c['dataset'],dataset_bundle=str(self._active_bundle()),routing_crs=dict(input_srs='EPSG:4326',network_srs='EPSG:'+str(epsg),tracks_srs='EPSG:'+str(epsg)))
        for key in ('time_endpoints','mtnet_time_binding','mtnet_raw_reference'):
            if key in c['paths']:bound['paths'][key]=c['paths'][key]
        if 'dfr_author_roads' in c:bound['dfr_author_roads']=c['dfr_author_roads']
        target.write_text(json.dumps(bound,indent=2),encoding='utf-8')
        return [target]

    def resources(self,**kwargs):
        args=['prepare_public_resources.py','--config','configs/local_new.json',
              '--out-config','configs/local_public.json','--out-dir','data/local_public_resources']
        # Keep Beijing's historical frozen public support. Its existing entry
        # checks graph identity; never feed this snapshot to a different city.
        if self.c['dataset']=='beijing':args+=['--frozen-support','resources']
        self.invoke('prepare_public_resources',args)
        if self.c['dataset']!='beijing':
            config=self.root/'configs/local_public.json'
            partitions=self.root/'data/local_public_resources/endpoint_partitions'
            ks=sorted({json.loads(p.read_text(encoding='utf-8'))['k']
                       for p in (self.root/'supplement/sweeps').glob('k_*_seed_*.json')})
            if not ks:raise ValueError('No registered K values')
            self.invoke('prepare_public_endpoint_partitions',[
                'tools/prepare_city_partitions.py','--config',config,
                '--out',partitions,'--ks',*ks])
            public=json.loads(config.read_text(encoding='utf-8'))
            public['paths']['endpoint_partitions']=str(partitions)
            config.write_text(json.dumps(public,indent=2),encoding='utf-8')
        return [self.root/'configs/local_public.json']

    def _bundle_config(self):
        config=self.control/'standard.config.json'
        config.write_text(json.dumps(dict(dataset_bundle=str(self._active_bundle()))),encoding='utf-8')
        return config

    def _active_bundle(self):
        source=self.standard/'dataset.json'
        data=json.loads(source.read_text(encoding='utf-8-sig'))
        if data.get('dataset')!=self.c['dataset']:raise ValueError('Selected city differs from standard package')
        if self.adapter!='standard_bundle':return source
        # The source package is read-only. Derived caches belong to this new
        # checkout, not to the original package and not to another batch.
        data['paths']={key:str((source.parent/value).resolve()) for key,value in data['paths'].items()
                       if key not in ('edge_cache','metric_cache','source_cache','ubodt','split_audit')}
        if 'dfr_author_roads' in data:
            data['dfr_author_roads']=dict(data['dfr_author_roads'])
            data['dfr_author_roads']['manifest']=str((source.parent/data['dfr_author_roads']['manifest']).resolve())
        if 'osm' not in data['paths'] and self.c.get('osm_source'):
            data['paths']['osm']=str(self.path('osm_source'))
        target=self.control/'input.dataset.json'
        target.write_text(json.dumps(data,indent=2),encoding='utf-8')
        return target


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('stage',choices=('show','fetch','public_graph','read','roads','bind','resources'))
    p.add_argument('--dry-run',action='store_true')
    p.add_argument('--review-only',action='store_true')
    p.add_argument('--accept-reviewed-subset',choices=('yes',))
    a=p.parse_args();workflow=Workflow()
    if a.stage=='show':print(json.dumps(dict(profile=str(workflow.profile),**workflow.c),indent=2));return
    workflow.run(a.stage,a.review_only,a.accept_reviewed_subset=='yes',a.dry_run)
