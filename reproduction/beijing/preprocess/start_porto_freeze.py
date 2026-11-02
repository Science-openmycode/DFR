"""Freeze audited original START trips with deterministic geometry views and splits."""
import argparse
from contextlib import ExitStack
import csv
import gzip
import hashlib
import json
from pathlib import Path
import pickle
import sys
import time
import zipfile
import numpy as np
from start_porto import rows, sha


class PickleList:
    """Bounded-memory standard pickle list; each item has a private protocol-3 memo.

    Protocol 3 uses explicit memo indices, so each item's BINPUT instructions can
    overwrite previous indices without affecting already appended objects.
    Do not upgrade this to protocol 4 (implicit MEMOIZE indices).
    """
    def __init__(self, stream):
        self.stream=stream; self.stream.write(b'\x80\x03]')
    def append(self,item):
        data=pickle.dumps(item,protocol=3)
        assert data[:2]==b'\x80\x03' and data[-1:]==b'.'
        self.stream.write(data[2:-1]); self.stream.write(b'a')
    def finish(self):self.stream.write(b'.')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive',type=Path,required=True)
    p.add_argument('--audit',type=Path,required=True)
    p.add_argument('--audit-sha256',required=True)
    p.add_argument('--graph',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--seed',type=int,default=20260713)
    a=p.parse_args();started=time.monotonic()
    if a.out.exists():p.error('Existing output is never overwritten')
    if sha(a.audit/'manifest.json')!=a.audit_sha256:raise ValueError('Audit changed')
    audit=json.loads((a.audit/'manifest.json').read_text())
    if audit['status']!='MAPPING_AUDIT_COMPLETE_NOT_FROZEN':raise ValueError('Audit incomplete')
    if sha(a.archive)!=audit['source_sha256']:raise ValueError('Source changed')
    if sha(a.graph/'manifest.json')!=audit['public_manifest_sha256']:raise ValueError('Graph changed')
    graph=json.loads((a.graph/'manifest.json').read_text())
    if graph['status']!='AUTHOR_PRE_VOCABULARY_GRAPH_EXPORTED':raise ValueError('Author graph required')
    for base, outputs in ((a.graph,graph['outputs']),(a.audit,audit['outputs'])):
        for name,digest in outputs.items():
            if Path(name).name!=name or sha(base/name)!=digest:raise ValueError('Artifact mismatch: '+name)
    mapping=json.loads((a.graph/'road_mapping.json').read_text())
    audit_rows=[];excluded=[]
    with (a.audit/'trajectory_audit.csv').open(encoding='utf-8',newline='') as f:
        for index,row in enumerate(csv.DictReader(f)):
            keep=row['status']=='MAPPING_ELIGIBLE' and not row['duplicate_of']
            audit_rows.append((row['original_split'],int(row['row_number']),row['source_id'],keep))
            if not keep:excluded.append(dict(source_index=index,reason=('DUPLICATE_PATH_TIME' if row['duplicate_of'] else row['status']),duplicate_of=row['duplicate_of']))
    n=sum(r[3] for r in audit_rows)
    if n<2:raise ValueError('Insufficient eligible population')
    permutation=np.random.default_rng(a.seed).permutation(n);ntrain=round(.8*n)
    in_train=np.zeros(n,dtype=bool);in_train[permutation[:ntrain]]=True
    indices={'train':np.flatnonzero(in_train).tolist(),'test':np.flatnonzero(~in_train).tolist()}
    a.out.mkdir(parents=True)
    source_ids=[]; source_position=0; kept=0
    with ExitStack() as stack,zipfile.ZipFile(a.archive) as z:
        original={str(int(r['geo_id'])):json.loads(r['coordinates']) for r in rows(z,'porto_roadmap_edge/porto_roadmap_edge.geo')}
        writers={}
        for name in ('trajectories.pkl','trajectories.pkl.gz','road_records.pkl.gz','train.pkl','test.pkl','start_road_timestamps.pkl.gz'):
            stream=stack.enter_context(gzip.open(a.out/name,'wb',compresslevel=3) if name.endswith('.gz') else (a.out/name).open('wb'))
            writers[name]=PickleList(stream)
        lineage=csv.writer(stack.enter_context((a.out/'source_lineage.csv').open('w',encoding='utf-8',newline='')))
        lineage.writerow(['dataset_index','source_index','original_split','row_number','original_id','start_ts','end_ts','coordinate_sha256'])
        for split in ('train','eval','test'):
            for number,row in enumerate(rows(z,f'porto/porto_{split}.csv',';')):
                expected=audit_rows[source_position]
                if (split,number,row.get('id',''))!=expected[:3]:raise ValueError('Audit/source alignment changed')
                current_source=source_position;source_position+=1
                if not expected[3]:continue
                path=json.loads(row['path']);times=json.loads(row['tlist'])
                # One deterministic road-start representative per START road
                # timestamp. These are geometry views, never claimed as GPS.
                coords=np.asarray([[original[str(e)][0][1],original[str(e)][0][0]] for e in path],dtype='<f8')
                opath=[mapping[str(e)]['edges'][0] for e in path]
                cpath=[segment for i,e in enumerate(path) if i==0 or e!=path[i-1]
                       for segment in mapping[str(e)]['edges']]
                record=dict(source_index=current_source,source_points=len(coords),cpath=cpath,opath=opath,
                            connected=True,accepted=True,reason='AUTHOR_ROAD_SEQUENCE',
                            coordinate_representation='source_road_start_geometry',matching_executed=False)
                for name in ('trajectories.pkl','trajectories.pkl.gz'):writers[name].append(coords)
                writers['road_records.pkl.gz'].append(record)
                writers['start_road_timestamps.pkl.gz'].append(np.asarray(times,dtype='<f8'))
                writers['train.pkl' if in_train[kept] else 'test.pkl'].append(coords)
                lineage.writerow([kept,current_source,split,number,row.get('id',''),times[0],times[-1],hashlib.sha256(coords.tobytes()).hexdigest()])
                source_ids.append(current_source);kept+=1
                if kept%100000==0:print(json.dumps({'converted':kept,'eligible':n}),flush=True)
        if source_position!=len(audit_rows) or kept!=n:raise ValueError('Population count mismatch')
        for writer in writers.values():writer.finish()
    for split,ids in indices.items():
        (a.out/f'{split}_split.json').write_text(json.dumps(dict(indices=ids,source_indices=[source_ids[i] for i in ids])),encoding='utf-8')
    (a.out/'source_indices.json').write_text(json.dumps(source_ids),encoding='utf-8')
    (a.out/'bbox.json').write_text(json.dumps(dict(bbox=graph['bbox'])),encoding='utf-8')
    review=dict(source_count=len(audit_rows),retained=n,excluded=len(excluded),exclusions=excluded,
                rule='retain mapping-valid original records; keep first exact path/time record in original split order',
                coordinate_view='one source directed road-start point per START timestamp; no GPS recovery or time interpolation')
    (a.out/'selection_review.json').write_text(json.dumps(review,indent=2),encoding='utf-8')
    manifest=dict(schema='frozen-road-dataset-v1',dataset='porto',status='FROZEN',trajectory_count=n,
        train_count=ntrain,test_count=n-ntrain,seed=a.seed,projected_crs='EPSG:32629',
        split_order='RNG membership with source-order records within each split',
        network=str((a.graph/'network.shp').resolve()),network_sha256=sha(a.graph/'network.shp'),
        network_sidecars={suffix:sha(a.graph/('network'+suffix)) for suffix in ('.shp','.shx','.dbf','.prj','.cpg')},
        original_source_sha256=audit['source_sha256'],mapping_audit_sha256=a.audit_sha256,
        graph_manifest_sha256=audit['public_manifest_sha256'],
        coordinates='Deterministic source-road start geometry view, one point per processed START road timestamp; not raw GPS',
        time_semantics='Original START processed UTC timestamp arrays preserved unchanged; no intermediate road times invented',
        release_note='Private research input, not a DP release; author-provided pre-vocabulary public graph',
        selection_review_sha256=sha(a.out/'selection_review.json'),
        artifacts={f.name:sha(f) for f in a.out.iterdir() if f.is_file()},
        argv=[sys.executable,*sys.argv],code_sha256=sha(__file__),elapsed_seconds=time.monotonic()-started)
    (a.out/'canonical_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in manifest.items() if k not in ('argv','artifacts')},indent=2))


if __name__=='__main__':main()
