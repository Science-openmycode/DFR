"""Public author-road grouping adapter; never read trajectory observations."""
from collections import defaultdict
import json
from pathlib import Path
from preprocess.dataset_contract import sha


def bind_author_domain(core, config, root, network):
    """Keep the Beijing core unchanged unless an explicit author binding exists."""
    if not config.get('dfr_author_roads'):
        return None
    builder, binding = load_author_domain(config['dfr_author_roads'], root, network)
    core.build_public_endpoint_domain = builder
    return binding


def author_groups(mapping, edge_ids):
    signatures = defaultdict(list)
    for road, row in mapping.items():
        edges = tuple(row['edges'])
        if row.get('status') != 'EXACT_UNIQUE_CONNECTED' or not edges:
            raise ValueError('Invalid author road mapping: ' + road)
        if any(type(e) is not int for e in edges):
            raise ValueError('Author edge IDs must be integers')
        signatures[edges].append(road)
    groups = {}
    aliases = []
    for edges, roads in signatures.items():
        # Exact duplicate complete directed polylines are aliases, not a choice
        # between competing partial road memberships. Preserve every source ID.
        name = 'START:' + json.dumps(sorted(roads), separators=(',', ':'))
        if len(roads) > 1:
            aliases.append(sorted(roads))
        for edge in edges:
            if edge in groups and groups[edge] != name:
                raise ValueError(f'Ambiguous partial author-road overlap at edge {edge}')
            groups[edge] = name
    if set(groups) != set(edge_ids):
        raise ValueError('Author mapping does not cover exactly the public graph')
    return groups, sorted(aliases)


def load_author_domain(binding, root, network):
    """Hash-bind the existing approved graph; do not edit frozen SHP/DBF files."""
    import geopandas as gpd
    manifest_path = (Path(root) / binding['manifest']).resolve()
    if sha(manifest_path) != binding['sha256']:
        raise ValueError('Author graph manifest SHA mismatch')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if manifest.get('carrier_policy') != 'source_directed_v1':
        raise ValueError('Explicit source-directed graph required')
    for name in ('network.shp', 'network.dbf', 'network.shx', 'network.prj', 'road_mapping.json'):
        if sha(manifest_path.parent / name) != manifest['outputs'][name]:
            raise ValueError('Author graph resource changed: ' + name)
    # Relocated standard packages may refer to the original author manifest.
    # Accept only identical complete graph bytes, never path names alone.
    for suffix in ('.shp','.dbf','.shx','.prj'):
        if sha(Path(network).with_suffix(suffix)) != manifest['outputs']['network'+suffix]:
            raise ValueError('Author graph copy changed: network'+suffix)
    frame = gpd.read_file(network)
    if frame['id'].duplicated().any():
        raise ValueError('Duplicate public edge IDs')
    mapping = json.loads((manifest_path.parent / 'road_mapping.json').read_text(encoding='utf-8'))
    groups, aliases = author_groups(mapping, frame['id'].astype(int))

    def build(cache):
        if set(map(int, cache['edge_nodes'])) != set(groups):
            raise ValueError('Endpoint cache edge IDs differ from author graph')
        attrs = {}
        for edge_id, nodes in cache['edge_nodes'].items():
            pair = tuple(nodes)
            value = (groups[int(edge_id)], None, None)
            if pair in attrs and attrs[pair] != value:
                raise ValueError('Metric node pair merges different author roads')
            attrs[pair] = value
        return sorted(attrs), attrs

    return build, {'mode': 'author-road-v1', 'manifest_sha256': binding['sha256'],
                   'adapter_sha256': sha(Path(__file__)),
                   'mapping_sha256': manifest['outputs']['road_mapping.json'],
                   'exact_duplicate_road_aliases': aliases,
                   'unused_road_class_and_heading': 'NOT_PROVIDED_NOT_CONSUMED'}
