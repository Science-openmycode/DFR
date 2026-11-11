"""Budget/entry organization checks; no private input or experiment generation."""
import math
import pytest
from experiments.separate import METHODS, ROUTE_METHODS
from mtnet_dp_od import engine

def test_existing_methods_preserved():
    assert METHODS == ('SPRT', 'PrivTrace', 'DPTraj-PM', 'DPStd')
    assert set(METHODS).issubset(ROUTE_METHODS)
    assert 'AdaTrace' in ROUTE_METHODS
    assert 'MTNet' not in ROUTE_METHODS

@pytest.mark.parametrize('total', [.2,.4,.7,1.,1.4,2.,3.])
def test_seven_existing_budgets(tmp_path,total):
    m=engine(tmp_path,'public-fixture');model=total/1.4;od=total*(.4/1.4)
    assert math.isclose(model+od,total,abs_tol=1e-14)
    sigma=m.sigma_for_budget(model)
    assert m.epsilon(sigma)<=model+1e-12
    assert abs(m.epsilon(sigma)-model)<1e-10
    if total==1.4:
        assert sigma==m.sigma_for_budget()
        assert 2/od==5.

@pytest.mark.parametrize('value',[0.,-1.,float('nan'),float('inf')])
def test_invalid_budget(tmp_path,value):
    with pytest.raises(ValueError):engine(tmp_path,'public-fixture').sigma_for_budget(value)

def test_standard_and_light_are_existing_mm2_option_sets():
    from pathlib import Path
    from algorithms.routers.mm2_mdp_adapter import mm2_command
    args=[Path('mm2.exe'),Path('network'),Path('tracks.csv'),Path('out')]
    standard=mm2_command(*args,tracks_srs='32650',network_srs='32650',profile='standard')
    light=mm2_command(*args,tracks_srs='32650',network_srs='32650',profile='light')
    assert light==standard+['--candidate-adoption','off','--simplify-track','on']
    assert standard[standard.index('--threads')+1]=='4'
