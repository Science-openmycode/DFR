"""Select four short real records for an isolated preprocessing CLI check."""
import argparse
import csv
import gzip
import json
from pathlib import Path
import pickle

ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--metadata',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    if a.out.exists():raise FileExistsError(a.out)
    with a.source.open('rb') as f:raw=pickle.load(f)
    with gzip.open(a.metadata/'timestamps_day_serial.pkl.gz','rb') as f:times=pickle.load(f)
    with (a.metadata/'source_binding.csv').open(encoding='utf-8-sig',newline='') as f:bindings=list(csv.DictReader(f))
    if len(raw)!=len(times) or len(raw)!=len(bindings):raise ValueError('Original metadata count differs')
    selected=[i for i,t in enumerate(raw) if 21<=len(t)<=50][:4]
    if len(selected)!=4:raise ValueError('Need four eligible short records for this documented check')
    a.out.mkdir(parents=True)
    with (a.out/'source.pkl').open('wb') as f:pickle.dump([raw[i] for i in selected],f,pickle.HIGHEST_PROTOCOL)
    with gzip.open(a.out/'timestamps.pkl.gz','wb') as f:pickle.dump([times[i] for i in selected],f,pickle.HIGHEST_PROTOCOL)
    rows=[dict(bindings[i],source_index=str(j)) for j,i in enumerate(selected)]
    with (a.out/'bindings.csv').open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    config=json.loads((ROOT/'configs/preprocess_beijing_8_16.json').read_text(encoding='utf-8'))
    config['paths'].update(source=str((a.out/'source.pkl').resolve()),
        timestamps=str((a.out/'timestamps.pkl.gz').resolve()),
        **{'timestamp-bindings':str((a.out/'bindings.csv').resolve())})
    config['parameters']['threads']=2
    (a.out/'preprocess.json').write_text(json.dumps(config,indent=2),encoding='utf-8')
    record=dict(classification='REAL_SUBSET_CLI_CHECK_NOT_FULL_CORPUS_EXPERIMENT',
        original_indices=selected,points=[len(raw[i]) for i in selected],count=4)
    (a.out/'selection.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
    print(json.dumps(record))

if __name__=='__main__':main()
