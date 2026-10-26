import json
import pytest
from preprocess.dataset_contract import validate_dataset,sha


def frozen_fixture(tmp_path):
    root=tmp_path/'dataset';root.mkdir()
    graph=tmp_path/'mirror.shp';graph.write_bytes(b'original graph')
    graph.with_suffix('.prj').write_bytes(b'original CRS')
    content={'trajectories.pkl':b'x','trajectories.pkl.gz':b'x','road_records.pkl.gz':b'x',
             'train.pkl':b'x','test.pkl':b'x','source_indices.json':b'[0,1]',
             'train_split.json':b'{"indices":[0]}','test_split.json':b'{"indices":[1]}','bbox.json':b'[]'}
    for name,data in content.items():(root/name).write_bytes(data)
    meta=dict(schema='frozen-road-dataset-v1',status='FROZEN',trajectory_count=2,train_count=1,test_count=1,
              network=str(tmp_path/'old_machine/missing.shp'),network_sha256=sha(graph),
              network_sidecars={'.prj':sha(graph.with_suffix('.prj'))},
              artifacts={name:sha(root/name) for name in content})
    (root/'canonical_manifest.json').write_text(json.dumps(meta),encoding='utf-8')
    return root,graph


def test_migration_keeps_original_manifest_and_dataset_identity(tmp_path):
    root,graph=frozen_fixture(tmp_path);before=sha(root/'canonical_manifest.json')
    with pytest.raises(FileNotFoundError):validate_dataset(root)
    result=validate_dataset(root,public_network=graph)
    assert result['dataset_id']==before==sha(root/'canonical_manifest.json')
    assert result['count']==2


@pytest.mark.parametrize('part',['graph','sidecar'])
def test_migration_does_not_accept_changed_graph_or_crs(tmp_path,part):
    root,graph=frozen_fixture(tmp_path)
    (graph if part=='graph' else graph.with_suffix('.prj')).write_bytes(b'wrong')
    with pytest.raises(ValueError):validate_dataset(root,public_network=graph)
