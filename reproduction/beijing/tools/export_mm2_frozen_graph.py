"""I/O-only binding of the existing MM2 public-graph exporter to frozen resources.

No trajectories or measurements are read. No matching is performed.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil


def digest(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def export(network, edge_cache, adapter, out):
    network, edge_cache, adapter, out = map(Path, (network, edge_cache, adapter, out))
    if out.exists():
        raise FileExistsError(out)
    sources = [network, edge_cache, adapter]
    sources += [network.with_suffix(s) for s in ('.dbf', '.shx', '.prj')]
    bindings = {str(p.resolve()): digest(p) for p in sources}
    ref = out / 'source_binding/public_assets'
    target = ref / 'beijing_network'
    target.mkdir(parents=True)
    for source in [network] + [network.with_suffix(s) for s in ('.dbf', '.shx', '.prj')]:
        shutil.copy2(source, target / ('network' + source.suffix))
    shutil.copy2(edge_cache, ref / 'ordered_portal_route_cache.pkl.gz')
    spec = importlib.util.spec_from_file_location('preserved_mm2_public_exporter', adapter)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Only path globals are rebound. The preserved export_graph function,
    # directed edge IDs, all geometry points and consistency checks are unchanged.
    module.HERE = out.resolve()
    module.REPO = (out / 'source_binding').resolve()
    module.export_graph()
    if any(digest(p) != h for p, h in bindings.items()):
        raise ValueError('Source changed during public graph export')
    outputs = {p.relative_to(out).as_posix(): digest(p) for p in (out / 'inputs').iterdir() if p.is_file()}
    record = dict(status='DONE', kind='PUBLIC_GRAPH_PREPARATION_ONLY',
        private_trajectories_accessed=False, matching_executed=False,
        inputs_sha256=bindings, outputs_sha256=outputs,
        note='Preserved export_graph; paths only; one directed OSM way per public edge, way_id=edge_id+1')
    (out / 'export_binding.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
    return record


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('network', 'edge-cache', 'adapter', 'out'):
        parser.add_argument('--' + name, type=Path, required=True)
    print(json.dumps(export(**vars(parser.parse_args())), indent=2))
