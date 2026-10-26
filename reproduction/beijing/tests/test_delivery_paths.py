import hashlib
import importlib.util
import json
from pathlib import Path
import pytest
import gzip
import pickle
import os
from preprocess.dataset_contract import validate_dataset

def test_delivery_archive_includes_runtime_contracts_and_excludes_runs(tmp_path,monkeypatch,capsys):
    import sys,zipfile
    from tools import package_delivery as package
    required=['manifest.json','pytest.ini','README.md','requirements-clean-windows-py313.txt',
              'plotting/plot_matrix.py','plotting/specs/full_27x48.json','deployment/MemoryGuard.ps1']
    excluded=['environment_freeze.txt','validation/report.json','setup_logs/install.txt',
              '.venv/secret.py','plotting/__pycache__/plot.pyc','results/formal.json']
    root=tmp_path/'candidate';root.mkdir()
    for rel in required+excluded:
        f=root/rel;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(rel.encode())
    archive=tmp_path/'candidate.zip'
    monkeypatch.setattr(package,'ROOT',root)
    monkeypatch.setattr(sys,'argv',['package_delivery.py','--out',str(archive)])
    package.main()
    with zipfile.ZipFile(archive) as z:
        assert set(z.namelist())==set(required)|{'delivery_package_manifest.json'}
        import json
        meta=json.loads(z.read('delivery_package_manifest.json'))
        assert meta['file_count']==len(required)
        for rel,entry in meta['files'].items():
            assert hashlib.sha256(z.read(rel)).hexdigest()==entry['sha256']
            assert len(z.read(rel))==entry['bytes']
    with pytest.raises(FileExistsError):package.main()

def test_runtime_binding_refuses_changed_libraries_and_system_environment(tmp_path,monkeypatch):
    import deployment.configure_windows_runtime as runtime
    monkeypatch.setattr(runtime.sys,'platform','win32')
    monkeypatch.setattr(runtime.sys,'prefix',str(tmp_path/'venv'))
    monkeypatch.setattr(runtime.sys,'base_prefix',str(tmp_path/'base'))
    site=tmp_path/'site';site.mkdir()
    monkeypatch.setattr(runtime.sysconfig,'get_path',lambda _:str(site))
    dlls=tmp_path/'resources/runtime';dlls.mkdir(parents=True)
    files={}
    for name in ('msvcp140.dll','msvcp140_1.dll','msvcp140_2.dll','vcruntime140.dll','vcruntime140_1.dll'):
        (dlls/name).write_bytes(b'bound fixture')
        files['resources/runtime/'+name]=hashlib.sha256(b'bound fixture').hexdigest()
    (tmp_path/'resources/binding.json').write_text(json.dumps({'files':files}))
    runtime.configure(tmp_path)
    pth=site/'beijing_runtime.pth';before=pth.read_bytes()
    runtime.configure(tmp_path)
    assert pth.read_bytes()==before
    (dlls/'msvcp140.dll').write_bytes(b'changed')
    with pytest.raises(ValueError,match='changed'):runtime.configure(tmp_path)
    assert pth.read_bytes()==before
    monkeypatch.setattr(runtime.sys,'prefix',runtime.sys.base_prefix)
    with pytest.raises(RuntimeError,match='non-isolated'):runtime.configure(tmp_path)

def test_preflight_detects_missing_matcher_companion(tmp_path):
    import preflight
    import sys
    if sys.platform!='win32':pytest.skip('Windows matcher runtime')
    paths={'stmatch':str(tmp_path/'stmatch.exe'),'runtime':str(tmp_path)}
    (tmp_path/'stmatch.exe').write_bytes(b'fixture')
    assert any('FMMLIB.dll' in e for e in preflight.matcher_dependencies(paths))
    for name in ('FMMLIB.dll','gdal204.dll','boost_serialization.dll'):
        (tmp_path/name).write_bytes(b'fixture')
    assert preflight.matcher_dependencies(paths)==[]

def test_migrated_network_keeps_identity(tmp_path):
    data=tmp_path/'dataset';data.mkdir();graph=tmp_path/'network.shp';graph.write_bytes(b'graph')
    values={'source_indices.json':[42,43],'train_split.json':{'indices':[0]},'test_split.json':{'indices':[1]},'bbox.json':{}}
    names=['trajectories.pkl','trajectories.pkl.gz','road_records.pkl.gz','train.pkl','test.pkl',*values]
    hashes={}
    for name in names:
        f=data/name;f.write_text(json.dumps(values.get(name,[])));hashes[name]=hashlib.sha256(f.read_bytes()).hexdigest()
    m={'schema':'frozen-road-dataset-v1','status':'FROZEN','trajectory_count':2,'train_count':1,'test_count':1,'artifacts':hashes,'network':'Z:/does/not/exist.shp','network_sha256':hashlib.sha256(graph.read_bytes()).hexdigest()}
    manifest=data/'canonical_manifest.json';manifest.write_text(json.dumps(m));before=manifest.read_bytes()
    (data/'network_location.json').write_text(json.dumps({'relative_path':'../network.shp'}))
    assert validate_dataset(data)['dataset_id']==hashlib.sha256(before).hexdigest()
    assert manifest.read_bytes()==before
    graph.write_bytes(b'wrong')
    with pytest.raises(ValueError,match='graph changed'):validate_dataset(data,verify_hashes=True)

def test_scoring_core_comes_from_bundle(monkeypatch):
    monkeypatch.delenv('DFR_LEGACY_ROOT',raising=False)
    root=Path(__file__).resolve().parents[1]
    spec=importlib.util.spec_from_file_location('delivery_scorer',root/'tools/evaluate_saved_roads.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    assert mod.CORE_PATH.resolve()==(root/'legacy/evaluation/route_metric_core.py').resolve()
    assert mod.CORE_PATH.is_file()

def test_bundled_edge_scorer_executes_without_original_checkout(tmp_path, monkeypatch):
    monkeypatch.delenv('DFR_LEGACY_ROOT', raising=False)
    root=Path(__file__).resolve().parents[1]
    spec=importlib.util.spec_from_file_location('portable_edge_scorer',root/'tools/compute_edge_route_metrics.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    cache={'edge_nodes':{1:(0,1),2:(1,2),3:(1,3)},'outdegree':{0:1,1:2,2:0,3:0},
           **{key:{i:i for i in range(4)} for key in ('labels24','labels96','labels384')}}
    real=[{'accepted':True,'cpath':[1,2]},{'accepted':True,'cpath':[1,3]}]
    for name,value in [('cache',cache),('real',real),('synthetic',real+[{'accepted':False,'cpath':[]}])]:
        with gzip.open(tmp_path/(name+'.pkl.gz'),'wb') as f:pickle.dump(value,f)
    result=mod.score_pair(tmp_path/'real.pkl.gz',tmp_path/'synthetic.pkl.gz',tmp_path/'cache.pkl.gz')
    assert result['RoadYield']==pytest.approx(2/3)
    assert result['EdgeCPC']==pytest.approx(1)
    import route_metric_core
    assert Path(route_metric_core.__file__).resolve()==(root/'legacy/evaluation/route_metric_core.py').resolve()


@pytest.mark.parametrize('router',['Nearest','STMatch','FMM'])
def test_actual_evaluate_entrypoint_in_clean_environment(tmp_path,router):
    import subprocess
    import sys
    import geopandas as gpd
    from shapely.geometry import LineString
    root=Path(__file__).resolve().parents[1]
    cache={'edge_nodes':{1:(0,1),2:(1,2),3:(1,3)},'outdegree':{0:1,1:2,2:0,3:0},
           **{key:{i:i for i in range(4)} for key in ('labels24','labels96','labels384')}}
    real=[{'accepted':True,'cpath':[1,2]},{'accepted':True,'cpath':[1,3]}]
    for name,value in [('cache',cache),('real',real),('synthetic',real+[{'accepted':False,'cpath':[]}])]:
        with gzip.open(tmp_path/(name+'.pkl.gz'),'wb') as f:pickle.dump(value,f)
    network=tmp_path/'network.shp'
    graph=gpd.GeoDataFrame({'id':[1,2,3],'source':[0,1,1],'target':[1,2,3],'length_m':[100.,100.,100.],
                           'osm_way':['fixture-a','fixture-b','fixture-c'],'highway':['residential']*3},
        geometry=[LineString([(116.,40.),(116.001,40.)]),LineString([(116.001,40.),(116.002,40.)]),
                  LineString([(116.001,40.),(116.001,40.001)])],crs='EPSG:4326').to_crs('EPSG:32650')
    graph['length_m']=graph.length
    graph.to_file(network)
    # Exhaustive directed shortest paths for this three-edge fixture only.
    # UBODT stores internal zero-based edge indices, not public edge IDs.
    lengths=list(graph.length)
    table=[(0,1,1,0,0,lengths[0]),(1,2,2,1,1,lengths[1]),(1,3,3,1,2,lengths[2]),
           (0,2,1,1,0,lengths[0]+lengths[1]),(0,3,1,1,0,lengths[0]+lengths[2])]
    ubodt=tmp_path/'ubodt.txt'
    ubodt.write_text('source;target;first_n;prev_n;next_e;cost\n'+''.join(';'.join(map(str,r))+'\n' for r in table))
    config=tmp_path/'fixture.json'
    config.write_text(json.dumps({'batch':'isolated-test-not-beijing-results','paths':{
        'output':str(tmp_path/'outputs'),'legacy':str(root/'legacy'),
        'metric_real_routes':str(tmp_path/'real.pkl.gz'),'metric_cache':str(tmp_path/'cache.pkl.gz'),
        'metric_network':str(network),'network':str(network),'edge_cache':str(tmp_path/'cache.pkl.gz'),
            'stmatch':str(root/'resources/stmatch/stmatch.exe'),'runtime':os.environ.get('DFR_TEST_RUNTIME',str(root/'resources/runtime')),
        'fmm':str(root/'resources/fmm/fmm.exe'),'ubodt':str(ubodt),
        'prepared':str(tmp_path),'dataset':'unused'},'dataset':'isolated_fixture'}),encoding='utf-8')
    measurement=tmp_path/'saved measurement';measurement.mkdir()
    with (measurement/'measurement.pkl').open('wb') as f:
        pickle.dump([[[40.,116.0005],[40.,116.0015]],[[40.,116.0005],[40.0005,116.001]],[]],f)
    (measurement/'measurement_manifest.json').write_text('{"classification":"TEST_FIXTURE"}',encoding='utf-8')
    routed=tmp_path/'actual route'
    route_command=[sys.executable,str(root/'route.py'),'--config',str(config),'--method','SPRT',
                   '--router',router,'--input',str(measurement),'--out',str(routed)]
    route_result=subprocess.run(route_command,cwd=tmp_path,capture_output=True,text=True,encoding='utf-8',timeout=60)
    assert route_result.returncode==0,route_result.stderr
    route_manifest=json.loads((routed/'route_manifest.json').read_text(encoding='utf-8'))
    assert route_manifest['status']=='VALID' and route_manifest['records']==3
    assert route_manifest['raw_source_used'] is False
    assert route_manifest['reasons']['accepted']==2
    with gzip.open(routed/'synthetic_routes.pkl.gz','rb') as f:routed_records=pickle.load(f)
    if router=='Nearest':
        assert [list(row['cpath']) for row in routed_records]==[[1,2],[1,3],[]]
    else:
        # HMM matching need not equal independent nearest-edge snapping.
        assert all(row['cpath'] and set(row['cpath']) <= {1,2,3} for row in routed_records[:2])
        assert not routed_records[2]['cpath']
        executable=root/'resources'/router.lower()/(router.lower()+'.exe')
        assert route_manifest['public_executable_sha256']==hashlib.sha256(executable.read_bytes()).hexdigest()
    out=tmp_path/'score with spaces'
    command=[sys.executable,str(root/'evaluate.py'),'--config',str(config),'--method','SPRT',
             '--router',router,'--input',str(routed/'synthetic_routes.pkl.gz'),'--out',str(out)]
    result=subprocess.run(command,cwd=tmp_path,capture_output=True,text=True,encoding='utf-8',timeout=60)
    assert result.returncode==0,result.stderr
    manifest=json.loads((out/'manifest.json').read_text(encoding='utf-8'))
    assert manifest['synthetic']['slots']==3
    assert manifest['synthetic']['valid_routes']==2
    assert manifest['metric_count']==24
    assert manifest['rematched'] is False and manifest['gap_filling'] is False
    assert Path(manifest['metric_core']['path'])==(root/'legacy/evaluation/route_metric_core.py')
    for entry in manifest['outputs'].values():
        assert hashlib.sha256(Path(entry['path']).read_bytes()).hexdigest()==entry['sha256']
    before=(out/'manifest.json').read_bytes()
    repeat=subprocess.run(command,cwd=tmp_path,capture_output=True,text=True,encoding='utf-8',timeout=60)
    assert repeat.returncode!=0
    assert (out/'manifest.json').read_bytes()==before

    if router=='Nearest':
        # Exercise the independent ordered-physical entrypoint with a fully
        # hash-bound artificial population, including the synthetic empty slot.
        prepared=tmp_path/'frozen fixture';prepared.mkdir()
        values={'source_indices.json':[10,11,12],
                'train_split.json':{'indices':[0,1]},'test_split.json':{'indices':[2]},
                'bbox.json':{'bbox':[39.9,40.1,115.9,116.1]}}
        for name,value in values.items():
            (prepared/name).write_text(json.dumps(value),encoding='utf-8')
        for name in ('trajectories.pkl','trajectories.pkl.gz','train.pkl','test.pkl'):
            opener=gzip.open if name.endswith('.gz') else open
            with opener(prepared/name,'wb') as handle:pickle.dump([],handle)
        with gzip.open(prepared/'road_records.pkl.gz','wb') as handle:
            pickle.dump(real+[real[0]],handle)
        artifacts={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in prepared.iterdir()}
        canonical={'schema':'frozen-road-dataset-v1','status':'FROZEN',
                   'trajectory_count':3,'train_count':2,'test_count':1,'artifacts':artifacts,
                   'network':str(network),'network_sha256':hashlib.sha256(network.read_bytes()).hexdigest()}
        manifest_path=prepared/'canonical_manifest.json'
        manifest_path.write_text(json.dumps(canonical),encoding='utf-8')
        physical_config=json.loads(config.read_text())
        physical_config.update(slots=3,frozen_dataset_id=hashlib.sha256(manifest_path.read_bytes()).hexdigest())
        physical_config['paths'].update(prepared=str(prepared),real_routes=str(prepared/'road_records.pkl.gz'))
        physical_config_path=tmp_path/'physical_fixture.json'
        physical_config_path.write_text(json.dumps(physical_config),encoding='utf-8')
        physical_out=tmp_path/'physical score'
        physical_command=[sys.executable,str(root/'evaluate_physical.py'),'--config',str(physical_config_path),
                          '--method','SPRT','--router',router,'--input',str(routed/'synthetic_routes.pkl.gz'),
                          '--out',str(physical_out)]
        physical_result=subprocess.run(physical_command,cwd=tmp_path,capture_output=True,text=True,encoding='utf-8',timeout=60)
        assert physical_result.returncode==0,physical_result.stderr
        binding=json.loads((physical_out/'input_binding.json').read_text())
        assert binding['real_slots']==binding['synthetic_slots']==binding['valid_real_slots']==3
        assert binding['dataset_id']==physical_config['frozen_dataset_id']
        physical_manifest=json.loads((physical_out/'manifest.json').read_text())
        assert physical_manifest['protocol']=='full_od_ordered_physical_mass_v1'
        assert physical_manifest['results_sha256']==hashlib.sha256((physical_out/'results.csv').read_bytes()).hexdigest()
        import csv
        with (physical_out/'results.csv').open() as handle:physical_row=next(csv.DictReader(handle))
        assert float(physical_row['RoadYield'])==pytest.approx(2/3)
        repeat_physical=subprocess.run(physical_command,cwd=tmp_path,capture_output=True,text=True,encoding='utf-8',timeout=60)
        assert repeat_physical.returncode!=0

        coords=[[[40.,116.0005],[40.,116.0015]],
                [[40.,116.0005],[40.0005,116.001]],
                [[40.,116.0005],[40.,116.0015]]]
        for name in ('trajectories.pkl','trajectories.pkl.gz','train.pkl','test.pkl'):
            opener=gzip.open if name.endswith('.gz') else open
            subset=coords[:2] if name=='train.pkl' else coords[2:] if name=='test.pkl' else coords
            with opener(prepared/name,'wb') as handle:pickle.dump(subset,handle)
            canonical['artifacts'][name]=hashlib.sha256((prepared/name).read_bytes()).hexdigest()
        manifest_path.write_text(json.dumps(canonical),encoding='utf-8')
        physical_config['frozen_dataset_id']=hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        osm=tmp_path/'coordinate_public_osm.pkl'
        with osm.open('wb') as handle:
            pickle.dump([{'id':1,'geometry':[{'lat':40.,'lon':116.},{'lat':40.,'lon':116.002}]},
                         {'id':2,'geometry':[{'lat':40.,'lon':116.001},{'lat':40.001,'lon':116.001}]}],handle)
        physical_config.update(bbox=[39.999,40.002,115.999,116.003],evaluation_seed=20260713)
        physical_config['paths'].update(real=str(prepared/'trajectories.pkl'),osm=str(osm))
        coordinate_m=Path(physical_config['paths']['output'])/physical_config['batch']/'measurements/SPRT'
        coordinate_m.mkdir(parents=True)
        (coordinate_m/'measurement.pkl').write_bytes((measurement/'measurement.pkl').read_bytes())
        physical_config_path.write_text(json.dumps(physical_config),encoding='utf-8')
        coordinate_out=tmp_path/'coordinate score'
        coordinate_run=subprocess.run([sys.executable,str(root/'evaluate_coordinates.py'),
            '--config',str(physical_config_path),'--method','SPRT','--router','Origin',
            '--metric-protocol','audit-v2','--out',str(coordinate_out)],cwd=tmp_path,
            capture_output=True,text=True,encoding='utf-8',timeout=90)
        assert coordinate_run.returncode==0,coordinate_run.stderr
        coordinate_manifest=json.loads((coordinate_out/'manifest.json').read_text())
        assert coordinate_manifest['outputs']['metrics.json']==hashlib.sha256((coordinate_out/'metrics.json').read_bytes()).hexdigest()

        # Derive the split audit and train-only lineage by executing the real
        # preparation/generation entrypoints; do not fabricate passing records.
        physical_config.update(train_slots=2,epsilon=1.4,seed=42)
        physical_config['paths'].update(train=str(prepared/'train.pkl'),test=str(prepared/'test.pkl'))
        physical_config_path.write_text(json.dumps(physical_config),encoding='utf-8')
        split_out=tmp_path/'verified split'
        tstr_config=tmp_path/'tstr_fixture.json'
        split_run=subprocess.run([sys.executable,str(root/'prepare_tstr_split.py'),
            '--config',str(physical_config_path),'--out',str(split_out),'--out-config',str(tstr_config)],
            cwd=tmp_path,capture_output=True,text=True,encoding='utf-8',timeout=60)
        assert split_run.returncode==0,split_run.stderr
        train_m=tmp_path/'train-only M'
        generation_run=subprocess.run([sys.executable,str(root/'synthesize.py'),
            '--config',str(tstr_config),'--method','DPStd','--train-only','--out',str(train_m)],
            cwd=tmp_path,capture_output=True,text=True,encoding='utf-8',timeout=90)
        assert generation_run.returncode==0,generation_run.stderr
        tstr_out=tmp_path/'strict tstr score'
        tstr_command=[sys.executable,str(root/'evaluate_tstr.py'),'--config',str(tstr_config),
            '--method','DPStd','--router','Origin','--input',str(train_m/'measurement.pkl'),
            '--lineage',str(train_m/'lineage.json'),'--metric-protocol','audit-v2','--out',str(tstr_out)]
        tstr_run=subprocess.run(tstr_command,cwd=tmp_path,capture_output=True,text=True,encoding='utf-8',timeout=90)
        assert tstr_run.returncode==0,tstr_run.stderr
        tstr_manifest=json.loads((tstr_out/'manifest.json').read_text())
        assert tstr_manifest['synthesis_lineage_verified'] is True
        assert tstr_manifest['disjoint_split_verified'] is True
        assert tstr_manifest['results_sha256']==hashlib.sha256((tstr_out/'results.csv').read_bytes()).hexdigest()
        lineage=json.loads((train_m/'lineage.json').read_text())
        lineage['input_policy']='full_corpus'
        bad_lineage=tmp_path/'invalid_full_corpus_lineage.json'
        bad_lineage.write_text(json.dumps(lineage),encoding='utf-8')
        bad_tstr=list(tstr_command)
        bad_tstr[bad_tstr.index('--lineage')+1]=str(bad_lineage)
        rejected_tstr=tmp_path/'rejected tstr'
        bad_tstr[-1]=str(rejected_tstr)
        bad_tstr_run=subprocess.run(bad_tstr,cwd=tmp_path,capture_output=True,text=True,encoding='utf-8',timeout=60)
        assert bad_tstr_run.returncode!=0 and 'Unknown generator input policy' in bad_tstr_run.stderr
        assert not rejected_tstr.exists()

        native_out=tmp_path/'native DFR'
        # The preserved DFR protocol samples all 384 fine cells; a three-edge
        # graph is outside its domain. Reject it early, then supply a public
        # 384-node directed cycle without changing any algorithm parameter.
        from synthesize_dfr import validate_endpoint_support
        with pytest.raises(ValueError,match='384 public endpoint cells'):
            validate_endpoint_support(tmp_path/'cache.pkl.gz')
        import math
        import shutil
        ring=[(116.+.01*math.cos(i*2*math.pi/384),40.+.01*math.sin(i*2*math.pi/384)) for i in range(384)]
        dfr_graph=gpd.GeoDataFrame({'id':list(range(1,385)),'source':list(range(384)),
            'target':[(i+1)%384 for i in range(384)],'osm_way':['fixture-ring']*384,
            'highway':['residential']*384},geometry=[LineString([ring[i],ring[(i+1)%384]]) for i in range(384)],crs='EPSG:4326').to_crs('EPSG:32650')
        dfr_graph['length_m']=dfr_graph.length
        dfr_network=tmp_path/'dfr_network.shp';dfr_graph.to_file(dfr_network)
        dfr_cache={'edge_nodes':{i+1:(i,(i+1)%384) for i in range(384)},
                   'labels384':{i:i for i in range(384)},'labels24':{i:i//16 for i in range(384)},
                   'labels96':{i:i//4 for i in range(384)},'outdegree':{i:1 for i in range(384)}}
        dfr_cache_path=tmp_path/'dfr_cache.pkl.gz'
        with gzip.open(dfr_cache_path,'wb') as handle:pickle.dump(dfr_cache,handle)
        dfr_prepared=tmp_path/'dfr artificial population';shutil.copytree(prepared,dfr_prepared)
        dfr_coords=[[[ring[j][1],ring[j][0]] for j in range(i,i+3)] for i in range(3)]
        for name in ('trajectories.pkl','trajectories.pkl.gz','train.pkl','test.pkl'):
            opener=gzip.open if name.endswith('.gz') else open
            subset=dfr_coords[:2] if name=='train.pkl' else dfr_coords[2:] if name=='test.pkl' else dfr_coords
            with opener(dfr_prepared/name,'wb') as handle:pickle.dump(subset,handle)
        with gzip.open(dfr_prepared/'road_records.pkl.gz','wb') as handle:
            pickle.dump([{'accepted':True,'cpath':[i+1,i+2]} for i in range(3)],handle)
        dfr_canonical=dict(canonical,network=str(dfr_network),network_sha256=hashlib.sha256(dfr_network.read_bytes()).hexdigest(),
            artifacts={name:hashlib.sha256((dfr_prepared/name).read_bytes()).hexdigest() for name in canonical['artifacts']})
        (dfr_prepared/'canonical_manifest.json').write_text(json.dumps(dfr_canonical),encoding='utf-8')
        dfr_config=dict(physical_config,paths=dict(physical_config['paths'],prepared=str(dfr_prepared),
            network=str(dfr_network),metric_cache=str(dfr_cache_path)),
            frozen_dataset_id=hashlib.sha256((dfr_prepared/'canonical_manifest.json').read_bytes()).hexdigest())
        dfr_config_path=tmp_path/'dfr_config.json';dfr_config_path.write_text(json.dumps(dfr_config),encoding='utf-8')
        dfr_run=subprocess.run([sys.executable,str(root/'synthesize_dfr.py'),
            '--config',str(dfr_config_path),'--out',str(native_out)],cwd=tmp_path,
            capture_output=True,text=True,encoding='utf-8',timeout=90)
        assert dfr_run.returncode==0,dfr_run.stderr
        native_manifest_path=native_out/'seed_42/manifest.json'
        native_manifest=json.loads(native_manifest_path.read_text())
        assert native_manifest['fixed_output_slots']==3
        assert native_manifest['privacy']['epsilon']==1.4
        for filename,digest in native_manifest['outputs'].items():
            assert hashlib.sha256((native_manifest_path.parent/filename).read_bytes()).hexdigest().lower()==digest.lower()
        with gzip.open(native_manifest_path.parent/'road_routes.pkl.gz','rb') as handle:native_routes=pickle.load(handle)
        assert len(native_routes)==3
        public_edges=set(dfr_cache['edge_nodes'].values())
        assert all(route and all(tuple(edge) in public_edges for edge in route) for route in native_routes)
        assert all(all(a[1]==b[0] for a,b in zip(route,route[1:])) for route in native_routes)
        dfr_audit=json.loads((native_out.with_name(native_out.name+'.private_audit')/'input_lineage.json').read_text())
        assert dfr_audit['status']=='DONE' and dfr_audit['dataset']['dataset_id']==dfr_config['frozen_dataset_id']

        # Both outgoing branches cross the same public region boundary, so
        # this fixture supplies a real two-option road-choice context.
        task_cache=dict(cache,labels384={0:0,1:1,2:2,3:2})
        task_cache_path=tmp_path/'task_cache.pkl.gz'
        with gzip.open(task_cache_path,'wb') as handle:pickle.dump(task_cache,handle)
        physical_config['paths'].update(metric_cache=str(task_cache_path),
                                       metric_real_routes=str(prepared/'road_records.pkl.gz'))
        physical_config_path.write_text(json.dumps(physical_config),encoding='utf-8')
        task_score=tmp_path/'task prerequisite score'
        score_run=subprocess.run([sys.executable,str(root/'evaluate.py'),'--config',str(physical_config_path),
            '--method','SPRT','--router',router,'--input',str(routed/'synthetic_routes.pkl.gz'),
            '--out',str(task_score)],cwd=tmp_path,capture_output=True,text=True,encoding='utf-8',timeout=60)
        assert score_run.returncode==0,score_run.stderr
        task_out=tmp_path/'road tasks'
        task_command=[sys.executable,str(root/'evaluate_road_tasks.py'),'--config',str(physical_config_path),
            '--method','SPRT','--router',router,'--input',str(routed/'synthetic_routes.pkl.gz'),
            '--score-manifest',str(task_score/'manifest.json'),'--out',str(task_out)]
        task_run=subprocess.run(task_command,cwd=tmp_path,capture_output=True,text=True,encoding='utf-8',timeout=60)
        assert task_run.returncode==0,task_run.stderr
        task_manifest=json.loads((task_out/'manifest.json').read_text())
        assert task_manifest['real_slots']==task_manifest['synthetic_slots']==3
        assert task_manifest['result_sha256']==hashlib.sha256((task_out/'metrics.json').read_bytes()).hexdigest()
        task_metrics=json.loads((task_out/'metrics.json').read_text())['metrics']
        assert task_metrics['RoadEvidenceYield']==pytest.approx(2/3)
        assert 'NextRoadAcc' in task_metrics and 'RC-NDCG' in task_metrics
        assert Path(task_manifest['metric_core']['path']).is_relative_to(root/'legacy')
        # A changed upstream input must be rejected before writing any scores.
        task_cache['labels384'][3]=3
        with gzip.open(task_cache_path,'wb') as handle:pickle.dump(task_cache,handle)
        mismatch_out=tmp_path/'rejected task scores'
        bad_run=subprocess.run(task_command[:-1]+[str(mismatch_out)],cwd=tmp_path,
                               capture_output=True,text=True,encoding='utf-8',timeout=60)
        assert bad_run.returncode!=0 and 'Road score input changed' in bad_run.stderr
        assert not mismatch_out.exists()


@pytest.mark.parametrize('method',['DPStd','SPRT','PrivTrace','DPTraj-PM'])
def test_actual_measurement_entrypoint_without_original_checkout(tmp_path,method):
    import subprocess
    import sys
    root=Path(__file__).resolve().parents[1]
    prepared=tmp_path/'prepared';prepared.mkdir()
    trajectories=[[[40.,116.0005],[40.,116.0015]],[[40.,116.0005],[40.0005,116.001]]]*8
    if method=='PrivTrace':
        # Original fixed level1_parameter=12500 requires >=50000 points.
        # Supply artificial data meeting that domain; never alter the algorithm threshold.
        trajectories=[[[40.+i*0.00002,116.0005+i*0.00003] for i in range(30)],
                      [[40.0006-i*0.00002,116.0005+i*0.00003] for i in range(30)]]*850
    with (prepared/'trajectories.pkl').open('wb') as f:pickle.dump(trajectories,f)
    (prepared/'bbox.json').write_text(json.dumps({'bbox':[39.999,40.002,115.999,116.003]}))
    osm=tmp_path/'public_fixture_osm.pkl'
    with osm.open('wb') as f:
        pickle.dump([{'id':1,'geometry':[{'lat':40.,'lon':116.},{'lat':40.,'lon':116.002}]},
                     {'id':2,'geometry':[{'lat':40.,'lon':116.001},{'lat':40.001,'lon':116.001}]}],f)
    config=tmp_path/'measurement_fixture.json'
    config.write_text(json.dumps({'dataset':'isolated_fixture','batch':'not_formal_results',
        'slots':3,'epsilon':1.4,'seed':42,'paths':{'output':str(tmp_path/'outputs'),
        'legacy':str(root/'legacy'),'prepared':str(prepared),'osm':str(osm)}}))
    out=tmp_path/'M only'
    result=subprocess.run([sys.executable,str(root/'synthesize.py'),'--config',str(config),
        '--method',method,'--out',str(out)],cwd=tmp_path,capture_output=True,text=True,encoding='utf-8',timeout=90)
    assert result.returncode==0,result.stderr
    manifest=json.loads((out/'measurement_manifest.json').read_text(encoding='utf-8'))
    assert manifest['public_slot_count']==3
    if method!='DPTraj-PM':assert manifest['status']=='VALID'
    assert manifest['M']==method
    data=out/'measurement.pkl'
    assert hashlib.sha256(data.read_bytes()).hexdigest()==manifest['outputs']['measurement.pkl']
    with data.open('rb') as f:assert len(pickle.load(f))==3
    assert not list(out.rglob('route_manifest.json'))
    assert not list(out.rglob('metrics.json'))


@pytest.mark.parametrize('failure',['missing_import','wrong_slots'])
def test_matcher_deployment_failure_has_final_invalid_evidence(tmp_path,monkeypatch,failure):
    from algorithms.routers import public_match_adapter as adapter
    measurement=tmp_path/'measurement.pkl'
    with measurement.open('wb') as f:pickle.dump([[[40.,116.],[40.,116.001]]],f)
    for name in ('network.shp','matcher.exe','cache.gz'):(tmp_path/name).write_bytes(b'test fixture')
    if failure=='missing_import':
        def missing(_):raise ModuleNotFoundError('isolated missing matcher dependency')
        monkeypatch.setattr(adapter,'_load_legacy_run_fmm',missing)
        expected=ModuleNotFoundError
    else:
        monkeypatch.setattr(adapter,'_load_legacy_run_fmm',lambda _:lambda *a:([],{'fixture':True}))
        expected=RuntimeError
    out=tmp_path/'failed'
    with pytest.raises(expected):
        adapter.run_public_match(measurement,out,matcher='STMatch',network=tmp_path/'network.shp',
            executable=tmp_path/'matcher.exe',edge_cache=tmp_path/'cache.gz',legacy_root=tmp_path)
    manifest=json.loads((out/'route_manifest.json').read_text(encoding='utf-8'))
    assert manifest['status']=='INVALID'
    assert manifest['error_type']==expected.__name__
    assert not (out/'synthetic_routes.pkl.gz').exists()


def test_mm2_public_mapping_is_required_and_bound(tmp_path):
    from preflight import matcher_dependencies
    root=Path(__file__).resolve().parents[1]
    assert any('MM2 public node mapping' in error for error in
               matcher_dependencies({'mm2_network':str(tmp_path/'network')}))
    mapping=tmp_path/'public_graph/inputs/public_edge_nodes.json'
    mapping.parent.mkdir(parents=True)
    mapping.write_text('{}')
    assert not matcher_dependencies({'mm2_network':str(tmp_path/'network')})
    binding=json.loads((root/'resources/mm2/binding.json').read_text())
    relative='resources/mm2/public_graph/inputs/public_edge_nodes.json'
    assert hashlib.sha256((root/relative).read_bytes()).hexdigest()==binding['files'][relative]
