import pytest
from preprocess.mtnet_endpoints import load_endpoints
from preprocess.dpmm_city import projection

def test_sparse_source_order(tmp_path):
    p=tmp_path/'times.csv';p.write_text('source_index,start_ts,end_ts\n5,10,20\n2,1,3\n')
    rows=load_endpoints(p,[2,5],[1,0])
    assert [(r['id'],r['start_ts']) for r in rows]==[(1,10),(2,1)]

def test_missing_source(tmp_path):
    p=tmp_path/'times.csv';p.write_text('source_index,start_ts,end_ts\n5,10,20\n')
    with pytest.raises(ValueError,match='Missing'):load_endpoints(p,[2,5],[0])

def test_projection():
    assert projection({'dataset':'beijing'})==(50,'S')
    assert projection({'dataset':'porto','routing_crs':{'network_srs':'EPSG:32629'},'bbox':[41.1,41.2,-8.7,-8.55]})==(29,'T')
