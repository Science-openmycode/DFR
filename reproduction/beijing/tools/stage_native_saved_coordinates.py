"""Geometry-only coordinate view of already saved native edge-record routes."""
import argparse
import gzip
import json
from pathlib import Path
import pickle
import tempfile

try:
    from tools.stage_native_edge_coordinates import stage, _binding
except ModuleNotFoundError:
    from stage_native_edge_coordinates import stage, _binding


def build(routes, network, edge_cache, out, native_source=None, bind_native_source=False):
    routes = Path(routes)
    binding = _binding(routes)
    representation = routes.parent/'route_manifest.json'
    frozen = routes.parent/'canonical_manifest.json'
    is_real = not representation.exists() and routes.name == 'road_records.pkl.gz' and frozen.exists()
    if is_real:
        dataset = json.loads(frozen.read_text(encoding='utf-8-sig'))
        if (dataset.get('schema') != 'frozen-road-dataset-v1' or dataset.get('status') != 'FROZEN'
                or dataset.get('artifacts',{}).get(routes.name) != binding['sha256']
                or dataset.get('network_sha256') != _binding(network)['sha256']):
            raise ValueError('Frozen real roads or public graph binding changed')
        if bind_native_source:
            raise ValueError('Frozen real reference is not a native generator release')
        meta = dict(classification='FROZEN_REAL_GEOMETRY_REFERENCE',rematched=False,
                    output_sha256=binding['sha256'],public_network_sha256=dataset['network_sha256'],
                    source_representation='frozen-real-edge-records')
    else:
        meta = json.loads(representation.read_text(encoding='utf-8-sig'))
    if not is_real and (meta.get('classification') != 'NATIVE_ROAD_REPRESENTATION_ONLY' or meta.get('rematched') is not False):
        raise ValueError('Requires explicitly checked native representation, not a rematched route')
    if meta['output_sha256'] != binding['sha256'] or meta['public_network_sha256'] != _binding(network)['sha256']:
        raise ValueError('Native representation or public network changed')
    if bind_native_source:
        if native_source is None or meta['native_sha256'] != _binding(native_source)['sha256']:
            raise ValueError('Native provenance view must bind the executed native release')
    with gzip.open(routes,'rb') as f:
        records = pickle.load(f)
    if is_real and len(records) != dataset['trajectory_count']:
        raise ValueError('Frozen real slot count changed')
    if is_real:
        indices_path = routes.parent/'source_indices.json'
        if dataset['artifacts'].get('source_indices.json') != _binding(indices_path)['sha256']:
            raise ValueError('Frozen real source-index binding changed')
        source_indices = json.loads(indices_path.read_text(encoding='utf-8-sig'))
        if len(source_indices) != len(records) or len(set(source_indices)) != len(records):
            raise ValueError('Frozen real source-index coverage changed')
    else:
        source_indices = range(len(records))
    edges = []
    for index, row in enumerate(records):
        if row['source_index'] != source_indices[index] or not isinstance(row['accepted'], bool):
            raise ValueError('Invalid saved native slot')
        edges.append(row['cpath'] if row['accepted'] else [])
    with tempfile.TemporaryDirectory(prefix='native_representation_') as temp:
        ids = Path(temp)/'edge_ids.pkl.gz'
        with gzip.open(ids,'wb') as f:
            pickle.dump(edges,f,pickle.HIGHEST_PROTOCOL)
        result = stage(routes=ids,network=network,edge_cache=edge_cache,out_dir=out)
    result.update(route_source=_binding(native_source) if bind_native_source else binding,
                  routed_artifact=binding,
                  rematched=False,gap_filling=False,route_selection=False,
                  derivation_mode='checked-'+meta.get('source_representation','native-roads')+'-to-identical-edge-geometry')
    if is_real:
        result.update(source_classification='FROZEN_REAL_GEOMETRY_REFERENCE',
                      frozen_dataset_manifest=_binding(frozen),dataset_id=_binding(frozen)['sha256'])
    else:
        result['native_representation_manifest'] = _binding(representation)
    for name in ('manifest.json','coordinates.pkl.manifest.json'):
        (Path(out)/name).write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('routes','network','edge-cache','out-dir'):
        p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--native-source',type=Path)
    p.add_argument('--bind-native-source',action='store_true')
    a = p.parse_args()
    result = build(a.routes,a.network,a.edge_cache,a.out_dir,a.native_source,a.bind_native_source)
    print('NATIVE_GEOMETRY_VIEW',result['record_count'],result['nonempty_slot_count'])


if __name__ == '__main__':
    main()
