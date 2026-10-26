import numpy as np
import pytest
from tools.evaluate_empty_coordinates import empty_statistics, UNDEFINED


def test_all_empty_slots_do_not_become_a_uniform_distribution():
    rows=[np.empty((0,2)) for _ in range(3)]
    result=empty_statistics([np.array([[0,0],[1,1]])],rows)
    assert all(result[key] is None for key in UNDEFINED)
    assert result['directed_road_validity']==0
    assert result['route_compatible_yield']==0
    assert len(rows)==3


def test_normal_cases_cannot_accidentally_use_empty_boundary():
    with pytest.raises(ValueError,match='ordinary release'):
        empty_statistics([], [np.array([[0,0],[1,1]])])
