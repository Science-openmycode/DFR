"""Check saved MM2/coordinate-stager contracts without generating or scoring data."""
import argparse
import json
from pathlib import Path
import tempfile
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.stage_routed_coordinates import stage
from tools.stage_native_edge_coordinates import _binding


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--fixed-binding-only', action='store_true')
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(args.out)
    folder = args.batch/'routes/SPRT/MM2-MDP'
    metadata = json.loads((folder/'route_manifest.json').read_text(encoding='utf-8'))
    network = ROOT/'resources/network/network.shp'
    cache = ROOT/'resources/edge_cache/edge_cache.pkl.gz'
    if args.fixed_binding_only:
        from tools.coordinate_resource_binding import coordinate_resources
        config=json.loads((ROOT/'reproduction_checked_20261024/config.json').read_text(encoding='utf-8'))
        cache, options=coordinate_resources(config,ROOT,'MM2-MDP',folder/'route_manifest.json')
        result={'status':'BOUND_TO_SAVED_PUBLIC_RESOURCES','experiment_executed':False,
                'cache':_binding(cache), 'stage_options':options,
                'route_manifest':_binding(folder/'route_manifest.json')}
        args.out.parent.mkdir(parents=True,exist_ok=True)
        args.out.write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result))
        return
    result = {'experiment_executed': False, 'route_manifest': _binding(folder/'route_manifest.json'),
              'configured_cache_matches_route_cache': _binding(cache)['sha256'] == metadata['public_edge_cache_sha256'],
              'caller_supplies_expected_network': False,
              'route_has_public_network_sha256': bool(metadata.get('public_network_sha256'))}
    with tempfile.TemporaryDirectory(prefix='mm2_contract_audit_') as temporary:
        try:
            stage(folder/'synthetic_routes.pkl.gz', folder/'route_manifest.json', network,
                  Path(temporary)/'view', measurement=args.batch/'measurements/SPRT/measurement.pkl',
                  edge_cache=cache, for_road_scoring=True)
        except (ValueError, FileNotFoundError) as exc:
            result.update(status='REJECTED', error=str(exc))
        else:
            result.update(status='ACCEPTED')
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
