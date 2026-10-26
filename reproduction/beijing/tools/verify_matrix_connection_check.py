"""Verify actual CLI collector output against two unchanged saved score pairs."""
import csv
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if __name__=='__main__':
    folder=ROOT/'validation/connection_cli'
    expected=json.loads((folder/'expected.json').read_text())
    with (folder/'matrix/matrix_sources.csv').open(encoding='utf-8-sig') as f:rows=list(csv.DictReader(f))
    assert len(rows)==1215
    for cell in expected['cells']:
        found=next(r for r in rows if r['row']==cell['row'] and r['column']=='BTF')
        assert float(found['value'])==cell['value'] and found['result_sha256']==cell['source_sha256']
    assert all(r['status']=='MISSING' and r['value']=='' for r in rows if r['row'] not in ['SPRT + STMatch','MTR-DFR'])
    report={'status':'PASSED','source_pairs':2,'matrix_positions':len(rows),'missing_never_filled':True,'formal_experiments_repeated':0}
    (folder/'verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))
