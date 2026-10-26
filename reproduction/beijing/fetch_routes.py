"""Fetch only a completed remote route cell and verify it against the local M."""
import argparse
import base64
import gzip
import hashlib
import json
from pathlib import Path
import pickle
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parent


def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def verify(folder,config,method,router,train_only=False):
    meta=json.loads((folder/'route_manifest.json').read_text(encoding='utf-8'))
    paths=config['paths'];base=(ROOT/paths['output'])/config['batch']
    data=folder/'synthetic_routes.pkl.gz'
    slots=config['train_slots'] if train_only else config['slots']
    expected={'M':method,'router':router,'status':'VALID','raw_source_used':False,
              'records':slots,
              'measurement_sha256':sha(base/('measurements_train' if train_only else 'measurements')/method/'measurement.pkl'),
              'public_network_sha256':sha(ROOT/paths['network']),
              'edge_cache_sha256':sha(ROOT/paths['edge_cache']),
              'output_sha256':sha(data)}
    for key,value in expected.items():
        if meta.get(key)!=value:raise ValueError('Route binding mismatch: '+key)
    if router in ('FMM','STMatch'):
        parameters=dict(max_points=32,radius_m=200.0,gps_error_m=50.0,candidates=8,
                        min_observation_share=0.95,route_only=True)
        if meta.get('parameters')!=parameters:raise ValueError('Different public routing protocol')
        if meta['public_executable_sha256']!=config['matcher_compatibility'][router.lower()+'_sha256']:
            raise ValueError('Different matcher executable')
    if router=='FMM':
        table=json.loads(Path(config['ubodt_manifest']).read_text(encoding='utf-8'))
        if meta['ubodt_sha256']!=table['output_sha256'] or table['network_sha256']!=expected['public_network_sha256']:
            raise ValueError('Wrong UBODT graph/table')
    with gzip.open(data,'rb') as f:rows=pickle.load(f)
    if len(rows)!=slots or [r['source_index'] for r in rows]!=list(range(slots)):
        raise ValueError('Missing/repeated/reordered route slots')
    return dict(method=method,router=router,records=len(rows),
                accepted=sum(bool(r['accepted']) for r in rows),status='VERIFIED',
                output_sha256=meta['output_sha256'])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',type=Path,required=True)
    p.add_argument('--method',required=True)
    p.add_argument('--router',required=True,choices=('Nearest','FMM','STMatch'))
    p.add_argument('--host',default='pc@10.134.48.163')
    p.add_argument('--train-only',action='store_true',help='Fetch a route from the independent train-only M, never the full-corpus release')
    p.add_argument('--remote-root',default='D:/MTR/experiments_20261016')
    a=p.parse_args();c=json.loads(a.config.read_text(encoding='utf-8'))
    if a.method not in ('SPRT','PrivTrace','DPStd','DPTraj-PM'):
        p.error('Unknown M')
    parent=ROOT/c['paths']['output']/c['batch']/('routes_train' if a.train_only else 'routes')/a.method
    target=parent/a.router
    if target.exists():
        print(json.dumps(verify(target,c,a.method,a.router,a.train_only)));return
    remote=a.remote_root+('/results_train/' if a.train_only else '/results/')+a.method+'/'+a.router
    # Paths are fixed to an explicit method/router and an ASCII deployment root.
    if any(char in remote for char in ("'",'\n','\r',';')):
        p.error('Unsupported remote path')
    command=("$ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue'; "
             f"$p='{remote}/route_manifest.json'; if (!(Test-Path -LiteralPath $p)) {{exit 3}}; "
             "$m=Get-Content -Raw -LiteralPath $p | ConvertFrom-Json; "
             "if ($m.status -ne 'VALID' -or !$m.M) {exit 3}; Write-Output 'READY'")
    encoded=base64.b64encode(command.encode('utf-16-le')).decode('ascii')
    result=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=8',a.host,
                           'powershell','-NoProfile','-EncodedCommand',encoded],capture_output=True,timeout=30)
    if result.returncode==3:
        print('PENDING_REMOTE_ROUTE',a.method,a.router);raise SystemExit(3)
    if result.returncode:
        raise RuntimeError('Remote status check failed: '+result.stderr.decode(errors='replace'))
    parent.mkdir(parents=True,exist_ok=True)
    staging=Path(tempfile.mkdtemp(prefix='_fetch_',dir=parent))
    subprocess.run(['scp','-r','-o','BatchMode=yes','-o','ConnectTimeout=8',
                    a.host+':'+remote,str(staging)],check=True)
    downloaded=staging/a.router
    report=verify(downloaded,c,a.method,a.router,a.train_only)
    downloaded.rename(target)
    staging.rmdir()
    print(json.dumps(report))


if __name__=='__main__':main()
