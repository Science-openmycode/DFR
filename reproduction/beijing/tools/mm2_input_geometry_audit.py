"""Read frozen MM2 inputs and completed native durations without rematching."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics


def summary(xs):
    s=sorted(xs)
    return dict(n=len(s),mean=statistics.mean(s) if s else None,
                p50=s[int((len(s)-1)*.5)] if s else None,
                p90=s[int((len(s)-1)*.9)] if s else None,
                p99=s[int((len(s)-1)*.99)] if s else None,max=max(s,default=None))


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    if a.out.exists():raise FileExistsError(a.out)
    report={}
    csv.field_size_limit(64*1024*1024)
    for method in ['SPRT','PrivTrace','DPStd','DPTraj-PM']:
        base=a.root/'results/roads_8_16_20261016/routes'/method/'MM2-MDP'
        f=base/'mm2_tracks.csv'
        steps=[];lengths=[];counts=[];chords=[]
        with f.open(encoding='utf-8',newline='') as handle:
            for row in csv.DictReader(handle):
                pts=[tuple(map(float,x.split())) for x in row['geometry'].split('(',1)[1].rstrip(')').split(',')]
                ds=[math.dist(x,y) for x,y in zip(pts,pts[1:])]
                steps.extend(ds);lengths.append(sum(ds));counts.append(len(pts));chords.append(math.dist(pts[0],pts[-1]))
        meta=dict(input_sha256=hashlib.sha256(f.read_bytes()).hexdigest(),
                  sampled_point_counts=summary(counts),step_distance_m=summary(steps),
                  sampled_polyline_length_m=summary(lengths),endpoint_chord_m=summary(chords),
                  step_over_1km_share=sum(d>1000 for d in steps)/len(steps))
        manifest=base/'route_manifest.json'
        if manifest.exists():
            m=json.loads(manifest.read_text());d=[]
            with (base/'mm2_run/matches.csv').open(encoding='utf-8',newline='') as h:
                for row in csv.DictReader(h):d.append(float(row['duration']))
            meta['completed_native_duration_seconds']=summary(d)
            meta['native_duration_sum_seconds']=sum(d)
            meta['final_output_sha256']=m.get('output_sha256')
        report[method]=meta
    a.out.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))


if __name__=='__main__':main()
