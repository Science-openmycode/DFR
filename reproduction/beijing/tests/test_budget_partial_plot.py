import pytest
from plotting.render_budget_comparison import validate_plot_rows

def test_complete_points_unchanged():
    assert validate_plot_rows([dict(value='0',sd='',n='1')])==0

def test_pending_requires_explicit_mode_and_remains_blank():
    rows=[dict(value='',sd='',n='0',status='MISSING')]
    with pytest.raises(ValueError):validate_plot_rows(rows)
    assert validate_plot_rows(rows,True)==1
    assert rows[0]['value']==''

def test_invalid_completed_value_not_hidden_as_missing():
    with pytest.raises(ValueError):
        validate_plot_rows([dict(value='nan',sd='',n='1')],True)
