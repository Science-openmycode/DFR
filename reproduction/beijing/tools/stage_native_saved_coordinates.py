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


def build(routes, network, edge_cache, out, native_source=None, for_tstr=False):
    routes = Path(routes)
    meta = json.loads((routes.parent/'route_manifest.json').read_text(encoding='utf-8'))
    binding = _binding(routes)
    if meta.get('classification') != 'NATIVE_ROAD_REPRESENTATION_ONLY' or meta.get('rematched') is not False:
        raise ValueError('Requires explicitly checked native representation, not a rematched route')
    if meta['output_sha256'] != binding['sha256'] or meta['public_network_sha256'] != _binding(network)['sha256']:
        raise ValueError('Native representation or public network changed')
    if for_tstr:
        if native_source is None or meta['native_sha256'] != _binding(native_source)['sha256']:
            raise ValueError('TSTR view must bind the executed native release')
    with gzip.open(routes,'rb') as f:
        records = pickle.load(f)
    edges = []
    for index, row in enumerate(records):
        if row['source_index'] != index or not isinstance(row['accepted'], bool):
            raise ValueError('Invalid saved native slot')
        edges.append(row['cpath'] if row['accepted'] else [])
    with tempfile.TemporaryDirectory(prefix='native_representation_') as temp:
        ids = Path(temp)/'edge_ids.pkl.gz'
        with gzip.open(ids,'wb') as f:
            pickle.dump(edges,f,pickle.HIGHEST_PROTOCOL)
        result = stage(routes=ids,network=network,edge_cache=edge_cache,out_dir=out)
    result.update(route_source=_binding(native_source) if for_tstr else binding,
                  routed_artifact=binding,
                  native_representation_manifest=_binding(routes.parent/'route_manifest.json'),
                  rematched=False,gap_filling=False,route_selection=False,
                  derivation_mode='checked-'+meta.get('source_representation','native-roads')+'-to-identical-edge-geometry')
    for name in ('manifest.json','coordinates.pkl.manifest.json'):
        (Path(out)/name).write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('routes','network','edge-cache','out-dir'):
        p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--native-source',type=Path)
    p.add_argument('--for-tstr',action='store_true')
    a = p.parse_args()
    result = build(a.routes,a.network,a.edge_cache,a.out_dir,a.native_source,a.for_tstr)
    print('NATIVE_GEOMETRY_VIEW',result['record_count'],result['nonempty_slot_count'])


if __name__ == '__main__':
    main()
