import csv
import json
import pickle
import gzip
import subprocess
from pathlib import Path
import pytest
from algorithms.routers.mm2_mdp_adapter import mm2_command,prepare_resume,resource_binding,MM2_FIELDS


@pytest.mark.parametrize('threads',[1,2,4,8])
def test_native_threads_not_omp_only(threads):
    command=mm2_command(Path('mm2'),Path('network'),Path('tracks'),Path('out'),tracks_srs='32629',network_srs='32629',threads=threads)
    assert command[command.index('--threads')+1]==str(threads)


@pytest.mark.parametrize('srs', ['EPSG:32650', 'EPSG:32629'])
def test_default_light_options_for_both_cities(srs):
    command=mm2_command(Path('mm2'),Path('network'),Path('tracks'),Path('out'),tracks_srs=srs,network_srs=srs)
    assert command[command.index('--threads')+1]=='4'
    assert command[command.index('--candidate-adoption')+1]=='off'
    assert command[command.index('--simplify-track')+1]=='on'
    assert command[command.index('--model')+1]=='value-iteration'
    assert command[command.index('--join-merges')+1]=='on'
    assert command[command.index('--concatenate-skips')+1]=='off'
    assert command[command.index('--within-edge-turns')+1]=='off'


def test_wsl_keeps_light_options_as_flags(monkeypatch):
    import ntpath
    from types import SimpleNamespace
    from algorithms.routers import mm2_mdp_adapter as adapter
    binary=Path('E:/mm2/tool.AppImage');network=Path('E:/roads/network')
    tracks=Path('E:/tracks.csv');output=Path('E:/out')
    monkeypatch.setattr(adapter,'os',SimpleNamespace(name='nt',path=ntpath))
    command=adapter.mm2_command(binary,network,tracks,output,tracks_srs='32629',network_srs='32629')
    assert command[:2]==['wsl.exe','--']
    assert command[command.index('--candidate-adoption')+1]=='off'
    assert command[command.index('--simplify-track')+1]=='on'
    assert command[command.index('--threads')+1]=='4'


@pytest.mark.parametrize('threads',[0,-1,True,1.5])
def test_invalid_threads_rejected(threads):
    with pytest.raises(ValueError):mm2_command(Path('mm2'),Path('n'),Path('t'),Path('o'),tracks_srs='32629',network_srs='32629',threads=threads)


def fixture(tmp):
    old=tmp/'old';(old/'mm2_run').mkdir(parents=True)
    tracks=tmp/'tracks.csv'
    with tracks.open('w',newline='',encoding='utf-8') as f:
        writer=csv.writer(f);writer.writerow(['id','geometry'])
        for i in range(3):writer.writerow([i,'LINESTRING(0 0,1 1)'])
    (old/'mm2_tracks.csv').write_bytes(tracks.read_bytes())
    cmd=mm2_command(Path('mm2'),Path('network'),tracks,Path('out'),tracks_srs='32629',network_srs='32629',threads=1)
    (old/'mm2_command.json').write_text(json.dumps(cmd))
    (old/'mm2_resources.json').write_text(json.dumps({'schema':1}))
    with (old/'mm2_run/matches.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.writer(f);w.writerow(MM2_FIELDS);w.writerow([0,'no','1','LINESTRING(0 0,1 1)','2'])
    return old,tracks,cmd


def test_resume_skips_only_complete_same_input_ids(tmp_path):
    old,tracks,cmd=fixture(tmp_path)
    with (old/'mm2_run/matches.csv').open('ab') as f:f.write(b'1,no,1,"LINESTRING(')
    cmd[cmd.index('--threads')+1]='4'
    result=prepare_resume(old,tracks,tmp_path/'pending.csv',tmp_path/'saved.csv',cmd,{0,1,2},{'schema':1})
    assert result['reused_records']==1 and result['remaining_records']==2
    assert result['discarded_partial_bytes']>0
    with (tmp_path/'pending.csv').open(newline='') as f:assert [int(r['id']) for r in csv.DictReader(f)]==[1,2]


def test_resume_rejects_different_m_or_routing_settings(tmp_path):
    old,tracks,cmd=fixture(tmp_path)
    tracks.write_text('changed')
    with pytest.raises(ValueError,match='M tracks'):prepare_resume(old,tracks,tmp_path/'p',tmp_path/'s',cmd,{0,1,2})
    tracks.write_bytes((old/'mm2_tracks.csv').read_bytes())
    cmd[cmd.index('--model')+1]='changed'
    with pytest.raises(ValueError,match='routing parameters'):prepare_resume(old,tracks,tmp_path/'p',tmp_path/'s',cmd,{0,1,2})


@pytest.mark.parametrize('reused_rows',[1,3])
def test_resume_runs_missing_global_ids_and_merges_every_slot(tmp_path,monkeypatch,reused_rows):
    from algorithms.routers.mm2_mdp_adapter import run_mm2,write_tracks_csv
    old=tmp_path/'old';(old/'mm2_run').mkdir(parents=True)
    data=tmp_path/'M.pkl';data.write_bytes(pickle.dumps([[[0.,0.],[1.,1.]]]*3))
    cache=tmp_path/'cache.pkl';cache.write_bytes(pickle.dumps({'edge_nodes':{1:(10,20)}}))
    binary=tmp_path/'mm2';binary.write_bytes(b'fake binary')
    network=tmp_path/'network';network.mkdir()
    write_tracks_csv(data,old/'mm2_tracks.csv',input_srs='EPSG:4326',tracks_srs='EPSG:4326')
    cmd=mm2_command(binary,network,old/'mm2_tracks.csv',old/'mm2_run',tracks_srs='4326',network_srs='4326',threads=1)
    (old/'mm2_command.json').write_text(json.dumps(cmd))
    (old/'mm2_resources.json').write_text(json.dumps(resource_binding(binary,network,cache)))
    with (old/'mm2_run/matches.csv').open('w',newline='') as f:
        writer=csv.writer(f);writer.writerow(MM2_FIELDS)
        for i in range(reused_rows):writer.writerow([i,'no',1,'LINESTRING(0 0,1 1)','2'])
    def native(command,**kwargs):
        assert reused_rows<3, 'Fully reused runs must not launch native MM2'
        assert command[command.index('--threads')+1]=='4'
        with Path(command[command.index('--tracks')+1]).open(newline='') as f:ids=[int(row['id']) for row in csv.DictReader(f)]
        assert ids==list(range(reused_rows,3))
        out=Path(command[command.index('--output')+1]);out.mkdir()
        with (out/'matches.csv').open('w',newline='') as f:
            writer=csv.writer(f);writer.writerow(MM2_FIELDS)
            for i in reversed(ids):writer.writerow([i,'no',1,'LINESTRING(0 0,1 1)','2'])
        return subprocess.CompletedProcess(command,0,stdout='',stderr='')
    monkeypatch.setattr('algorithms.routers.mm2_mdp_adapter.subprocess.run',native)
    result=run_mm2(data,tmp_path/'new',executable=binary,network=network,edge_cache=cache,
                  tracks_srs='EPSG:4326',network_srs='EPSG:4326',resume_from=old)
    assert result['records']==3 and result['threads']==4 and result['resume']['reused_records']==reused_rows
    assert result['mm2_executed']==(reused_rows<3)
    if reused_rows==3:
        assert result['route_generation']=='reused_complete_mm2_routes_native_not_executed'
        assert 'all eligible slots reused' in (tmp_path/'new/mm2_stdout.log').read_text()
    with gzip.open(tmp_path/'new/synthetic_routes.pkl.gz','rb') as f:rows=pickle.load(f)
    assert [row['source_index'] for row in rows]==[0,1,2]
    assert all(row['accepted'] for row in rows)


def test_missing_or_changed_resource_binding_rejected(tmp_path):
    old,tracks,cmd=fixture(tmp_path)
    with pytest.raises(ValueError,match='content changed'):
        prepare_resume(old,tracks,tmp_path/'p',tmp_path/'s',cmd,{0,1,2},{'schema':2})
    (old/'mm2_resources.json').unlink()
    with pytest.raises(ValueError,match='binding missing'):
        prepare_resume(old,tracks,tmp_path/'p',tmp_path/'s',cmd,{0,1,2},{'schema':1})


def test_heavy_settings_cannot_be_resumed_as_light(tmp_path):
    old,tracks,command=fixture(tmp_path)
    previous=list(command)
    for flag in ['--candidate-adoption','--simplify-track']:
        i=previous.index(flag);del previous[i:i+2]
    (old/'mm2_command.json').write_text(json.dumps(previous))
    with pytest.raises(ValueError,match='routing parameters differ'):
        prepare_resume(old,tracks,tmp_path/'p',tmp_path/'s',command,{0,1,2})


@pytest.mark.parametrize('part',['binary','network','cache','map'])
def test_same_path_content_replacement_detected(tmp_path,part):
    binary=tmp_path/'mm2';binary.write_bytes(b'old')
    network=tmp_path/'network';network.mkdir(); road=network/'edges';road.write_bytes(b'old')
    cache=tmp_path/'cache';cache.write_bytes(b'old')
    mapping=tmp_path/'public_graph/inputs/public_edge_nodes.json';mapping.parent.mkdir(parents=True);mapping.write_text('{}')
    before=resource_binding(binary,network,cache)
    {'binary':binary,'network':road,'cache':cache,'map':mapping}[part].write_bytes(b'new')
    assert resource_binding(binary,network,cache)!=before
