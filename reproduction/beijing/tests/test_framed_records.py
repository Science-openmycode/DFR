import gzip,pickle
import numpy as np
import pytest
from preprocess.framed_records import records

def write(path,values):
    with gzip.open(path,'wb') as f:
        f.write(b'\x80\x03]')
        for row in values:f.write(pickle.dumps(row,protocol=3)[2:-1]+b'a')
        f.write(b'.')

def test_stream_and_standard_unpickler_agree(tmp_path):
    values=[np.asarray([[i,i+1]],dtype=float) for i in range(12)]
    p=tmp_path/'v.gz';write(p,values)
    with gzip.open(p,'rb') as f:reference=pickle.load(f)
    actual=list(records(p,12))
    assert all(np.array_equal(a,b) for a,b in zip(actual,reference,strict=True))

def test_stream_count_mismatch(tmp_path):
    p=tmp_path/'v.gz';write(p,[1,2])
    with pytest.raises(ValueError,match='count'):list(records(p,3))

def test_stream_trailing_data(tmp_path):
    p=tmp_path/'v.gz';write(p,[1])
    with gzip.open(p,'ab') as f:f.write(b'junk')
    with pytest.raises(ValueError,match='trailing'):list(records(p,1))

def test_legacy_pickle(tmp_path):
    p=tmp_path/'v.pkl';p.write_bytes(pickle.dumps([1,2],protocol=5))
    assert list(records(p,2))==[1,2]
    with pytest.raises(ValueError,match='Large input'):list(records(p,100001))
