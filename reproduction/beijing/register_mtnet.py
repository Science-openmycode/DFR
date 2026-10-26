"""Register a completed MTNet edge-ID release without matching or repairing it."""
import argparse
import gzip
import json
from pathlib import Path
import pickle
from numbers import Integral

from preprocess.dataset_contract import validate_dataset, sha

ROOT=Path(__file__).resolve().parent


def validate_training_preparation(prep, prepared, config, path):
    """Require the exact frozen training selection, not a full-population model."""
    m=json.loads(prep.read_text(encoding='utf-8'))
    audit=json.loads(path('split_audit').read_text(encoding='utf-8'))
    indices=json.loads((prepared/'train_split.json').read_text(encoding='utf-8'))['indices']
    expected=dict(split_audit_sha256=sha(path('split_audit')),
                  train_sha256=sha(path('train')),test_sha256=sha(path('test')),
                  train_indices_sha256=sha(prepared/'train_split.json'))
    if (m.get('dataset_id')!=config['frozen_dataset_id']
            or m.get('evaluation_scope')!='strict_tstr'
            or m.get('input_count')!=config['train_slots']
            or m.get('input_sha256')!=expected['train_sha256']
            or m.get('selected_frozen_indices')!=indices
            or len(indices)!=config['train_slots'] or len(set(indices))!=len(indices)
            or m.get('split_binding')!=expected
            or audit.get('status')!='passed' or not audit.get('all_source_indices_used_once')
            or audit.get('train_sha256')!=expected['train_sha256']
            or audit.get('test_sha256')!=expected['test_sha256']
            or audit.get('full_sha256')!=sha(path('real'))):
        raise ValueError('MTNet requires the exact verified frozen train-only preparation')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',type=Path,required=True)
    p.add_argument('--source',type=Path,required=True,help='Fetched native_release directory')
    p.add_argument('--out',type=Path)
    p.add_argument('--train-only',action='store_true')
    p.add_argument('--preparation',type=Path,help='Verified fetched preparation manifest')
    p.add_argument('--model',type=Path,help='Final model bound by the native release')
    a=p.parse_args();c=json.loads(a.config.read_text(encoding='utf-8'))
    def path(key):return (ROOT/c['paths'][key]).resolve()
    identity=validate_dataset(path('prepared'))
    if identity['dataset_id']!=c['frozen_dataset_id']:raise ValueError('Wrong frozen input')
    meta=json.loads((a.source/'manifest.json').read_text(encoding='utf-8'))
    native=a.source/'routes.pkl'
    slots=c['train_slots'] if a.train_only else c['slots']
    if (meta['generated_records']!=slots or meta['routes_sha256']!=sha(native)
            or meta['post_generation_matching'] is not False or meta['private_input_access_during_generation'] is not False):
        raise ValueError('MTNet native release binding invalid')
    base=path('output')/c['batch']
    prep=a.preparation or base/'mtnet_prepared/full_preparation_manifest.json'
    if a.train_only:
        if a.preparation is None or a.model is None:
            raise ValueError('Train-only registration requires explicit preparation and final model')
        validate_training_preparation(prep,path('prepared'),c,path)
    if meta['preparation_manifest_sha256']!=sha(prep):raise ValueError('MTNet used another prepared input')
    if a.model is not None and meta['model_sha256']!=sha(a.model):raise ValueError('MTNet final model hash mismatch')
    with native.open('rb') as f:raw=pickle.load(f)
    with gzip.open(path('edge_cache'),'rb') as f:edges=pickle.load(f)['edge_nodes']
    if len(raw)!=slots:raise ValueError('Missing native slots')
    rows=[]
    for index,route in enumerate(raw):
        if not isinstance(route,(list,tuple)) or any(not isinstance(e,Integral) or isinstance(e,bool) for e in route):
            raise ValueError('MTNet must supply explicit native edge IDs')
        route=list(map(int,route))
        if any(e not in edges for e in route):raise ValueError('Unknown native public edge ID; no rematching permitted')
        if any(edges[u][1]!=edges[v][0] for u,v in zip(route,route[1:])):
            raise ValueError('Disconnected native MTNet route; no gap filling permitted')
        rows.append(dict(source_index=index,accepted=bool(route),connected=bool(route),cpath=route,
                         reason='accepted' if route else 'empty_native_slot'))
    out=(a.out or base/('routes_train' if a.train_only else 'routes')/'MTNet/Origin').resolve()
    if out.exists():raise FileExistsError(out)
    out.mkdir(parents=True);output=out/'synthetic_routes.pkl.gz'
    with gzip.open(output,'wb') as f:pickle.dump(rows,f,pickle.HIGHEST_PROTOCOL)
    record=dict(classification='NATIVE_ROAD_REPRESENTATION_ONLY',method='MTNet',rematched=False,
                gap_filling=False,route_selection=False,records=len(rows),native_sha256=sha(native),
                public_network_sha256=sha(path('network')),output_sha256=sha(output),
                source_representation='native_edge_ids',dataset_id=identity['dataset_id'],
                native_manifest_sha256=sha(a.source/'manifest.json'))
    record.update(evaluation_scope='strict_tstr' if a.train_only else 'full_corpus',
                  preparation_manifest_sha256=sha(prep),model_sha256=meta['model_sha256'])
    (out/'route_manifest.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
    print('REGISTERED_NATIVE_MTNET',len(rows),sha(output))


if __name__=='__main__':main()
