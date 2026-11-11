"""Lossless coordinate adapter around the unchanged AdaTrace author code."""
import argparse
import hashlib
import json
import pickle
import os
import shutil
import subprocess
import time
from pathlib import Path

import numpy as np
from pyproj import Transformer

ROOT = Path(__file__).resolve().parent
DATA = ROOT/'resources/dataset/trajectories.pkl'
DATA_SHA = None

def sha(p):
    with Path(p).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def save(p, data):
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

def main():
    global DATA, DATA_SHA
    p = argparse.ArgumentParser()
    p.add_argument('stage', choices=['build', 'prepare', 'generate', 'bind'])
    p.add_argument('--source', type=Path)
    p.add_argument('--out', type=Path)
    p.add_argument('--limit', type=int, default=0)
    p.add_argument('--epsilon', type=float, default=1.4)
    p.add_argument('--config', type=Path, help='Existing city/experiment configuration')
    p.add_argument('--author-root', type=Path, help='Unchanged author checkout; defaults to paths.adatrace_author_root or vendor/adatrace')
    p.add_argument('--java-home', type=Path, help='JDK directory; otherwise use JAVA_HOME or PATH')
    a = p.parse_args()
    tick = time.perf_counter()
    from preprocess.dataset_config import load_config
    c=load_config(a.config,ROOT) if a.config else {}
    DATA=(ROOT/c.get('paths',{}).get('real',str(DATA))).resolve()
    slots=c.get('slots',15730)
    projection=c.get('adatrace',{}).get('projection',c.get('routing_crs',{}).get('tracks_srs','EPSG:32650'))
    if a.stage!='build': DATA_SHA=sha(DATA)
    author=(a.author_root or ROOT/c.get('paths',{}).get('adatrace_author_root','vendor/adatrace')).resolve()
    classes=ROOT/'resources/adatrace/classes'
    home=a.java_home or c.get('paths',{}).get('java_home') or os.environ.get('JAVA_HOME')
    def java_tool(name):
        suffix='.exe' if os.name=='nt' else ''
        file=str(Path(home)/'bin'/(name+suffix)) if home else shutil.which(name)
        if not file or not Path(file).is_file():raise FileNotFoundError('Configure JDK: '+name)
        return file
    jars = [author/'commons-math3-3.4.1.jar', author/'kd.jar']
    cp = os.pathsep.join(map(str, [classes] + jars))
    if a.stage == 'build':
        if not (author/'src/Main.java').is_file() or not all(x.is_file() for x in jars):raise FileNotFoundError('Incomplete AdaTrace author checkout')
        classes.mkdir(parents=True,exist_ok=False)
        sources = sorted((author/'src').rglob('*.java')) + [ROOT/'vendor/adatrace_adapter/AdaTraceCLI.java']
        argv = [java_tool('javac'), '-encoding', 'UTF-8', '-cp', cp, '-d', str(classes)] + list(map(str, sources))
        save(classes.parent/'build_argv.json', argv)
        subprocess.run(argv, check=True)
        save(classes.parent/'build_manifest.json', dict(status='PASS', sources={str(x):sha(x) for x in sources}, jars={x.name:sha(x) for x in jars}, seconds=time.perf_counter()-tick))
        return
    out = a.out.resolve()
    if a.stage == 'bind':
        assert a.source is not None and a.limit == 0
        source=a.source.resolve()
        proof=json.loads((source/'input_manifest.json').read_text(encoding='utf-8'))
        assert proof['status']=='PASS' and proof['scope']=='FULL' and proof['slots']==slots
        assert proof['input_sha256']==DATA_SHA and sha(source/'input.dat')==proof['author_text_sha256']
        out.mkdir(parents=True,exist_ok=False)
        os.link(source/'input.dat',out/'input.dat')
        shutil.copy2(source/'input_manifest.json',out/'input_manifest.json')
        save(out/'input_reuse.json',dict(source=str(source),sha256=proof['author_text_sha256'],policy='same-byte NTFS hardlink; no reprocessing or private fitting',seconds=time.perf_counter()-tick))
        return
    if a.stage == 'prepare':
        out.mkdir(parents=True, exist_ok=False)
        assert sha(DATA) == DATA_SHA
        with DATA.open('rb') as f:
            real = pickle.load(f)
        assert len(real) == slots
        if a.limit:
            assert a.limit > 0
            real = real[:a.limit]
        forward = Transformer.from_crs(4326, projection, always_xy=True)
        inverse = Transformer.from_crs(projection, 4326, always_xy=True)
        points = 0
        err = 0.
        with (out/'input.dat').open('w', encoding='ascii') as f:
            for i, item in enumerate(real):
                arr = np.asarray(item, dtype=float)[:, :2]
                assert len(arr) >= 2 and np.isfinite(arr).all()
                x,y = forward.transform(arr[:,1], arr[:,0])
                lon,lat = inverse.transform(x,y)
                err = max(err, float(np.max(np.abs(np.array([lat,lon]).T-arr))))
                f.write(f'#{i}:\n>0:' + ';'.join(f'{u:.12f},{v:.12f}' for u,v in zip(x,y)) + '\n')
                points += len(arr)
                if (i+1)%500 == 0:
                    print(f'PREPARED_SLOTS={i+1}/{len(real)}', flush=True)
        assert err < 1e-8
        save(out/'input_manifest.json', dict(status='PASS', slots=len(real), points=points, input_sha256=DATA_SHA, author_text_sha256=sha(out/'input.dat'), crs=projection, coordinate_order='easting,northing; inverse output lat,lon', roundtrip_max_degrees=err, scope='PREFLIGHT_ONLY' if a.limit else 'FULL', seconds=time.perf_counter()-tick))
        return
    info = json.loads((out/'input_manifest.json').read_text(encoding='utf-8'))
    assert info['status']=='PASS' and sha(out/'input.dat')==info['author_text_sha256']
    assert info['input_sha256']==DATA_SHA and info['crs']==projection
    assert not (out/'measurement.pkl').exists()
    argv = [java_tool('java'), '-Xmx6g', '-cp', cp, 'AdaTraceCLI', str(out/'input.dat'), str(out/'synthetic.dat'), str(a.epsilon)]
    save(out/'java_argv.json', argv)
    with (out/'java.log').open('w', encoding='utf-8') as log:
        result = subprocess.run(argv, stdout=log, stderr=subprocess.STDOUT)
    save(out/'java_exit.json', dict(returncode=result.returncode, seconds=time.perf_counter()-tick))
    if result.returncode:
        raise RuntimeError((out/'java.log').read_text(encoding='utf-8'))
    inverse = Transformer.from_crs(projection, 4326, always_xy=True)
    syn = []
    with (out/'synthetic.dat').open(encoding='utf-8') as f:
        for line in f:
            if line.startswith('#'):
                continue
            xy = np.array([[float(v) for v in pair.split(',')] for pair in line.strip()[3:].split(';') if pair])
            lon,lat = inverse.transform(xy[:,0],xy[:,1])
            arr = np.column_stack([lat,lon])
            assert np.isfinite(arr).all()
            syn.append(arr)
    assert len(syn) == info['slots']
    with (out/'measurement.pkl').open('xb') as f:
        pickle.dump(syn,f,pickle.HIGHEST_PROTOCOL)
    build = json.loads((classes.parent/'build_manifest.json').read_text(encoding='utf-8'))
    save(out/'measurement_manifest.json', dict(schema_version=1,kind='measurement',status='VALID',M='AdaTrace',epsilon=a.epsilon,seed=None,randomness='Unmodified author code uses multiple unseeded RNGs; fixed seed not controlled', public_slot_count=len(syn), input_sha256=DATA_SHA, source_sha256=sha(author/'src/Main.java'), upstream_commit='55fc77b7255b8871c4ac6f95f6c12a141a07bdfc', parameters=dict(grid=6,budget_weights=[.05,.35,.5,.1],attacks=False,projection=projection), classification='AUTHOR_CODE_RESEARCH_BASELINE_NOT_INDEPENDENTLY_PRIVACY_CERTIFIED', implementation='git-disl/AdaTrace unchanged synthesis; argument/coordinate adapter', author_variant='TripDistribution.java explicitly implements DP-Star single-level OD, not CCS two-level OD+OLS; report as AdaTrace public-code variant',outputs={'measurement.pkl':sha(out/'measurement.pkl')},author_sources=build['sources'],scope=info['scope'],elapsed_seconds=time.perf_counter()-tick))
    print(json.dumps(dict(slots=len(syn),seconds=time.perf_counter()-tick,status='VALID')), flush=True)

if __name__=='__main__':
    main()
