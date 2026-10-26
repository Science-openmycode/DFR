"""Public endpoint partition validation; never reads private trajectories."""
import hashlib
import json
from numbers import Integral
from pathlib import Path


def file_sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def validate_partition(cache, labels, count, selected=8):
    if isinstance(count, bool) or not isinstance(count, Integral) or count < max(24, selected):
        raise ValueError('Endpoint partition count must be an integer >=24 and >= selected cells')
    count = int(count)
    normalized = {}
    for key, value in labels.items():
        if isinstance(value, bool) or not isinstance(value, Integral):
            raise ValueError('Endpoint labels must be integers')
        node = int(key)
        if str(node) != str(key) or node in normalized:
            raise ValueError('Invalid or duplicate public node identifier')
        normalized[node] = int(value)
    nodes = {int(node) for edge in cache['edge_nodes'].values() for node in edge}
    if set(normalized) != nodes:
        raise ValueError('Endpoint partition must cover exactly the public graph nodes')
    if set(normalized.values()) != set(range(count)):
        raise ValueError('Actual nonempty region count does not match declared K')
    coarse = cache['labels24']
    parents = {}
    for node, cell in normalized.items():
        parent = coarse.get(node)
        if not isinstance(parent, Integral) or not 0 <= int(parent) < 24:
            raise ValueError('Missing or invalid public coarse-region label')
        if cell in parents and parents[cell] != int(parent):
            raise ValueError('A fine region crosses coarse-region boundaries')
        parents[cell] = int(parent)
    if set(parents.values()) != set(range(24)):
        raise ValueError('All 24 fixed coarse regions must remain supported')
    for role in (0, 1):
        supported = {normalized[int(edge[role])] for edge in cache['edge_nodes'].values()}
        if supported != set(range(count)):
            raise ValueError(f'Partition has unsupported endpoint regions for role {role}')
    return normalized, count


def load_partition(path, cache, *, network, metric_cache, selected=8):
    path = Path(path)
    payload = json.loads(path.read_text(encoding='utf-8'))
    if payload.get('schema') != 'dfr-public-endpoint-partition-v1':
        raise ValueError('Unsupported endpoint partition schema')
    if payload.get('source') != 'public-road-graph-only':
        raise ValueError('Partition must be derived from the public road graph only')
    expected = {'network_sha256': file_sha(network), 'metric_cache_sha256': file_sha(metric_cache)}
    if any(payload.get(key) != value for key, value in expected.items()):
        raise ValueError('Endpoint partition graph/cache binding mismatch')
    labels, count = validate_partition(cache, payload['labels'], payload['k'], selected)
    binding = dict(schema=payload['schema'], source=payload['source'], k=count,
                   selected_cells_per_role=selected, partition_sha256=file_sha(path), **expected)
    return labels, count, binding
