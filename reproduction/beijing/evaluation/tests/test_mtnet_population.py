import pytest

from prepare_mtnet_frozen import select_population,load_original_adapter


def fixture_population():
    return [2,0,3,1], [dict(id=i+1,timestamp=100+i) for i in range(4)], [
        dict(accepted=True,cpath=[100+i]) for i in range(4)]


def test_train_only_preserves_non_sorted_split_order_and_alignment():
    source,binding,roads=fixture_population()
    records,selected=select_population(source,binding,roads,[3,0])
    assert [r['id'] for r in records]==[1,2]
    assert [r['original_source_index'] for r in records]==[1,2]
    assert [r['frozen_population_index'] for r in records]==[3,0]
    assert [r['timestamp'] for r in records]==[101,102]
    assert [r['cpath'] for r in selected]==[[103],[100]]
    assert binding[1]['id']==2  # Do not mutate the shared timestamp binding.


def test_test_only_bad_timestamp_is_never_read_by_selection():
    source,binding,roads=fixture_population()
    binding[0]={}
    assert len(select_population(source,binding,roads,[3,0])[0])==2


@pytest.mark.parametrize('selection',[[],[0,0],[-1],[4],[True],[1.0]])
def test_invalid_selection_rejected(selection):
    with pytest.raises(ValueError):
        select_population(*fixture_population(),selection)


def test_full_selection_retains_original_order():
    source,binding,roads=fixture_population()
    records,selected=select_population(source,binding,roads,list(range(4)))
    assert [r['original_source_index'] for r in records]==source
    assert selected==roads


def test_selected_failed_road_rejected():
    source,binding,roads=fixture_population()
    roads[0]['accepted']=False
    with pytest.raises(ValueError):
        select_population(source,binding,roads,[0])


def test_author_import_bridges_csv_overflow_and_restores_function(tmp_path,monkeypatch):
    import csv
    calls=[]
    def c_long_limit(value=None):
        if value is not None and value>(1<<31)-1:raise OverflowError('32-bit C long')
        calls.append(value);return 1024
    monkeypatch.setattr(csv,'field_size_limit',c_long_limit)
    file=tmp_path/'adapter.py'
    file.write_text('import csv,sys\ncsv.field_size_limit(sys.maxsize)\nRESULT=7\n')
    assert load_original_adapter('csv_bridge_test',file).RESULT==7
    assert calls==[(1<<31)-1]
    assert csv.field_size_limit is c_long_limit
