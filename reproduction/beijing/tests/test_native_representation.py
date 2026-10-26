import importlib.util
from pathlib import Path

import pandas as pd
import pytest
from shapely.geometry import LineString


def module():
    file=Path(__file__).resolve().parents[1]/'tools/convert_native_node_pairs.py'
    spec=importlib.util.spec_from_file_location('native_representation',file)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def test_parallel_ids_with_same_geometry_preserve_walk_and_slots():
    m=module(); line=LineString([(0,0),(1,0)])
    f=pd.DataFrame([dict(id=8,source=1,target=2,geometry=line),
                    dict(id=3,source=1,target=2,geometry=line)])
    rows=m.convert([[(1,2)],[]],m.canonical_pairs(f))
    assert rows[0]['cpath']==[3]
    assert len(rows)==2 and not rows[1]['accepted']


def test_different_geometry_cannot_be_resolved_by_choosing_a_road():
    f=pd.DataFrame([dict(id=8,source=1,target=2,geometry=LineString([(0,0),(1,0)])),
                    dict(id=3,source=1,target=2,geometry=LineString([(0,0),(0,1),(1,0)]))])
    with pytest.raises(ValueError,match='Ambiguous physical geometry'):
        module().canonical_pairs(f)


def test_disconnected_native_route_is_not_completed():
    with pytest.raises(ValueError,match='disconnected'):
        module().convert([[(1,2),(3,4)]],{(1,2):1,(3,4):2})
