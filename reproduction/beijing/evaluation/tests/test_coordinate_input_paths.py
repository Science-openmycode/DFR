import json
import pickle
import sys
from pathlib import Path
import pytest
import evaluate_coordinates as entry


@pytest.mark.parametrize('method,router',[('SPRT','FMM'),('MTR-DFR','Origin'),('MTNet','Origin')])
@pytest.mark.parametrize('protocol',['legacy','audit-v2'])
def test_explicit_relative_road_input_reaches_child_as_same_absolute_file(tmp_path,monkeypatch,method,router,protocol):
    monkeypatch.setattr(entry,'ROOT',tmp_path)
    monkeypatch.chdir(tmp_path)
    paths={k:k for k in ('prepared','network','real','osm','edge_cache','legacy')}
    paths['output']='results'
    config=tmp_path/'config.json'
    config.write_text(json.dumps(dict(paths=paths,frozen_dataset_id='frozen',batch='batch',slots=1,dataset='test',bbox=[0,1,0,1],evaluation_seed=1)))
    monkeypatch.setattr(entry,'validate_dataset',lambda *a,**kw:dict(dataset_id='frozen'))
    view=tmp_path/'results/batch/coordinate_views'/method/router
    view.mkdir(parents=True)
    with (view/'coordinates.pkl').open('wb') as f:pickle.dump([[[0,0],[1,1]]],f)
    road=Path('inputs/explicit_routes.pkl.gz');road.parent.mkdir();road.write_bytes(b'unchanged-route-object')
    calls=[]
    monkeypatch.setattr(entry.subprocess,'run',lambda command,**kwargs:calls.append(command))
    monkeypatch.setattr(sys,'argv',['evaluate_coordinates.py','--config',str(config),'--method',method,'--router',router,
        '--input',str(road),'--metric-protocol',protocol])
    entry.main()
    assert len(calls)==1
    argument=calls[0][calls[0].index('--road-routes')+1]
    assert Path(argument).is_absolute()
    assert Path(argument)==road.resolve()
    assert Path(argument).read_bytes()==b'unchanged-route-object'
