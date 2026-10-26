from pathlib import Path
import pytest
from tools.export_mm2_frozen_graph import export


def fixture(tmp_path, change=False):
    network = tmp_path / 'network.shp'
    for suffix in ('.shp', '.dbf', '.shx', '.prj'):
        network.with_suffix(suffix).write_bytes(suffix.encode())
    cache = tmp_path / 'cache.pkl.gz'; cache.write_bytes(b'public cache')
    adapter = tmp_path / 'adapter.py'
    adapter.write_text("def export_graph():\n"
        "    assert (REPO/'public_assets/beijing_network/network.shp').read_bytes()==b'.shp'\n"
        "    assert (REPO/'public_assets/ordered_portal_route_cache.pkl.gz').read_bytes()==b'public cache'\n"
        "    target=HERE/'inputs';target.mkdir()\n"
        "    (target/'public_network.osm').write_text('all public points')\n" +
        ("    from pathlib import Path\n    Path(" + repr(str(network)) + ").write_bytes(b'changed')\n" if change else ''),
        encoding='utf-8')
    return network, cache, adapter, tmp_path / 'out'


def test_binds_paths_only_and_refuses_overwrite(tmp_path):
    args = fixture(tmp_path)
    record = export(*args)
    assert record['status'] == 'DONE'
    assert record['private_trajectories_accessed'] is False
    assert record['matching_executed'] is False
    assert (args[-1]/'inputs/public_network.osm').read_text() == 'all public points'
    with pytest.raises(FileExistsError): export(*args)


def test_rejects_changed_public_source(tmp_path):
    args = fixture(tmp_path, change=True)
    with pytest.raises(ValueError, match='Source changed'): export(*args)
    assert not (args[-1]/'export_binding.json').exists()


def test_requires_complete_shapefile(tmp_path):
    args = fixture(tmp_path)
    args[0].with_suffix('.shx').unlink()
    with pytest.raises(FileNotFoundError): export(*args)
    assert not args[-1].exists()
