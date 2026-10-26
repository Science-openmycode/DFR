"""Bind saved MM2 geometry to frozen public resources; never rematch routes."""
import hashlib
import json
from pathlib import Path


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def coordinate_resources(config, root, router, route_manifest=None):
    root = Path(root)
    def path(key):
        return (root/config['paths'][key]).resolve()
    if router != 'MM2-MDP':
        return path('edge_cache'), {}
    if route_manifest is None:
        raise ValueError('MM2 coordinate staging requires its saved route manifest')
    meta = json.loads(Path(route_manifest).read_text(encoding='utf-8'))
    if meta.get('router') != router or meta.get('raw_source_used') is not False:
        raise ValueError('Not a public MM2 route')
    # Never fall back to a different node namespace merely because it exists.
    cache = path('mm2_edge_cache') if config['paths'].get('mm2_edge_cache') else path('metric_cache')
    if sha(cache) != meta.get('public_edge_cache_sha256'):
        raise ValueError('MM2 coordinate cache differs from its saved route binding')
    public_map = (path('mm2_public_edge_nodes') if config['paths'].get('mm2_public_edge_nodes')
                  else path('mm2').parent/'public_graph/inputs/public_edge_nodes.json')
    if sha(public_map) != meta.get('public_edge_nodes_sha256'):
        raise ValueError('MM2 public edge-node map differs from saved route binding')
    canonical = json.loads((path('prepared')/'canonical_manifest.json').read_text(encoding='utf-8'))
    expected = canonical['network_sha256']
    if sha(path('network')) != expected:
        raise ValueError('Coordinate network differs from frozen dataset network')
    return cache, {'expected_mm2_network_sha256': expected}
