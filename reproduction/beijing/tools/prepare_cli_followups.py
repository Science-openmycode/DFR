"""Prepare small-test public partition/configuration inputs; no synthesis or scoring."""
import argparse
import copy
import gzip
import hashlib
import json
from pathlib import Path
import pickle

ROOT=Path(__file__).resolve().parents[1]

def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def write(path,data):
    path.write_text(json.dumps(data,indent=2),encoding='utf-8')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('config','out','train-coordinates','train-lineage'):
        p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    if a.out.exists():raise FileExistsError(a.out)
    for path in (a.config,a.train_coordinates,a.train_lineage):
        if not path.is_file():raise FileNotFoundError(path)
    c=json.loads(a.config.read_text(encoding='utf-8'))
    # Only public labels/cache construct the endpoint partition.
    metric=(ROOT/c['paths']['metric_cache']).resolve()
    network=(ROOT/c['paths']['network']).resolve()
    with gzip.open(metric,'rb') as stream:cache=pickle.load(stream)
    a.out.mkdir(parents=True)
    write(a.out/'partition24.json',dict(schema='dfr-public-endpoint-partition-v1',
        source='public-road-graph-only',k=24,labels=cache['labels24'],
        network_sha256=sha(network),metric_cache_sha256=sha(metric),
        purpose='ARTIFICIAL_CLI_TEST_ONLY_NOT_RESEARCH_RESULTS'))
    budget=copy.deepcopy(c);budget['epsilon']=.2
    write(a.out/'budget_0p2.json',budget)
    releases={'MTR-DFR':dict(coordinates=str(a.train_coordinates.resolve()),
                            lineage=str(a.train_lineage.resolve()))}
    write(a.out/'releases.json',releases)
    c['tstr_releases']=releases
    write(a.out/'ordered_attack.json',c)
    print('FOLLOWUP_INPUTS_READY',a.out)

if __name__=='__main__':main()
