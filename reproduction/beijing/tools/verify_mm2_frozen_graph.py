"""Bind paths for the preserved MM2 full public geometry/edge-ID verifier."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys


def sha(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def verify(directory, verifier):
    directory, verifier = Path(directory).resolve(), Path(verifier).resolve()
    if (directory / 'graph_validation.json').exists():
        raise FileExistsError('Public graph validation already exists')
    binding = json.loads((directory/'public_graph/export_binding.json').read_text(encoding='utf-8'))
    if binding.get('status') != 'DONE' or binding.get('matching_executed') is not False:
        raise ValueError('Public export not complete')
    for name, expected in binding['outputs_sha256'].items():
        if sha(directory/'public_graph'/name) != expected:
            raise ValueError('Public export changed: ' + name)
    source = directory/'public_graph/inputs/public_network.osm'
    alias = directory/'inputs/public_network.osm'
    if alias.exists():
        if sha(alias) != sha(source):
            raise ValueError('Different existing public OSM alias')
    else:
        shutil.copy2(source, alias)
    before = {str(p): sha(p) for p in (verifier, directory/'adapter.py', directory/'network/edges.csv')}
    sys.path.insert(0, str(directory))
    spec = importlib.util.spec_from_file_location('preserved_mm2_geometry_verifier', verifier)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.HERE = directory
    module.REPO = directory/'public_graph/source_binding'
    module.graph_check()
    if any(sha(p) != h for p, h in before.items()):
        raise ValueError('Verifier, adapter or imported graph changed')
    result = json.loads((directory/'graph_validation.json').read_text(encoding='utf-8'))
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('directory', 'verifier'):
        p.add_argument('--'+name, type=Path, required=True)
    print(json.dumps(verify(**vars(p.parse_args())), indent=2))
