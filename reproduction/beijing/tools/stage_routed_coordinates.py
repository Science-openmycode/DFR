"""Create a deterministic routed coordinate view, preserving rejected slots."""
import argparse
import gzip
import importlib.util
import json
import pickle
from pathlib import Path
import tempfile


def stage(routes, manifest, network, out_dir, measurement=None, edge_cache=None, for_road_scoring=False,
          expected_mm2_network_sha256=None):
    spec = importlib.util.spec_from_file_location('edge_coordinate_stage', Path(__file__).with_name('stage_native_edge_coordinates.py'))
    geometry = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(geometry)
    meta = json.loads(Path(manifest).read_text(encoding='utf-8'))
    measurement = Path(measurement or meta['measurement'])
    original = geometry._binding(measurement)
    if original['sha256'] != meta['measurement_sha256']:
        raise ValueError('measurement hash mismatch')
    if meta.get('status') != 'VALID' or meta.get('raw_source_used') is not False:
        raise ValueError('route manifest must declare valid public postprocessing')
    if meta.get('router') not in ('Nearest', 'FMM', 'STMatch', 'MM2-MDP'):
        raise ValueError('not a coordinate-M public router')
    route_binding = geometry._binding(Path(routes))
    if not meta.get('output_sha256') or route_binding['sha256'] != meta['output_sha256']:
        raise ValueError('route hash mismatch')
    expected_network = meta.get('public_network_sha256')
    mm2 = meta['router'] == 'MM2-MDP'
    if expected_mm2_network_sha256 is not None:
        if not mm2 or (expected_network and expected_network != expected_mm2_network_sha256):
            raise ValueError('explicit MM2 network binding conflicts with route manifest')
        expected_network = expected_mm2_network_sha256
    if not expected_network or geometry._binding(Path(network))['sha256'] != expected_network:
        raise ValueError('network hash missing or mismatch')
    if mm2:
        if (not edge_cache or not meta.get('public_edge_cache_sha256')
                or geometry._binding(Path(edge_cache))['sha256'] != meta['public_edge_cache_sha256']
                or meta.get('public_raw_node_connectivity_checked') is not True
                or not meta.get('public_edge_nodes_sha256')):
            raise ValueError('MM2 requires bound edge cache and raw public-node connectivity evidence')
    with gzip.open(routes, 'rb') as stream:
        records = pickle.load(stream)
    with measurement.open('rb') as stream:
        count = len(pickle.load(stream))
    if len(records) != count:
        raise ValueError('routed and measurement slot counts differ')
    if mm2 and (meta.get('records') != count
                or any(row.get('source_index') != i for i, row in enumerate(records))):
        raise ValueError('MM2 must preserve every ordered source slot')
    edge_routes = []
    for record in records:
        if not isinstance(record, dict) or not {'accepted', 'cpath'}.issubset(record):
            raise ValueError('expected explicit edge-record routes')
        # Nearest's accepted flag is set only after its connectivity check;
        # its existing schema does not have a separate connected field.
        if 'connected' not in record and meta['router'] not in ('Nearest', 'MM2-MDP'):
            raise ValueError('missing connected flag')
        edge_routes.append(record['cpath'] if record['accepted'] and record.get('connected', True) else [])
    with tempfile.TemporaryDirectory(prefix='dfr_routed_geometry_') as temporary:
        ids = Path(temporary) / 'edge_ids.pkl.gz'
        with gzip.open(ids, 'wb') as stream:
            pickle.dump(edge_routes, stream)
        result = geometry.stage(routes=ids, network=Path(network), out_dir=Path(out_dir), edge_cache=edge_cache)
    result.update(derivation_mode='public-router-edge-IDs-to-directed-geometry',
                  route_source=route_binding if for_road_scoring else original,
                  measurement_source=original, original_measurement_path=meta['measurement'],
                  routed_artifact=route_binding,
                  route_manifest=geometry._binding(Path(manifest)),
                  lineage_policy='route_source binds the DP measurement ancestor; routed_artifact binds the exact geometry input',
                  router=meta['router'])
    if mm2:
        result.update(network_binding_policy='explicit frozen-network SHA plus directed public geometry verification',
                      expected_mm2_network_sha256=expected_network,
                      raw_node_connectivity_evidence=meta['public_edge_nodes_sha256'])
    for name in ('coordinates.pkl.manifest.json', 'manifest.json'):
        (Path(out_dir) / name).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('routes', 'manifest', 'network', 'out-dir'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--measurement',type=Path,help='Explicit migrated M file; original SHA256 must match')
    parser.add_argument('--edge-cache',type=Path)
    parser.add_argument('--for-road-scoring',action='store_true',help='Bind route_source to the actual road object, while retaining measurement_source ancestry')
    parser.add_argument('--expected-mm2-network-sha256',help='Explicit frozen public shapefile SHA for MM2 manifests; original manifest is not rewritten')
    result = stage(**vars(parser.parse_args()))
    print(json.dumps({'records': result['record_count'], 'valid': result['nonempty_slot_count']}))


if __name__ == '__main__':
    main()
