import csv
import gzip
import json
import pickle
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
from preprocess.historical_review import digest, validate_historical_review
from preprocess.historical_review import preserve_frozen_projection


def fixture(tmp):
    raw=[np.array([[39.8,116.2],[39.9,116.3]])];times=[np.array([1.,2.])]
    bindings=[{'source_index':'0','coordinate_sha256':'verified-elsewhere','plt_file':'001/Trajectory/a.plt'}]
    legacy=tmp/'legacy_inputs';legacy.mkdir();(tmp/'dataset').mkdir()
    def save(path,value):
        with (gzip.open(path,'wb') if str(path).endswith('.gz') else open(path,'wb')) as f:pickle.dump(value,f)
    save(legacy/'source.pkl',raw);save(legacy/'timestamps.pkl.gz',times)
    (legacy/'network.shp').write_bytes(b'graph');(legacy/'matcher-module.py').write_bytes(b'matcher')
    with (legacy/'timestamp-bindings.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(bindings[0]));w.writeheader();w.writerows([dict(bindings[0],plt_file='E:\\old\\Data\\001\\Trajectory\\a.plt')])
    records=[dict(source_index=0,accepted=True,cpath=[1])]
    save(tmp/'reviewed_records.pkl.gz',records);save(tmp/'dataset/road_records.pkl.gz',records)
    (tmp/'selection_review.json').write_text('{}')
    manifest=dict(selection_review_sha256=digest(tmp/'selection_review.json'),artifacts={'road_records.pkl.gz':digest(tmp/'dataset/road_records.pkl.gz')})
    (tmp/'dataset/canonical_manifest.json').write_text(json.dumps(manifest))
    argv=['python','road_dataset.py','--dataset','beijing','--bbox','39.75','40.15','116.1','116.65'];inputs={}
    for role in ('source','network','matcher-module','timestamps','timestamp-bindings'):
        path=next(legacy.glob(role+'.*'));old='/missing/original/'+path.name
        argv+=['--'+role,old];inputs[old]=digest(path)
    previous=dict(command=argv,inputs=inputs,dataset_manifest_sha256=digest(tmp/'dataset/canonical_manifest.json'))
    (tmp/'preprocessing_run.json').write_text(json.dumps(previous))
    args=SimpleNamespace(dataset='beijing',bbox=[39.75,40.15,116.1,116.65],network=legacy/'network.shp',matcher_module=legacy/'matcher-module.py')
    return previous,args,raw,times,bindings


def test_relocated_legacy_is_checked(tmp_path):
    previous,args,raw,times,bindings=fixture(tmp_path)
    rows,proof=validate_historical_review(tmp_path,previous,args,raw,times,bindings)
    assert len(rows)==1 and proof['matching_executed'] is False


@pytest.mark.parametrize('change',['source','time','road','manifest'])
def test_changed_input_is_rejected(tmp_path,change):
    previous,args,raw,times,bindings=fixture(tmp_path)
    if change=='source':raw[0][0,0]+=1
    if change=='time':times[0][0]+=1
    if change=='road':(tmp_path/'reviewed_records.pkl.gz').write_bytes(gzip.compress(pickle.dumps([dict(source_index=0,accepted=True,cpath=[2])])) )
    if change=='manifest':(tmp_path/'dataset/canonical_manifest.json').write_text('{}')
    with pytest.raises(ValueError):validate_historical_review(tmp_path,previous,args,raw,times,bindings)


def test_existing_projection_is_not_rewritten_for_machine_roundoff():
    old=np.array([[39.98528311754313,116.45079874742703]])
    new=old.copy();new[0,0]=np.nextafter(new[0,0],0)
    result,delta=preserve_frozen_projection(new,old)
    assert np.array_equal(result,old) and delta>0


@pytest.mark.parametrize('latitude',[39.91,float('nan')])
def test_projection_guard_rejects_real_movement(latitude):
    with pytest.raises(ValueError):preserve_frozen_projection([[latitude,116.3]],[[39.9,116.3]])
