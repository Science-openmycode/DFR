import importlib.util
from pathlib import Path
import sqlite3

spec=importlib.util.spec_from_file_location('exact',Path(__file__).resolve().parents[2]/'tools/convert_dpmm_exact_geometry.py')
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)


def database(rows):
    db=sqlite3.connect(':memory:');db.execute('CREATE TABLE segments(k TEXT,edge INTEGER,source INTEGER,target INTEGER)')
    db.executemany('INSERT INTO segments VALUES (?,?,?,?)',rows);return db


def test_exact_geometry_resolves_direction():
    db=database([(mod.key((116.,39.),(117.,40.)),8,1,2)])
    assert mod.resolve([[39.,116.],[40.,117.]],db)==([8],'valid')
    assert mod.resolve([[40.,117.],[39.,116.]],db)[1]=='no_exact_public_segment'


def test_ambiguity_never_selects_one_edge():
    token=mod.key((116.,39.),(117.,40.));db=database([(token,8,1,2),(token,9,1,2)])
    assert mod.resolve([[39.,116.],[40.,117.]],db)==([],'ambiguous_public_segment')


def test_disconnected_never_bridges():
    db=database([(mod.key((1,1),(2,2)),1,1,2),(mod.key((2,2),(3,3)),2,9,10)])
    assert mod.resolve([[1,1],[2,2],[3,3]],db)==([],'disconnected_public_representation')


def test_empty_slot_stays_empty():
    db=database([]);assert mod.resolve([],db)==([],'empty_native_slot')


def test_same_public_edge_geometry_vertices_collapse_only_same_id():
    db=database([(mod.key((1,1),(2,2)),1,1,3),(mod.key((2,2),(3,3)),1,1,3)])
    assert mod.resolve([[1,1],[2,2],[3,3]],db)==([1],'valid')


def test_cli_projected_public_geometry_and_empty_slots(tmp_path):
    import hashlib,json,os,pickle,subprocess,sys,gzip
    import numpy as np
    import shapefile
    from pyproj import CRS,Transformer
    coords=tmp_path/'coordinates.pkl';rows=[np.array([[39.9,116.3],[39.91,116.31],[39.92,116.32]]),np.empty((0,2))]
    coords.write_bytes(pickle.dumps(rows))
    digest=hashlib.sha256(coords.read_bytes()).hexdigest()
    manifest=tmp_path/'manifest.json';manifest.write_text(json.dumps({'unchanged_released_arrays_verified':True,'output':{'sha256':digest},'original_slot_count':2}))
    network=tmp_path/'network.shp';projection=Transformer.from_crs(4326,32650,always_xy=True)
    with shapefile.Writer(str(network),shapeType=shapefile.POLYLINE) as writer:
        for field in ('id','source','target'):writer.field(field,'N',decimal=0)
        for i,(a,b) in enumerate(zip(rows[0][:-1],rows[0][1:])):
            writer.line([[projection.transform(a[1],a[0]),projection.transform(b[1],b[0])]])
            writer.record(10+i,i,i+1)
    network.with_suffix('.prj').write_text(CRS(32650).to_wkt())
    run=subprocess.run([sys.executable,'-X','utf8',str(Path(mod.__file__)),'--coordinates',str(coords),'--slot-manifest',str(manifest),'--network',str(network),'--out-dir',str(tmp_path/'out')],capture_output=True,encoding='utf-8',env=dict(os.environ,PYTHONUTF8='1'))
    assert run.returncode==0,run.stderr
    with gzip.open(tmp_path/'out/synthetic_routes.pkl.gz','rb') as stream:result=pickle.load(stream)
    assert result[0]['cpath']==[10,11] and result[0]['accepted']
    assert result[1]['cpath']==[] and not result[1]['accepted']
    assert hashlib.sha256(coords.read_bytes()).hexdigest()==digest
    audit=Path(mod.__file__).with_name('verify_dpmm_geometry_roundtrip.py')
    run=subprocess.run([sys.executable,'-X','utf8',str(audit),'--coordinates',str(coords),'--routes',str(tmp_path/'out/synthetic_routes.pkl.gz'),'--network',str(network),'--report',str(tmp_path/'audit.json')],capture_output=True,encoding='utf-8',env=dict(os.environ,PYTHONUTF8='1'))
    assert run.returncode==0,run.stderr
    assert json.loads((tmp_path/'audit.json').read_text())['passed'] is True
